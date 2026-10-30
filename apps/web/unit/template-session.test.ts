import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { renderToStaticMarkup } from "react-dom/server";
import { contentText, responseBlocks } from "../src/rich/v7-response";
import { knownErrorMessage } from "../src/errors/messages";
import { ProjectApiFailure } from "../src/rich/v7-connection";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { projectClient, harness, type Harness, type Traffic } from "./support/template-harness";
import { blockStart, paragraphs, refused, response, saved, scripted, select, settled, type, type Reply, type Wire } from "./support/scripted-project";

function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

const paperText = "By Shared title / Journal North.";
type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[]; traffic: Traffic[] };

async function opened(value: Harness): Promise<Opened> {
  const warnings: string[] = [];
  const traffic: Traffic[] = [];
  const connection = await projectClient(value, traffic);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = session.queue.template.durable;
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  // Headless editors install extension plugins only on mount; the session plugin is registered directly.
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor);
  await session.recoverDraft();
  return { session, editor, warnings, traffic };
}
function doc(editor: TemplateEditor): Node { return editor._tiptapEditor.state.doc; }
function start(editor: TemplateEditor, id: string): number {
  let found = -1;
  doc(editor).descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  assert.ok(found >= 0, id); return found;
}
function dispatch(editor: TemplateEditor, build: (tr: ReturnType<typeof editor._tiptapEditor.state.tr.insertText>) => void): void {
  const tr = editor._tiptapEditor.state.tr; build(tr); editor._tiptapEditor.view.dispatch(tr);
}
function caret(editor: TemplateEditor, pos: number): void { dispatch(editor, tr => { tr.setSelection(TextSelection.create(tr.doc, pos)); }); }
function editorTexts(editor: TemplateEditor): string[] {
  const result: string[] = [];
  doc(editor).descendants(node => {
    if (node.type.name === "blockContainer" && node.firstChild?.type.name === "paragraph") result.push(`${String(node.attrs["id"])}=${node.firstChild.textContent}`);
  });
  return result;
}
function canonicalTexts(session: TemplateEditorSession): string[] {
  const result: string[] = [];
  for (const [id, block] of responseBlocks(session.queue.template.durable)) {
    const group = block.groups[0];
    if (group?.kind === "content" && responseBlocks(session.queue.template.durable).get(id)) result.push(`${id}=${contentText(group.content)}`);
  }
  return result;
}

test("typing becomes one queued intent, saves, and re-projects canonical content after drain", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  try {
    const a = start(editor, "block-paper-a");
    dispatch(editor, tr => { tr.insertText("!", a + 16); });
    dispatch(editor, tr => { tr.insertText("?", a + 17); });
    assert.equal(session.queue.template.pending.length, 2);
    assert.equal(session.history.length, 1, "contiguous typing is one SessionHistory action");
    await session.flush();
    assert.ok(await session.reproject());
    assert.deepEqual(editorTexts(editor).filter(text => text.startsWith("block-paper")), canonicalTexts(session).filter(text => text.startsWith("block-paper")));
    assert.ok(canonicalTexts(session).includes("block-paper-a=By Shared title!? / Journal North."));
  } finally { session.close(); await value.close(); }
});

test("Undo and Redo run as server commands and re-project the editor", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  try {
    dispatch(editor, tr => { tr.insertText("!", start(editor, "block-paper-a") + 16); });
    await session.flush();
    await session.navigate("undo");
    assert.ok(canonicalTexts(session).includes(`block-paper-a=${paperText}`));
    assert.ok(editorTexts(editor).includes(`block-paper-a=${paperText}`));
    assert.equal(session.history.position, 0);
    await session.navigate("redo");
    assert.ok(editorTexts(editor).includes("block-paper-a=By Shared title! / Journal North."));
    assert.equal(session.history.position, 1);
    assert.equal(session.mode, "normal");
  } finally { session.close(); await value.close(); }
});

test("Enter splits through Python and local block IDs end at re-projection", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  try {
    caret(editor, start(editor, "block-paper-a") + 10);
    assert.equal(session.enter(), true);
    const local = editorTexts(editor).find(text => text.startsWith("local-"));
    assert.equal(local?.split("=")[1], " title / Journal North.");
    // Typing into the new local block is expressed before the split is saved.
    dispatch(editor, tr => { tr.insertText("X", editor._tiptapEditor.state.selection.from); });
    await session.flush();
    assert.ok(await session.reproject());
    const texts = editorTexts(editor);
    assert.ok(!texts.some(text => text.startsWith("local-")), "re-projection uses canonical block IDs");
    assert.ok(texts.includes("block-paper-a=By Shared"));
    assert.ok(texts.some(text => text.endsWith("=X title / Journal North.")));
    assert.deepEqual(texts.filter(text => !text.startsWith("block-paper-b")), canonicalTexts(session).filter(text => !text.startsWith("block-paper-b")));
    const selection = editor._tiptapEditor.state.selection.$from;
    assert.equal(selection.parent.textContent, "X title / Journal North.", "the caret follows its re-keyed block");
  } finally { session.close(); await value.close(); }
});

