import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { errorMessage } from "../src/errors/messages";
import { templateSchema } from "../src/rich/template-schema";
import { textPosition } from "../src/rich/v7-extraction";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor, type TemplateSessionPort } from "../src/rich/v7-session";
import { RefusalNotice } from "../src/workbench/editor/RefusalNotice";
import { refusalDue, refusalPlace } from "../src/workbench/editor/refusal-notice";
import { projectClient, harness } from "./support/template-harness";

// F4 of the tester feedback of 2026-11-23: a refused input is said at the place of work.
function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

test("the same refusal text does not show again within 3 s; another text shows at once", () => {
  assert.equal(refusalDue(null, "a", 1000), true);
  const last = { text: "a", at: 1000 };
  assert.equal(refusalDue(last, "a", 3999), false);
  assert.equal(refusalDue(last, "a", 4000), true);
  assert.equal(refusalDue(last, "b", 1001), true);
});

test("the message stands above the first line, inside the window, and never on the «Изменить текст» button", () => {
  const window = { width: 1000, height: 800 }, size = { width: 300, height: 30 };
  assert.deepEqual(refusalPlace({ left: 100, top: 400, right: 400, bottom: 418 }, size, window), { left: 100, top: 364 });
  assert.deepEqual(refusalPlace({ left: 900, top: 400, right: 990, bottom: 418 }, size, window), { left: 692, top: 364 });
  // The button flipped above the selection: the message goes above the button.
  const button = { left: 100, top: 360, right: 240, bottom: 392 };
  assert.deepEqual(refusalPlace({ left: 100, top: 400, right: 400, bottom: 418 }, size, window, button), { left: 100, top: 324 });
  // No room above the first line of the window: below the line.
  assert.deepEqual(refusalPlace({ left: 100, top: 10, right: 400, bottom: 28 }, size, window), { left: 100, top: 34 });
});

test("the message is a status with the catalog text", () => {
  const html = renderToStaticMarkup(createElement(RefusalNotice, { refusal: { id: 1, text: errorMessage("TECHNOLOGY_IN_FACTS"),
    line: { left: 0, top: 0, right: 0, bottom: 0 } }, done: () => {} }));
  assert.match(html, /role="status"/u);
  assert.ok(html.includes(errorMessage("TECHNOLOGY_IN_FACTS")));
});

for (const given of [true, false]) {
  test(`the session port: a refused paste into a technology line goes to ${given ? "the callback, not the notice area" : "the notice area"}`, async () => {
    const value = await harness("e04");
    const warnings: string[] = [], refused: string[] = [];
    const port: TemplateSessionPort = { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {},
      ...given ? { refused: (text: string) => { refused.push(text); } } : {} };
    const connection = await projectClient(value);
    const session = new TemplateEditorSession(connection, port, 60_000);
    try {
      const project = session.queue.template.durable.workspace.project;
      assert.ok(project);
      const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(project.document) });
      editor._tiptapEditor.registerPlugin(session.plugin);
      session.bind(editor, project.document);
      await session.recoverDraft();
      let python = "";
      editor._tiptapEditor.state.doc.descendants(node => {
        if (node.type.name === "blockContainer" && node.firstChild?.textContent === "Python") python = String(node.attrs["id"]);
        return !python;
      });
      const pos = textPosition(editor._tiptapEditor.state.doc, { container: { blockId: python, kind: "content", cellId: null }, offset: 2 });
      assert.ok(pos !== null);
      const tr = editor._tiptapEditor.state.tr;
      editor._tiptapEditor.view.dispatch(tr.setSelection(TextSelection.create(tr.doc, pos)));
      await session.pasteFrom(null, "Go");
      const text = errorMessage("TECHNOLOGY_IN_FACTS");
      assert.deepEqual(given ? refused : warnings, [text]);
      assert.deepEqual(given ? warnings : refused, []);
    } finally { session.close(); await value.close(); }
  });
}
