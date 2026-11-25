import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { capabilities, message, settings, view } from "./support/assistant";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { Transcript } = await import("../src/workbench/assistant/Transcript");
const { Composer } = await import("../src/workbench/assistant/Composer");
const { resumeScope } = await import("../src/workbench/assistant/scope");

const composer = { view: view({ settings, capabilities, flags: { allowEdits: false, allowWeb: true }, run: null }), captured: null, active: false, applying: false,
  title: "Две колонки", draft: () => {}, flags: () => {}, model: () => {}, send: () => {}, stop: () => {}, clear: () => {}, settings: () => {} };

test("the resume transcript shows no attachment line under a message", () => {
  const shown = view({ messages: [message("user", "Проверь", "run-1"), message("assistant", "Готово", "run-1")], run: null });
  const resume = renderToStaticMarkup(createElement(Transcript, { view: shown, active: false, resource: () => {}, focus: () => false, draft: () => {} }));
  assert.ok(!resume.includes("chat-message-attachment"));
});

test("an empty chat asks its question and offers no ready prompts (D139)", () => {
  const empty = view({ messages: [], run: null });
  for (const [scope, title, question] of [[resumeScope, "Чат по резюме", "в резюме? Напишите вопрос ниже."]] as const) {
    const html = renderToStaticMarkup(createElement(Transcript, { view: empty, active: false, resource: () => {}, focus: () => false, draft: () => {}, scope }));
    const part = /<div class="chat-empty">(.*?)<\/div>/u.exec(html)?.[1] ?? "";
    assert.ok(part.includes(title) && part.includes(question), part);
    assert.ok(!part.includes("<button"), "no ready prompts");
  }
});

test("the resume composer keeps its edits switch and the whole-project context, and lists no template command", () => {
  const resume = renderToStaticMarkup(createElement(Composer, { ...composer, scope: resumeScope, view: { ...composer.view, draft: "/" } }));
  assert.ok(resume.includes("Разрешить правки") && resume.includes('id="chat-input"') && resume.includes("Весь проект"));
  assert.ok(!resume.includes("/design-template"));
});