test("input the server cannot address is refused without touching the editor or the queue", async () => {
  const value = await harness();
  const { session, editor, warnings } = await opened(value);
  try {
    const before = doc(editor), a = start(editor, "block-paper-a");
    dispatch(editor, tr => { tr.setNodeMarkup(a - 1, undefined, { textAlignment: "center" }); });
    dispatch(editor, tr => { tr.delete(a + 5, start(editor, "block-paper-b") + 3); });
    assert.equal(doc(editor), before);
    assert.equal(session.queue.template.pending.length, 0);
    assert.equal(session.history.length, 0);
    assert.deepEqual(warnings, [knownErrorMessage("V7_INPUT_UNSUPPORTED"), knownErrorMessage("V7_INPUT_UNSUPPORTED")]);
  } finally { session.close(); await value.close(); }
});

test("a composition is saved once, as its final text, at composition end", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  try {
    const a = start(editor, "block-paper-a");
    session.compositionStart();
    dispatch(editor, tr => { tr.insertText("k", a + 16); });
    dispatch(editor, tr => { tr.insertText("カ", a + 16, a + 17); });
    assert.equal(session.queue.template.pending.length, 0, "composition updates stay in the editor");
    session.compositionEnd();
    assert.equal(session.queue.template.pending.length, 1);
    await session.flush();
    assert.ok(canonicalTexts(session).includes("block-paper-a=By Shared titleカ / Journal North."));
  } finally { session.close(); await value.close(); }
});

test("IME input beside repeated characters survives save, projection and reopen", async () => {
  const value = await harness();
  const { session, editor, warnings } = await opened(value);
  try {
    dispatch(editor, tr => { tr.insertText("ああ", start(editor, "block-paper-a")); });
    await session.flush(); await session.reproject();
    session.compositionStart();
    dispatch(editor, tr => { tr.insertText("あ", start(editor, "block-paper-a") + 1); });
    session.compositionEnd();
    await session.flush(); await session.reproject();
    const expected = `block-paper-a=あああ${paperText}`;
    assert.ok(canonicalTexts(session).includes(expected));
    assert.ok(editorTexts(editor).includes(expected));
    await session.navigateAway(); await session.resume();
    assert.ok(canonicalTexts(session).includes(expected));
    assert.equal(warnings.length, 0, warnings.join("\n"));
  } finally { session.close(); await value.close(); }
});

test("composition updates that cannot fold retain every already-applied change", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  try {
    session.compositionStart();
    dispatch(editor, tr => { tr.insertText("あ", start(editor, "block-paper-a")); });
    dispatch(editor, tr => { tr.insertText("い", start(editor, "block-paper-b") + 2); });
    session.compositionEnd();
    assert.equal(session.queue.template.pending.length, 2);
    const visible = editorTexts(editor).filter(text => text.startsWith("block-paper"));
    await session.flush(); await session.reproject();
    assert.deepEqual(editorTexts(editor).filter(text => text.startsWith("block-paper")), visible);
  } finally { session.close(); await value.close(); }
});

test("a definitive rejection keeps all input; retry re-expresses it from canonical text and saves", async () => {
  const value = await harness();
  const { session, editor, warnings } = await opened(value);
  try {
    const api = session.connection, prepare = api.edit.bind(api);
    let reject = true;
    api.edit = (...args) => {
      if (reject) { reject = false; return Promise.reject(new ProjectApiFailure("V7_INPUT_REJECTED", 422)); }
      return prepare(...args);
    };
    const a = start(editor, "block-paper-a");
    dispatch(editor, tr => { tr.insertText("!", a + 16); });
    await assert.rejects(session.flush(), /V7_INPUT_REJECTED/);
    assert.equal(session.queue.template.state.kind, "rejected");
    // Later input buffers behind the block; nothing is lost or resent.
    dispatch(editor, tr => { tr.insertText("?", a + 17); });
    assert.equal(session.queue.template.pending.length, 2);
    assert.ok(warnings.includes(knownErrorMessage("V7_INPUT_REJECTED") ?? ""));
    session.retry();
    assert.equal(session.queue.template.state.kind, "ready");
    assert.equal(session.queue.template.pending.length, 1, "one correction per affected container");
    await session.flush();
    assert.ok(canonicalTexts(session).includes("block-paper-a=By Shared title!? / Journal North."));
    assert.ok(await session.reproject());
    assert.ok(editorTexts(editor).includes("block-paper-a=By Shared title!? / Journal North."));
  } finally { session.close(); await value.close(); }
});

