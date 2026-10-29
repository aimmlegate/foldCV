import assert from "node:assert/strict";
import test from "node:test";
import { Schema, type Node } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { DecorationSet } from "@tiptap/pm/view";
import { DOUBTFUL_VALUE, remarkMarks, remarkMarksPlugin, type RemarkMarks } from "../src/rich/remarks";
import { groupAnchors, type OutlineDocument } from "../src/rich/outline";

type Block = OutlineDocument["regions"][number]["blocks"][number];
const text = (value: string) => ({ type: "text", text: value, styles: {} });
const fact = (recordId: string, key: string, value: string) => ({ type: "fact_field", recordId, fieldKey: key,
  cellId: JSON.stringify(["fact", recordId, key]), text: value, styles: {} });
const line = (id: string, content: unknown[], children: Block[] = []): Block => ({ id, type: "paragraph", content, children });
const heading = (id: string, value: string): Block => ({ id, type: "heading", content: [text(value)], children: [] });
const item = (id: string, recordId: string | null, children: Block[]): Block =>
  ({ id, type: "section", content: [], props: recordId ? { recordId } : {}, children });
const cell = (recordId: string, key: string) => JSON.stringify(["fact", recordId, key]);

// A header without a heading, Focus rows in the sidebar, then jobs with technology chips and claims, and a tools line
// that is no item.
const document: OutlineDocument = { regions: [
  { id: "header", role: "header", blocks: [item("identity", "candidate", [line("name", [fact("candidate", "name", "Alex Example")])])] },
  { id: "sidebar", role: "sidebar", blocks: [heading("focus", "ФОКУС"),
    item("focus-python", "python", [line("python", [fact("python", "display", "Python")]), line("python-years", [text("3 года")])]),
    heading("education", "ОБРАЗОВАНИЕ"), item("school", "school", [line("school-name", [fact("school", "institution", "MIT")])])] },
  { id: "main", role: "main", blocks: [heading("summary", "О СЕБЕ"), line("about", [text("Backend engineer.")]),
    heading("projects", "ПРОЕКТЫ"),
    item("labs", "labs", [line("labs-title", [fact("labs", "employer", "Example Labs")]),
      line("labs-dates", [fact("labs", "period:p1:start", "весна 2021"), text(" — "), fact("labs", "period:p1:end", "н.в.")]),
      line("labs-chips", [fact("python", "display", "Python"), text(" "), fact("nginx", "display", "Nginx")]),
      line("labs-claim", [fact("claim", "value", "Cut latency")])]),
    line("fallback", [text("Reduced median latency by 80%.")]),
    heading("tools", "ИНСТРУМЕНТЫ"), line("tools-line", [fact("nginx", "display", "Nginx"), text(", "), fact("kafka", "display", "Kafka")])] },
] };
const issue = (targetIds: string[], blockIds: string[], message = "Замечание", state = "active") => ({ state, message, targetIds, blockIds });
const known = (rawText: string) => ({ rawText, value: rawText, status: "known" });
const unresolved = (rawText: string) => ({ rawText, value: null, status: "unresolved" });
const sorted = (map: ReadonlyMap<string, readonly string[]>) => [...map].sort(([left], [right]) => left.localeCompare(right));

test("a remark marks the fields it names wherever the text shows them, not the blocks Python placed it on", () => {
  // As the skill group remark: technology cells as targets, and blocks found by shared source lines.
  const marks = remarkMarks(document, [issue([cell("nginx", "display")], ["about", "focus-python", "labs-chips"], "Группа не определена.")]);
  assert.deepEqual(sorted(marks.cells), [[cell("nginx", "display"), ["Группа не определена."]]], "the chip and the tools line share one cell");
  assert.equal(marks.blocks.size, 0);
});

test("a remark without a shown field marks its blocks; a named heading stands for its whole section", () => {
  const marks = remarkMarks(document, [
    issue([cell("gone", "display"), "scope-task"], ["fallback", "tools-line"], "Показан исходный текст."),
    issue(["scope-outline"], ["projects", "labs", "labs-title", "labs-claim", "fallback"], "Разметка записей под вопросом."),
    issue(["scope-other"], ["school", "deleted-block"], "Образование под вопросом."),
  ]);
  assert.deepEqual(sorted(marks.blocks), [
    ["projects", ["Разметка записей под вопросом."]],
    ["school-name", ["Образование под вопросом."]],
    ["tools-line", ["Показан исходный текст."]],
    ["fallback", ["Показан исходный текст."]],
  ].sort(([left], [right]) => String(left).localeCompare(String(right))),
  "a section's other blocks keep only remarks that do not name its heading; an item frame marks its lines");
  assert.equal(marks.cells.size, 0);
});

