import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { templateSchema } from "../src/rich/template-schema";
import { textPosition } from "../src/rich/v7-extraction";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { RewriteRequests, type RewriteActivity, type RewriteStage } from "../src/rich/rewrite-progress";
import { projectClient, harness, type Harness, type Traffic } from "./support/template-harness";
import { blockStart, response, saved, scripted, select as selectRange, settled, type, type Reply, type Wire } from "./support/scripted-project";

function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

const TASK = "Implemented queue processing.";
const RESULT = "Our team reduced median latency from 800 ms to 500 ms.";
type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[]; reopen: () => Promise<Opened> };

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
  // Reopen: a clean detach, then a new writer session reads only the durable record.
  const reopen = async () => { await session.navigateAway(); session.close(); return opened(value); };
  return { session, editor, warnings, reopen };
}

type Part = Record<string, unknown>;
type Shown = { id: string; parent: string; type: string; text: string; parts: Part[] };
async function shown(session: TemplateEditorSession): Promise<{ response: TemplateProjectResponseV1; blocks: Shown[] }> {
  const response = session.queue.template.durable, project = response?.workspace.project;
  assert.ok(response && project);
  const blocks: Shown[] = [];
  const visit = (block: Record<string, unknown>, parent: string) => {
    const content = Array.isArray(block["content"]) ? block["content"] as Part[] : [];
    blocks.push({ id: String(block["id"]), parent, type: String(block["type"]), parts: content,
      text: content.map(part => typeof part["text"] === "string" ? part["text"] : "").join("") });
    for (const child of block["children"] as Record<string, unknown>[]) visit(child, String(block["id"]));
  };
  for (const region of project.document.regions) for (const block of region.blocks) visit(block as unknown as Record<string, unknown>, region.id);
  return { response, blocks };
}
function fields(block: Shown): { cellId: unknown; occurrenceId: unknown }[] {
  return block.parts.filter(part => "cellId" in part).map(part => ({ cellId: part["cellId"], occurrenceId: part["occurrenceId"] }));
}
function unique(values: { cellId: unknown; occurrenceId: unknown }[]): { cellId: unknown; occurrenceId: unknown }[] {
  return [...new Map(values.map(value => [JSON.stringify(value), value])).values()];
}
function relations(response: TemplateProjectResponseV1): Map<string, string> {
  const facts = response.workspace.project?.facts;
  assert.ok(facts);
  return new Map(facts.relations.filter(value => value.active && value.kind === "owned_by").map(value => [value.subjectId, value.targetId]));
}
function factsWire(response: TemplateProjectResponseV1): string { return JSON.stringify(response.workspace.project?.facts.records); }

function doc(editor: TemplateEditor): Node { return editor._tiptapEditor.state.doc; }
function textStart(editor: TemplateEditor, id: string): number {
  let found = -1;
  doc(editor).descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  assert.ok(found >= 0, id); return found;
}
/** The editor position after `offset` characters of a block's text, inside field nodes as typing would be. */
function at(editor: TemplateEditor, id: string, offset: number): number {
  const value = textPosition(doc(editor), { container: { blockId: id, kind: "content", cellId: null }, offset });
  assert.ok(value !== null, id); return value;
}
function select(editor: TemplateEditor, anchor: number, head = anchor): void {
  const tr = editor._tiptapEditor.state.tr; tr.setSelection(TextSelection.create(tr.doc, anchor, head)); editor._tiptapEditor.view.dispatch(tr);
}
/** From the first block's text start to the next sibling's text start: whole blocks, as Shift+Down selects them. */
function selectWhole(editor: TemplateEditor, first: string, next: string): void { select(editor, textStart(editor, first), textStart(editor, next)); }

async function rewriteCalls(value: Harness): Promise<{ instruction: string; source: string }[]> {
  const response = await fetch(value.origin + "/harness/rewrites");
  const calls: unknown = (await response.json() as { calls: unknown }).calls;
  assert.ok(Array.isArray(calls));
  return calls as { instruction: string; source: string }[];
}

