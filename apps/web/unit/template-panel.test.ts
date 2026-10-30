import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { contentText, responseBlocks } from "../src/rich/v7-response";
import { templateSchema } from "../src/rich/template-schema";
import { panelCommandsV7 } from "../src/rich/v7-panel";
import { focusOptions, searchIcons, wholeYears, yearsValue } from "../src/rich/v7-focus";
import { parseFocusIconChoices } from "../src/projects/api";
import { ProjectApiFailure } from "../src/rich/v7-connection";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { projectClient, harness, type Harness, type Traffic } from "./support/template-harness";

function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

const kinds = new Map([["job", "employment"], ["tech", "technology"], ["person", "candidate"], ["school", "education"], ["note", "claim"]]);
test("Focus rows and technology edits are forwarded", () => {
  assert.deepEqual(panelCommandsV7({ operation: "move_focus", recordId: "tech", beforeRecordId: "other" }, kinds),
    [{ operation: "move_focus", recordId: "tech", beforeRecordId: "other" }]);
  assert.deepEqual(panelCommandsV7({ operation: "move_focus", recordId: "tech", beforeRecordId: null }, kinds),
    [{ operation: "move_focus", recordId: "tech" }]);
  assert.deepEqual(panelCommandsV7({ operation: "add_to_focus", recordId: "tech" }, kinds), [{ operation: "add_to_focus", recordId: "tech" }]);
  assert.deepEqual(panelCommandsV7({ operation: "remove_from_focus", recordId: "tech" }, kinds),
    [{ operation: "remove_from_focus", recordId: "tech" }]);
  assert.deepEqual(panelCommandsV7({ operation: "edit", recordId: "tech", values: { experience: "" } }, kinds),
    [{ operation: "edit", recordId: "tech", values: { experience: "" } }]);
  assert.equal(panelCommandsV7({ operation: "add_to_focus", recordId: "job" }, kinds), null);
  assert.deepEqual(panelCommandsV7({ operation: "edit", recordId: "tech", values: { experience: "3", display: "Go" } }, kinds),
    [{ operation: "edit", recordId: "tech", values: { experience: "3", display: "Go" } }]);
});

test("only what Python saves is forwarded: technology add, removal and clearing, other records' fields, item removal", () => {
  assert.deepEqual(panelCommandsV7({ operation: "add", recordKind: "technology", jobId: "job", values: { display: "Go" }, lineBlockId: "line" }, kinds),
    [{ operation: "add", recordKind: "technology", jobId: "job", values: { display: "Go" } }]);
  assert.deepEqual(panelCommandsV7({ operation: "remove", recordId: "tech" }, kinds), [{ operation: "remove", recordId: "tech" }]);
  assert.deepEqual(panelCommandsV7({ operation: "clear_technologies", recordKind: "technology", jobId: null, recordId: null, periodId: null, values: {} }, kinds),
    [{ operation: "clear_technologies", recordKind: "technology", jobId: null, recordId: null, periodId: null, values: {} }]);
  assert.deepEqual(panelCommandsV7({ operation: "edit", recordId: "person", values: { name: "Alex" } }, kinds),
    [{ operation: "edit", recordId: "person", values: { name: "Alex" } }]);
  assert.deepEqual(panelCommandsV7({ operation: "remove", recordId: "school" }, kinds), [{ operation: "remove", recordId: "school" }]);
  assert.deepEqual(panelCommandsV7({ operation: "edit", recordId: "note", values: { value: "Led a team" } }, kinds),
    [{ operation: "edit", recordId: "note", values: { value: "Led a team" } }]);
  // No adapter: a candidate or claim removal, adding an education item, a claim or a technology with other values.
  for (const command of [{ operation: "remove", recordId: "person" }, { operation: "remove", recordId: "note" },
    { operation: "add", recordKind: "education", values: { institution: "School" } }, { operation: "add", recordKind: "claim", values: { value: "x" } },
    { operation: "add", recordKind: "technology", values: { display: "Go", experience: "3" } }, { operation: "edit", recordId: "person", values: {} },
    { operation: "edit", recordId: "school", jobId: "job", values: { institution: "School" } }] as const)
    assert.equal(panelCommandsV7(command, kinds), null, JSON.stringify(command));
});