test("leaving drains and detaches; resume reattaches the same session and input saves again", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  try {
    dispatch(editor, tr => { tr.insertText("!", start(editor, "block-paper-a") + 16); });
    // The caret follows typed text; re-projections keep it after "!" although "!" becomes its own field fragment.
    caret(editor, start(editor, "block-paper-a") + 17);
    await session.navigateAway();
    assert.equal(session.mode, "detached");
    assert.ok(canonicalTexts(session).includes("block-paper-a=By Shared title! / Journal North."), "navigation drained pending input");
    await session.resume();
    assert.equal(session.mode, "normal");
    dispatch(editor, tr => { tr.insertText("?", tr.selection.from); });
    await session.flush();
    assert.ok(canonicalTexts(session).includes("block-paper-a=By Shared title!? / Journal North."));
  } finally { session.close(); await value.close(); }
});

test("an outside canonical advance (export record) is adopted; later saves and detach still succeed", async () => {
  const value = await harness();
  const { session, editor } = await opened(value);
  const advance = async () => { const reply = await fetch(`${value.origin}/harness/advance`, { method: "POST" }); assert.equal(reply.status, 200); };
  try {
    dispatch(editor, tr => { tr.insertText("!", start(editor, "block-paper-a") + 16); });
    caret(editor, start(editor, "block-paper-a") + 17);
    await session.flush();
    await advance();
    // The export path refreshes explicitly; the queue takes the advance as its base while idle.
    await session.refresh();
    dispatch(editor, tr => { tr.insertText("?", tr.selection.from); });
    await session.flush();
    assert.ok(canonicalTexts(session).includes("block-paper-a=By Shared title!? / Journal North."));
    // Without a refresh, a stale detach header is re-read once while this writer still owns the session.
    await advance();
    await session.navigateAway();
    assert.equal(session.mode, "detached");
  } finally { session.close(); await value.close(); }
});

/** One reply edits block a and also moves block b, as a second occurrence of one fact does; input on b then conflicts. */
async function conflicted() {
  let revision = 1;
  const sent: Wire[] = [];
  const opened = await scripted(response([{ id: "a", text: "aaa" }, { id: "b", text: "bbb" }], 1), (_path, request) => {
    if (!request) return refused("REQUEST_FAILED", 500);
    sent.push(request);
    revision++;
    return saved(response(sent.length === 1 ? [{ id: "a", text: "aaaX" }, { id: "b", text: "moved" }] : [{ id: "a", text: "aaaX" }, { id: "b", text: "bbbY" }], revision), request.clientMutationId);
  });
  type(opened.editor, "X", blockStart(opened.editor, "a") + 3);
  type(opened.editor, "Y", blockStart(opened.editor, "b") + 3);
  await assert.rejects(opened.session.flush(), /V7_INPUT_CONFLICT/);
  assert.equal(opened.session.queue.template.state.kind, "conflict");
  return { ...opened, sent };
}

test("keeping my text ends a text conflict: the editor's text is saved and leaving works again", async () => {
  const { session, editor, sent } = await conflicted();
  try {
    session.keepEditorText();
    assert.equal(session.queue.template.state.kind, "ready");
    await session.flush();
    await settled();
    assert.equal(sent.at(-1)?.operation.kind, "replace_text");
    assert.deepEqual(paragraphs(editor), ["a=aaaX", "b=bbbY"]);
    await session.navigateAway();
    assert.equal(session.mode, "detached");
  } finally { session.close(); }
});

test("discarding ends a text conflict: the saved text is shown and leaving works again", async () => {
  const { session, editor, sent } = await conflicted();
  try {
    session.discard();
    assert.equal(session.queue.template.state.kind, "ready");
    assert.deepEqual(paragraphs(editor), ["a=aaaX", "b=moved"]);
    assert.equal(session.queue.template.pending.length, 0);
    await session.navigateAway();
    assert.equal(session.mode, "detached");
    assert.equal(sent.length, 1, "nothing more was sent");
  } finally { session.close(); }
});

test("the block notice offers both choices and each button calls its own action", () => {
  const notice = BlockedInputNotice({ text: "Текст", keep: () => {}, discard: () => {} });
  const html = renderToStaticMarkup(notice);
  assert.ok(html.includes("Сохранить мой текст") && html.includes("Вернуть сохранённый текст"));
  assert.ok(html.includes("Текст"));
});