test("E05: a preview changes nothing; Apply replaces exactly the shown text once; one Undo restores it", async () => {
  const value = await harness("e04");
  const { session, editor, warnings } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const [first, second] = blocks.filter(block => block.text === TASK);
    assert.ok(first && second);
    const before = JSON.stringify(response.workspace.project), length = session.history.length;
    const identities = (list: Shown[]) => JSON.stringify(list.map(block => [block.id, block.text, fields(block)]));
    const shape = identities(blocks);
    select(editor, at(editor, second.id, 0), at(editor, second.id, "Implemented queue".length));
    const preview = await session.rewritePreview("clearer");
    assert.equal(preview.source, "Implemented queue");
    assert.equal(preview.text, "Implemented queue (revised)");
    ({ response } = await shown(session));
    assert.equal(JSON.stringify(response.workspace.project), before, "no document or fact change before Apply");
    assert.equal(session.history.length, length, "no history action before Apply");
    assert.deepEqual((await rewriteCalls(value)).map(call => call.source), ["Implemented queue"]);

    // The user adjusts the shown text; exactly that text applies.
    await session.applyRewrite(preview, "Built the queue");
    ({ response, blocks } = await shown(session));
    assert.equal(blocks.find(block => block.id === second.id)?.text, "Built the queue processing.");
    assert.equal(blocks.find(block => block.id === first.id)?.text, TASK, "unrelated content unchanged");
    const claims = response.workspace.project?.facts.records.filter(record => record.kind === "claim")
      .map(record => (record as unknown as { value: { rawText: string } }).value.rawText).sort();
    assert.deepEqual(claims, [RESULT, TASK, "Built the queue processing."].sort());
    assert.equal(session.history.length, length + 1, "one action");
    assert.equal((await rewriteCalls(value)).length, 1, "Apply makes no generation call");
    await session.navigate("undo");
    ({ response, blocks } = await shown(session));
    // Revision counters move forward; text and identities return exactly.
    assert.equal(identities(blocks), shape, "one Undo restores the document");
    await session.navigate("redo");
    ({ blocks } = await shown(session));
    assert.equal(blocks.find(block => block.id === second.id)?.text, "Built the queue processing.");
    assert.equal(warnings.length, 0, warnings.join("\n"));
  } finally { session.close(); await value.close(); }
});

test("E05: a preview made stale by later typing conflicts on Apply and changes nothing else", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    const { blocks } = await shown(session);
    const role = blocks.find(block => block.text === "Role: Backend Engineer");
    assert.ok(role);
    select(editor, at(editor, role.id, "Role: ".length), at(editor, role.id, role.text.length));
    const preview = await session.rewritePreview("upper");
    assert.equal(preview.text, "BACKEND ENGINEER");
    const end = at(editor, role.id, role.text.length);
    select(editor, end);
    editor._tiptapEditor.view.dispatch(editor._tiptapEditor.state.tr.insertText("!", end));
    await session.flush();
    await assert.rejects(session.applyRewrite(preview), /V7_INPUT_CONFLICT/);
    const after = (await shown(session)).blocks.find(block => block.id === role.id);
    assert.equal(after?.text, "Role: Backend Engineer!", "only the later typing is saved");
    assert.equal(session.queue.template.pending.length, 0, "the refused replacement is dropped");
  } finally { session.close(); await value.close(); }
});

test("E05: cancelling a running preview and a failed generation leave the document and history unchanged", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    const { response, blocks } = await shown(session);
    const target = blocks.find(block => block.text === "2024–present");
    assert.ok(target);
    const before = JSON.stringify(response.workspace.project), length = session.history.length;
    select(editor, at(editor, target.id, 0), at(editor, target.id, 4));
    const running = session.rewritePreview("hold", "held-request");
    // Attach before cancel: the preview can reject as soon as the server answers, before the assertion awaits it.
    const settled = running.then(result => ({ failed: false as const, result }), (error: unknown) => ({ failed: true as const, error }));
    for (let attempt = 0; attempt < 100 && (await rewriteCalls(value)).length === 0; attempt++) await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(await session.cancelRewrite("held-request"), true);
    const outcome = await settled;
    assert.equal(outcome.failed, true);
    assert.match(String(outcome.failed ? outcome.error : ""), /CANCELLED/);
    await assert.rejects(session.rewritePreview("fail"), /MODEL_DENIED/);
    assert.equal(JSON.stringify((await shown(session)).response.workspace.project), before);
    assert.equal(session.history.length, length);
  } finally { session.close(); await value.close(); }
});

function requests(cancel: (requestId: string) => Promise<boolean> = () => Promise.resolve(true)) {
  const replies: { resolve: (text: string) => void; reject: (error: Error) => void }[] = [], stages: ((stage: RewriteStage) => void)[] = [];
  const activity: (RewriteActivity | null)[] = [], done: string[] = [], failed: string[] = [], cancelled: string[] = [], cancelFailed: unknown[] = [];
  const runs = new RewriteRequests<string>({
    preview: (_id, stage) => { stages.push(stage); return new Promise((resolve, reject) => { replies.push({ resolve, reject }); }); },
    cancel: id => { cancelled.push(id); return cancel(id); }, activity: value => activity.push(value), done: value => done.push(value),
    failed: value => failed.push(value), cancelFailed: value => cancelFailed.push(value),
  });
  return { runs, replies, stages, activity, done, failed, cancelled, cancelFailed };
}