test("a Focus icon choice is forwarded with the icon alone; an empty icon returns to the template's choice", () => {
  assert.deepEqual(panelCommandsV7({ operation: "set_focus_icon", recordId: "tech", values: { icon: "mysql" } }, kinds),
    [{ operation: "set_focus_icon", recordId: "tech", values: { icon: "mysql" } }]);
  assert.deepEqual(panelCommandsV7({ operation: "set_focus_icon", recordId: "tech", values: { icon: "" } }, kinds),
    [{ operation: "set_focus_icon", recordId: "tech", values: { icon: "" } }]);
  for (const command of [{ operation: "set_focus_icon", recordId: "tech" }, { operation: "set_focus_icon", recordId: "tech",
    values: { icon: "mysql", experience: "3" } }, { operation: "set_focus_icon", recordId: "job", values: { icon: "mysql" } },
    { operation: "set_focus_icon", recordId: "tech", jobId: "job", values: { icon: "mysql" } }] as const)
    assert.equal(panelCommandsV7(command, kinds), null, JSON.stringify(command));
});

test("the icon search ranks a whole name, its start, a word's start, then any part, and never lists every icon", () => {
  const icon = (id: string, ...names: string[]) => ({ id, names, sha256: "a".repeat(64) });
  const icons = [icon("mssql", "microsoft sql server", "msql", "mssql"), icon("mysql", "mysql"), icon("postgresql", "postgres", "postgresql"),
    icon("sqlite", "sqlite"), icon("csharp", "c#", "csharp"), icon("cplusplus", "c++", "cplusplus")];
  assert.deepEqual(searchIcons(icons, " "), []);
  assert.deepEqual(searchIcons(icons, "SQL").map(value => [value.id, value.label]),
    [["sqlite", "sqlite"], ["mssql", "microsoft sql server"], ["mysql", "mysql"], ["postgresql", "postgresql"]]);
  assert.deepEqual(searchIcons(icons, "Postgres").map(value => value.label), ["postgres"]);
  // Punctuation is ignored except # and +, which tell C# from C++.
  assert.deepEqual(searchIcons(icons, "C#").map(value => value.id), ["csharp"]);
  assert.deepEqual(searchIcons(icons, "c++").map(value => value.id), ["cplusplus"]);
  assert.deepEqual(searchIcons(icons, "sql-server").map(value => value.id), ["mssql"]);
  assert.equal(searchIcons(icons, "s", 2).length, 2);
});

test("icon choices from Python are checked before the search uses them", () => {
  const value = { schemaVersion: 1, icons: [{ id: "mysql", names: ["mysql"], sha256: "b".repeat(64) }],
    rows: { tech: { automatic: { id: "initial-1", sha256: "c".repeat(64) }, remembered: "mysql" }, other: { automatic: null, remembered: null } } };
  const parsed = parseFocusIconChoices(value);
  assert.deepEqual(parsed.icons, value.icons);
  assert.deepEqual(parsed.rows.get("tech"), value.rows.tech);
  assert.deepEqual(parsed.rows.get("other"), { automatic: null, remembered: null });
  for (const broken of [{ ...value, schemaVersion: 2 }, { ...value, icons: [{ id: "mysql", names: ["mysql"], sha256: "short" }] },
    { ...value, rows: { tech: { automatic: null, remembered: 3 } } }, { ...value, rows: { tech: { automatic: "mysql", remembered: null } } },
    { ...value, rows: [] }])
    assert.throws(() => parseFocusIconChoices(broken), ProjectApiFailure, JSON.stringify(broken));
});

test("stated experience gives whole years only when it states them", () => {
  assert.deepEqual(["3 года", "1 год", "11 лет", "2 years", " 1 year ", "10 месяцев", "1,5 года", "около 3 лет", ""].map(wholeYears),
    [3, 1, 11, 2, 1, null, null, null, null]);
});