test("retry after a refused split shows the saved text and names it instead of deleting the right half", async () => {
  const sent: Wire[] = [];
  const { session, editor, warnings } = await scripted(response([{ id: "a", text: "left right" }], 1), (_path, request) => {
    if (request) sent.push(request);
    return refused("PROJECT_TOO_LARGE", 413);
  });
  try {
    select(editor, blockStart(editor, "a") + 5);
    session.enter();
    assert.ok(paragraphs(editor).some(value => value.endsWith("=right")));
    await assert.rejects(session.flush());
    session.keepEditorText();
    await settled();
    assert.equal(session.queue.template.state.kind, "ready");
    assert.deepEqual(paragraphs(editor), ["a=left right"]);
    assert.deepEqual(sent.map(value => value.operation.kind), ["split_block"], "no text difference is sent");
    assert.ok(warnings.at(-1)?.startsWith(errorMessage("V7_CHANGE_NOT_SAVED")) && warnings.at(-1)?.includes("left right"));
    await session.navigateAway();
  } finally { session.close(); }
});

test("retry after a refused merge shows both saved blocks and names their text", async () => {
  const { session, editor, warnings } = await scripted(response([{ id: "a", text: "one" }, { id: "b", text: "two" }], 1), () => refused("V7_INPUT_REJECTED"));
  try {
    select(editor, blockStart(editor, "b"));
    assert.equal(session.join("backward"), true);
    assert.deepEqual(paragraphs(editor), ["a=onetwo"]);
    await assert.rejects(session.flush());
    session.keepEditorText();
    await settled();
    assert.equal(session.queue.template.state.kind, "ready");
    assert.deepEqual(paragraphs(editor), ["a=one", "b=two"]);
    assert.ok(warnings.at(-1)?.includes("one") && warnings.at(-1)?.includes("two"));
  } finally { session.close(); }
});

test("retry after refused marks shows the saved style and says the change was not saved", async () => {
  const { session, editor, warnings } = await scripted(response([{ id: "a", text: "plain" }], 1), () => refused("V7_INPUT_REJECTED"));
  const bold = () => { let found = false; doc(editor).descendants(node => { if (node.marks.some(mark => mark.type.name === "bold")) found = true; }); return found; };
  try {
    const a = blockStart(editor, "a");
    select(editor, a, a + 5);
    editor.toggleStyles({ bold: true });
    assert.ok(bold());
    await assert.rejects(session.flush());
    session.keepEditorText();
    await settled();
    assert.equal(session.queue.template.state.kind, "ready");
    assert.equal(bold(), false, "the unsaved style left the editor");
    assert.ok(warnings.at(-1)?.startsWith(errorMessage("V7_CHANGE_NOT_SAVED")) && warnings.at(-1)?.includes("plain"));
  } finally { session.close(); }
});

test("retry saves corrected text and still reports the marks beside it", async () => {
  const sent: Wire[] = [];
  let refusing = true;
  const { session, editor, warnings } = await scripted(response([{ id: "a", text: "plain" }, { id: "b", text: "other" }], 1), (_path, request) => {
    if (!request) return refused("REQUEST_FAILED", 500);
    sent.push(request);
    if (refusing) { refusing = false; return refused("V7_INPUT_REJECTED"); }
    return saved(response([{ id: "a", text: "plain" }, { id: "b", text: "otherZ" }], 2), request.clientMutationId);
  });
  try {
    const a = blockStart(editor, "a");
    select(editor, a, a + 5);
    editor.toggleStyles({ bold: true });
    type(editor, "Z", blockStart(editor, "b") + 5);
    await assert.rejects(session.flush());
    session.keepEditorText();
    assert.ok(warnings.at(-1)?.startsWith(errorMessage("V7_CHANGE_NOT_SAVED")));
    await session.flush();
    await settled();
    assert.deepEqual(sent.map(value => value.operation.kind), ["set_marks", "replace_text"]);
    assert.deepEqual(paragraphs(editor), ["a=plain", "b=otherZ"]);
  } finally { session.close(); }
});

test("a late read in refresh does not take a newer edit back", async () => {
  let release = () => {}, reading = false;
  const late = response([{ id: "a", text: "aaa" }], 1);
  const { session, editor } = await scripted(late, async (_path, request) => {
    if (request) return saved(response([{ id: "a", text: "aaaZ" }], 2), request.clientMutationId);
    if (!reading) return { status: 200, body: late };
    await new Promise<void>(resolve => { release = resolve; });
    return { status: 200, body: late };
  });
  try {
    reading = true;
    const refreshing = session.refresh();
    await settled();
    type(editor, "Z", blockStart(editor, "a") + 3);
    await session.flush();
    await settled();
    assert.equal(session.queue.template.durable.workspace.projectRevision, 2);
    release();
    await refreshing;
    assert.equal(session.queue.template.durable.workspace.projectRevision, 2);
    assert.deepEqual(paragraphs(editor), ["a=aaaZ"]);
  } finally { session.close(); }
});