test("a reply of a superseded rewrite never fills the panel", async () => {
  const { runs, replies, activity, done, failed, cancelled } = requests();
  const first = runs.submit();
  const id = activity[0]?.actionId;
  assert.equal(activity[0]?.stage, "saving");
  runs.supersede();
  assert.equal(activity.at(-1), null);
  assert.deepEqual(cancelled, [id]);
  assert.equal(runs.running, false);
  replies[0]?.resolve("old preview");
  await first;
  const second = runs.submit();
  replies[1]?.reject(new Error("CANCELLED"));
  await second;
  assert.deepEqual(done, []);
  assert.deepEqual(failed, ["CANCELLED"], "the current request still reports");
});

test("a current reply fills the panel and ends the activity", async () => {
  const { runs, replies, activity, done } = requests();
  const run = runs.submit();
  replies[0]?.resolve("new text");
  await run;
  assert.deepEqual(done, ["new text"]);
  assert.equal(activity.at(-1), null);
});

test("cancel shows its own stage, later stages do not replace it, and the reply ends it", async () => {
  const { runs, replies, stages, activity, failed } = requests();
  const run = runs.submit(), id = activity[0]?.actionId ?? "";
  stages[0]?.("running");
  await runs.cancel(id);
  assert.equal(activity.at(-1)?.stage, "cancelling");
  stages[0]?.("running");
  assert.equal(activity.at(-1)?.stage, "cancelling");
  replies[0]?.reject(new Error("CANCELLED"));
  await run;
  assert.deepEqual(failed, ["CANCELLED"]);
  assert.equal(activity.at(-1), null);
});

test("a cancel that fails or is refused says so and the stage returns", async () => {
  for (const cancel of [() => Promise.reject(new Error("REQUEST_FAILED")), () => Promise.resolve(false)]) {
    const { runs, replies, stages, activity, cancelFailed } = requests(cancel);
    const run = runs.submit(), id = activity[0]?.actionId ?? "";
    stages[0]?.("queued");
    await runs.cancel(id);
    assert.equal(activity.at(-1)?.stage, "queued");
    assert.equal(cancelFailed.length, 1);
    replies[0]?.resolve("text");
    await run;
  }
});

type PreviewBody = { requestId: string; snapshot: unknown; range: unknown };
function previewReply(request: Wire | null, source: string, text: string): Reply {
  const body = request?.body as PreviewBody | undefined;
  return { status: 200, body: { schemaVersion: 1, requestId: body?.requestId, snapshot: body?.snapshot, range: body?.range, source, text } };
}
const rewriteTask = (stage: string) => ({ status: 200, body: { schemaVersion: 1, tasks: [{ kind: "rewrite", state: "running", stage, detail: { requestId: "request-1" } },
  { kind: "rewrite", state: "running", stage: "generating", detail: { requestId: "other" } }] } });

test("a preview walks through the save, the send and the server's real stages", async () => {
  const seen: string[] = [];
  let generating = () => {}, reads = 0;
  const running = new Promise<void>(resolve => { generating = resolve; });
  const { session, editor } = await scripted(response([{ id: "a", text: "source" }], 1), async (path, request) => {
    if (path.endsWith("/tasks")) return rewriteTask(++reads === 1 ? "queued" : "generating");
    await running;
    return previewReply(request, "source", "new");
  });
  try {
    const a = blockStart(editor, "a");
    selectRange(editor, a, a + 6);
    const preview = await session.rewritePreview("Make clearer", "request-1", stage => { seen.push(stage); if (stage === "running") generating(); });
    assert.equal(preview.text, "new");
    assert.deepEqual(seen.slice(0, 4), ["saving", "starting", "queued", "running"]);
  } finally { session.close(); }
});

test("a cancel during the save stops the preview before it is sent", async () => {
  const paths: string[] = [];
  let release = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  const { session, editor } = await scripted(response([{ id: "a", text: "source" }, { id: "b", text: "other" }], 1), async (path, request) => {
    paths.push(path);
    if (path.endsWith("/rewrite/cancel")) return { status: 200, body: { cancelled: true } };
    await held;
    return saved(response([{ id: "a", text: "source" }, { id: "b", text: "otherZ" }], 2), request?.clientMutationId ?? "");
  });
  try {
    type(editor, "Z", blockStart(editor, "b") + 5);
    const a = blockStart(editor, "a");
    selectRange(editor, a, a + 6);
    const preview = session.rewritePreview("Make clearer", "request-1");
    await settled();
    assert.equal(await session.cancelRewrite("request-1"), true);
    release();
    await assert.rejects(preview, (error: Error) => error.message === "CANCELLED");
    assert.ok(!paths.some(path => path.endsWith("/rewrite/preview")), "the model is never asked");
  } finally { session.close(); }
});