test("the years field sends whole years as digits and nothing for other input", () => {
  assert.deepEqual(["3", "3.0", "1e1", "-0", "0", "100", ""].map(value => yearsValue(value, false)), ["3", "3", "10", "0", "0", "100", ""]);
  assert.deepEqual(["3.5", "-1", "101", "x"].map(value => yearsValue(value, false)), [null, null, null, null]);
  // A half-typed value (3-) reads as "" in the browser; it must not clear the stated years.
  assert.equal(yearsValue("", true), null);
});

test("a Focus option binds a general record no line shows before another general one, and a job's last", () => {
  const record = (id: string, name: string, jobId: string | null = null) => ({ id, jobId, display: { rawText: name } });
  const options = focusOptions([record("group-python", "Python"), record("focus-python", "Python"), record("job-kafka", "Kafka", "job"),
    record("group-go", "Go"), record("job-go", "go", "job"), record("job-rust", "Rust", "job"), record("shown-sql", "SQL")],
    new Set(["group-python", "group-go", "job-rust"]), new Set(["sql"]));
  assert.deepEqual(options.map(value => value.recordId), ["group-go", "job-kafka", "focus-python", "job-rust"]);
});

test("panel commands adapt to Python's V7 employment form; a technology reorder is forwarded", () => {
  assert.deepEqual(panelCommandsV7({ operation: "edit", recordId: "job", values: { role: "Lead", "period:p1:start": "01.2021" } }, kinds),
    [{ operation: "edit", recordId: "job", values: { role: "Lead", "period:p1:start": "01.2021" } }]);
  assert.deepEqual(panelCommandsV7({ operation: "remove_period", recordId: "job", periodId: "p1", values: { role: "Lead" } }, kinds),
    [{ operation: "edit", recordId: "job", values: { role: "Lead" } }, { operation: "remove_period", recordId: "job", periodId: "p1" }]);
  assert.deepEqual(panelCommandsV7({ operation: "add_period", recordId: "job", values: {} }, kinds),
    [{ operation: "add_period", recordId: "job", values: {} }]);
  assert.deepEqual(panelCommandsV7({ operation: "add", recordKind: "employment", values: { employer: "Acme", start: "01.2024" } }, kinds),
    [{ operation: "add", recordKind: "employment", values: { employer: "Acme", start: "01.2024" } }]);
  assert.deepEqual(panelCommandsV7({ operation: "move_technology", recordId: "tech", beforeRecordId: "other" }, kinds),
    [{ operation: "move_technology", recordId: "tech", beforeRecordId: "other" }]);
  assert.deepEqual(panelCommandsV7({ operation: "move_technology", recordId: "tech", beforeRecordId: null }, kinds),
    [{ operation: "move_technology", recordId: "tech" }]);
  assert.equal(panelCommandsV7({ operation: "move_technology", recordId: "job", beforeRecordId: "tech" }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "edit", recordId: "job", values: {} }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "remove", recordId: "job", jobId: "job" }, kinds), null);
});

type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[] };
async function opened(value: Harness): Promise<Opened> {
  const warnings: string[] = [];
  const traffic: Traffic[] = [];
  const connection = await projectClient(value, traffic);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = session.queue.template.durable;
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  await session.recoverDraft();
  return { session, editor, warnings };
}
function issues(session: TemplateEditorSession): Record<string, string> {
  return Object.fromEntries((session.queue.template.durable.workspace.project?.importIssues ?? []).map(issue => [issue.id, issue.state]));
}
function employment(session: TemplateEditorSession): { id: string; role: string } {
  const record = session.queue.template.durable.workspace.project?.facts.records.find(item => item.kind === "employment");
  assert.ok(record?.kind === "employment");
  return { id: record.id, role: record.role.rawText };
}

