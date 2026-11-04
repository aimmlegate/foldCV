import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AgentApiFailure } from "../src/assistant/api";
import { AssistantRuns } from "../src/assistant/controller";
import { sampleSpent, TemplateAssistantApi, type TemplateFields } from "../src/assistant/template";
import type { Fetcher } from "../src/rich/v7-connection";
import { capabilities, message, run, settings, view } from "./support/assistant";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { Transcript } = await import("../src/workbench/assistant/Transcript");
const { Composer } = await import("../src/workbench/assistant/Composer");
const { resumeScope, templateScope } = await import("../src/workbench/assistant/scope");

const composer = { view: view({ settings, capabilities, flags: { allowEdits: false, allowWeb: true }, run: null }), captured: null, active: false, applying: false,
  title: "Две колонки", draft: () => {}, flags: () => {}, model: () => {}, send: () => {}, stop: () => {}, clear: () => {}, settings: () => {} };

test("the sent message names its sample; other messages and the resume transcript show none", () => {
  const shown = view({ messages: [message("user", "Сделай по образцу", "run-1"), message("assistant", "Готово", "run-1"), message("user", "Ещё", "run-2")], run: null });
  const html = renderToStaticMarkup(createElement(Transcript, { view: shown, active: false, resource: () => {}, focus: () => false, draft: () => {},
    scope: templateScope, attachment: (runId: string) => runId === "run-1" ? "Образец.docx" : null }));
  assert.equal(html.match(/chat-message-attachment/gu)?.length, 1);
  assert.ok(html.includes("Образец.docx"));
  const resume = renderToStaticMarkup(createElement(Transcript, { view: shown, active: false, resource: () => {}, focus: () => false, draft: () => {} }));
  assert.ok(!resume.includes("chat-message-attachment"));
});

test("an empty chat asks its question and offers no ready prompts, in both drawers (D139)", () => {
  const empty = view({ messages: [], run: null });
  for (const [scope, title, question] of [[templateScope, "Чат по шаблону", "в шаблоне? Напишите вопрос ниже."],
    [resumeScope, "Чат по резюме", "в резюме? Напишите вопрос ниже."]] as const) {
    const html = renderToStaticMarkup(createElement(Transcript, { view: empty, active: false, resource: () => {}, focus: () => false, draft: () => {}, scope }));
    const part = /<div class="chat-empty">(.*?)<\/div>/u.exec(html)?.[1] ?? "";
    assert.ok(part.includes(title) && part.includes(question), part);
    assert.ok(!part.includes("<button"), "no ready prompts");
  }
});

test("the templates composer shows its own context and no edits switch; the resume composer keeps both", () => {
  const html = renderToStaticMarkup(createElement(Composer, { ...composer, scope: templateScope,
    context: createElement("span", { className: "chat-attachment" }, "Образец.docx") }));
  assert.ok(html.includes("Образец.docx") && html.includes('id="template-chat-input"'));
  assert.ok(!html.includes("Разрешить правки") && !html.includes("Весь проект"));
  const resume = renderToStaticMarkup(createElement(Composer, { ...composer, scope: resumeScope }));
  assert.ok(resume.includes("Разрешить правки") && resume.includes('id="chat-input"') && resume.includes("Весь проект"));
});

test("a run with a replaced sample is refused before it starts and the panel shows the code's message", async () => {
  const conversation = { id: "conversation-1", title: "", createdAt: "2026-11-03T12:00:00+00:00", updatedAt: "2026-11-03T12:00:00+00:00" };
  const fetcher: Fetcher = input => {
    const url = String(input), reply = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }));
    if (url === "/v1/settings/assistant") return reply(settings);
    if (url.endsWith("/capabilities")) return reply(capabilities);
    if (url.endsWith("/conversations")) return reply({ items: [conversation] });
    if (url.endsWith("/messages")) return reply({ conversation, messages: [], sources: [], findings: [], runs: [], files: [] });
    if (url.endsWith("/runs")) return reply({ error: { code: "SAMPLE_NOT_FOUND" } }, 404);
    return reply({ items: [] });
  };
  const runs = new AssistantRuns<TemplateFields>(new TemplateAssistantApi(fetcher), { applyProposal: () => Promise.reject(new AgentApiFailure("REQUEST_FAILED")) }, () => {}, 1);
  try {
    await runs.init(); runs.draft("По образцу");
    await runs.sendWith(() => Promise.resolve({ templateId: "generic", assetsFrom: "generic", text: "x", textHash: "h", sampleId: "gone" }));
    assert.equal(runs.view.error, "SAMPLE_NOT_FOUND");
    assert.equal(runs.view.pendingSend, false, "a refusal is final, not a retry");
    assert.equal(runs.view.run, null);
    assert.equal(runs.view.draft, "По образцу", "the message stays for another try");
    assert.equal(sampleSpent(null, runs.view), true, "a sample the service lost leaves the composer");
  } finally { runs.close(); }
});

test("a sample goes with one run: it leaves after a started run, and stays after a lost reply or no send", async () => {
  const conversation = { id: "conversation-1", title: "", createdAt: "2026-11-03T12:00:00+00:00", updatedAt: "2026-11-03T12:00:00+00:00" };
  for (const [answer, spent] of [[() => reply(run("completed", "run-2"), 201), true], [() => reply({ error: { code: "AGENT_UNAVAILABLE" } }, 503), false]] as const) {
    const fetcher: Fetcher = input => {
      const url = String(input);
      if (url === "/v1/settings/assistant") return reply(settings);
      if (url.endsWith("/capabilities")) return reply(capabilities);
      if (url.endsWith("/conversations")) return reply({ items: [conversation] });
      if (url.endsWith("/messages")) return reply({ conversation, messages: [], sources: [], findings: [], runs: [], files: [] });
      if (url.endsWith("/runs")) return answer();
      return reply({ items: [] });
    };
    const runs = new AssistantRuns<TemplateFields>(new TemplateAssistantApi(fetcher), { applyProposal: () => Promise.reject(new AgentApiFailure("REQUEST_FAILED")) }, () => {}, 1);
    try {
      await runs.init(); runs.draft("По образцу");
      await runs.sendWith(() => Promise.resolve({ templateId: "generic", assetsFrom: "generic", text: "x", textHash: "h", sampleId: "sample-1" }));
      assert.equal(sampleSpent(null, runs.view), spent);
    } finally { runs.close(); }
  }
  assert.equal(sampleSpent("run-1", { run: run("running", "run-1"), error: null }), false, "Send did nothing while a run was shown");
  // The run started, so the service took the sample, even when the read after it failed; no run, no sample taken.
  assert.equal(sampleSpent("run-1", { run: run("running", "run-2"), error: "AGENT_UNAVAILABLE" }), true);
  assert.equal(sampleSpent(null, { run: null, error: "AGENT_UNAVAILABLE" }), false);
});

function reply(value: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(value), { status })); }