test("retired, blank and target-less remarks mark nothing; one place keeps each distinct message once", () => {
  const marks = remarkMarks(document, [
    issue([cell("kafka", "display")], [], "Старое", "retired"),
    issue([cell("kafka", "display")], [], "   "),
    issue([], ["about", "labs-title"], "Тип роли не определён."),
    issue([cell("kafka", "display")], [], "Первое"),
    issue([cell("kafka", "display"), cell("nginx", "display")], [], "Первое"),
    issue([cell("kafka", "display")], [], "Второе"),
  ]);
  assert.deepEqual(sorted(marks.cells), [[cell("kafka", "display"), ["Первое", "Второе"]], [cell("nginx", "display"), ["Первое"]]]);
  assert.equal(marks.blocks.size, 0);
});

test("values Python could not read are marked where shown; a current end label and a catalog key are not doubts", () => {
  const facts = { records: [
    { id: "labs", kind: "employment", employer: known("Example Labs"),
      periods: [{ id: "p1", start: unresolved("весна 2021"), end: unresolved("н.в."), present: { ...known("н.в."), value: true } }] },
    { id: "python", kind: "technology", display: known("Python"), canonicalId: unresolved("python?") },
    { id: "kafka", kind: "technology", display: unresolved("Kafka?") },
    { id: "hidden", kind: "language", language: unresolved("Klingon") },
  ] };
  assert.deepEqual(sorted(remarkMarks(document, [], facts).cells),
    [[cell("kafka", "display"), [DOUBTFUL_VALUE]], [cell("labs", "period:p1:start"), [DOUBTFUL_VALUE]]]);
  const dated = { records: [{ id: "labs", kind: "employment",
    periods: [{ id: "p1", start: known("2021"), end: known("2025-03"), present: { ...known("н.в."), value: true } }] }] };
  assert.deepEqual(sorted(remarkMarks(document, [], dated).cells), [[cell("labs", "period:p1:end"), [DOUBTFUL_VALUE]]],
    "a dated end beside «present» is a doubt");
});

test("each fact group jumps to the section listing its records as items, else to one showing its fields", () => {
  const kinds = new Map([["candidate", "candidate"], ["python", "technology"], ["nginx", "technology"], ["kafka", "technology"],
    ["school", "education"], ["labs", "employment"], ["claim", "claim"]]);
  assert.deepEqual([...groupAnchors(document, kinds)].sort(), [["candidate", "name"], ["education", "education"], ["employment", "projects"],
    ["technology", "focus"]], "the header has no heading; job chips and claims inside a job do not count");
  // Without Focus rows the technologies are the tools line, not the chips of the first job.
  const oneColumn: OutlineDocument = { regions: document.regions.map(region => region.role === "sidebar" ? { ...region, blocks: [] } : region) };
  assert.equal(groupAnchors(oneColumn, kinds).get("technology"), "tools");
});

// The editor's node names; the plugin reads only the container IDs and the field cell IDs.
const schema = new Schema({ nodes: {
  doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
  blockContainer: { content: "paragraph blockGroup?", attrs: { id: { default: "block" } } },
  paragraph: { content: "inline*" }, templateField: { inline: true, group: "inline", content: "text*", attrs: { cellId: { default: "" } } },
  text: { group: "inline" },
} });

function decorations(doc: Node, marks: RemarkMarks | null) {
  const plugin = remarkMarksPlugin(() => marks), set = plugin.props.decorations?.call(plugin, EditorState.create({ schema, doc, plugins: [plugin] }));
  return set instanceof DecorationSet ? set.find() : [];
}

test("the plugin marks a field node and a block's own text, and nothing while the switch is off", () => {
  const field = schema.node("templateField", { cellId: "cell-1" }, schema.text("Nginx"));
  const nested = schema.node("blockContainer", { id: "child" }, schema.node("paragraph", null, schema.text("Nested")));
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    schema.node("blockContainer", { id: "line" }, schema.node("paragraph", null, [schema.text("Uses "), field])),
    schema.node("blockContainer", { id: "parent" }, [schema.node("paragraph", null, schema.text("Parent")),
      schema.node("blockGroup", null, nested)]),
  ]));
  const at = (name: string) => { let found = -1; doc.descendants((node, pos) => { if (found < 0 && node.isText && node.text === name) found = pos; }); return found; };
  const marks: RemarkMarks = { cells: new Map([["cell-1", ["Группа не определена."]]]), blocks: new Map([["parent", ["Под вопросом."]]]) };
  const found = decorations(doc, marks).map(value => [value.from, value.to]).sort((left, right) => (left[0] ?? 0) - (right[0] ?? 0));
  // The field node starts one step before its text; the parent's own text, not its nested child, is marked.
  assert.deepEqual(found, [[at("Nginx") - 1, at("Nginx") + "Nginx".length + 1], [at("Parent"), at("Parent") + "Parent".length]]);
  assert.deepEqual(decorations(doc, null), []);
  assert.deepEqual(decorations(doc, { cells: new Map(), blocks: new Map() }), []);
});