function roleText(session: TemplateEditorSession): string {
  for (const block of responseBlocks(session.queue.template.durable).values()) {
    const group = block.groups[0];
    if (group?.kind === "content" && contentText(group.content).startsWith("Role: ")) return contentText(group.content);
  }
  return assert.fail("role paragraph missing");
}
/** The PM position just after the role field's last character, inside the field node. */
function roleEnd(editor: TemplateEditor): number {
  let found = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => {
    if (node.type.name === "templateField" && node.attrs["fieldKey"] === "role") found = pos + 1 + node.content.size;
    return found < 0;
  });
  assert.ok(found > 0); return found;
}
function dispatch(editor: TemplateEditor, work: (tr: ReturnType<TemplateEditor["_tiptapEditor"]["state"]["tr"]["insertText"]>) => void): void {
  const tr = editor._tiptapEditor.state.tr; work(tr); editor._tiptapEditor.view.dispatch(tr);
}

test("a panel role edit saves through Python with input locked until its result is shown", async () => {
  const value = await harness("issues");
  const { session } = await opened(value);
  try {
    const job = employment(session);
    const done = session.panel({ operation: "edit", recordId: job.id, values: { role: "staff engineer" } });
    await done;
    assert.equal(employment(session).role, "staff engineer");
    assert.equal(roleText(session), "Role: staff engineer");
    assert.equal(session.writable, true);
    assert.equal(session.history.length, 1, "one panel action");
  } finally { session.close(); await value.close(); }
});

test("E03: editing A retires only A; Undo restores it, Redo retires it, retyping the old wording keeps it retired", async () => {
  const value = await harness("issues");
  const { session, editor } = await opened(value);
  try {
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "active" });
    const end = roleEnd(editor);
    dispatch(editor, tr => { tr.setSelection(TextSelection.create(tr.doc, end)); });
    dispatch(editor, tr => { tr.insertText("!", end); });
    await session.flush();
    assert.equal(roleText(session), "Role: backend engineer!");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "retired" });
    await session.navigate("undo");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "active" });
    assert.equal(roleText(session), "Role: backend engineer");
    await session.navigate("redo");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "retired" });
    // Restoring the original wording is a new edit; it does not reactivate the issue.
    const after = roleEnd(editor);
    dispatch(editor, tr => { tr.delete(after - 1, after); });
    await session.flush();
    assert.equal(roleText(session), "Role: backend engineer");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "retired" });
  } finally { session.close(); await value.close(); }
});

test("a technology rename saves through Python; an action without an adapter is refused without touching the queue", async () => {
  const value = await harness("issues");
  const { session, warnings } = await opened(value);
  try {
    const records = () => session.queue.template.durable.workspace.project?.facts.records ?? [];
    const technology = records().find(item => item.kind === "technology");
    assert.ok(technology);
    await session.panel({ operation: "edit", recordId: technology.id, values: { display: "Go" } });
    const renamed = records().find(item => item.id === technology.id);
    assert.ok(renamed?.kind === "technology");
    assert.equal(renamed.display.rawText, "Go");
    await assert.rejects(session.panel({ operation: "add", recordKind: "language", values: { language: "French" } }), /PANEL_ACTION_UNSUPPORTED/);
    // Python's refusal keeps its code for the panel's text, and the editor takes the next command.
    await assert.rejects(session.panel({ operation: "edit", recordId: technology.id, values: { display: "  " } }),
      (error: unknown) => error instanceof ProjectApiFailure && error.code === "TECHNOLOGY_NAME_REQUIRED" && error.status === 422);
    assert.equal(session.queue.template.state.kind, "ready");
    await session.panel({ operation: "edit", recordId: technology.id, values: { display: "Rust" } });
    assert.equal(session.queue.template.pending.length, 0);
    // The facts panel shows the refusals; the editor's notices stay clear.
    assert.equal(warnings.length, 0);
  } finally { session.close(); await value.close(); }
});

test("a finding on a fact reaches its row through the panel's focus request", () => {
  // The handle runs only in a mounted tree, so the wiring is read from the component.
  const source = readFileSync(new URL("../src/rich/TemplateEditor.tsx", import.meta.url), "utf8");
  assert.match(source, /setFactFocus\(\{ recordId: anchor\.recordId \}\)/u);
  assert.match(source, /focusRequest=\{factFocus\} onFocused=\{factFocused\}/u);
});
