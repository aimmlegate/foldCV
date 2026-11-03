import assert from "node:assert/strict";
import test from "node:test";
import { AgentApiFailure } from "../src/assistant/api";
import { AssistantRuns } from "../src/assistant/controller";
import { applyStep, parseSample, parseTemplateProposal, proposalCard, proposalTarget, TemplateAssistantApi, textHash,
  type TemplateFields, type TemplateProposal } from "../src/assistant/template";
import type { Fetcher } from "../src/rich/v7-connection";
import { applyProposal, type ApplyEditor } from "../src/workbench/templates/apply";
import type { ShownTemplate } from "../src/workbench/templates/studio";
import { capabilities, run, settings } from "./support/assistant";

const saved = (id: string, text: string): ShownTemplate => ({ kind: "saved", state: { package: { id, name: id, revision: "1.0.0", packageHash: "a".repeat(64) },
  format: "yaml", text, bundled: false, edited: false } });
async function proposal(base: string, changes: Partial<TemplateProposal> = {}): Promise<TemplateProposal> {
  return { id: "proposal-1", conversationId: "conversation-1", runId: "run-1", templateId: "generic", name: null, baseHash: await textHash(base),
    text: "template:\n  name: Крупнее\n", summary: "Имя на 2 pt крупнее", state: "proposed", ...changes };
}

/** The templates screen as Apply sees it, with a record of what it did. */
function editor(shown: ShownTemplate | null, text: string, stored: Record<string, string> = {}, leave = true) {
  const log: string[] = [];
  const state = { shown, text };
  const port: ApplyEditor = {
    current: () => state,
    mayLeave: () => { log.push("ask"); return Promise.resolve(leave); },
    open: templateId => { log.push(`open ${templateId}`); const value = stored[templateId] ?? ""; state.shown = saved(templateId, value); state.text = value; return Promise.resolve(value); },
    showDraft: (name, assetsFrom, value) => { log.push(`draft ${name} ${String(assetsFrom)}`); state.shown = { kind: "draft", name, assetsFrom }; state.text = value; },
    renameDraft: name => { log.push(`rename ${name}`); if (state.shown?.kind === "draft") state.shown = { ...state.shown, name }; },
    replace: value => { log.push("replace"); state.text = value; },
  };
  return { port, log, state };
}

test("the SHA-256 of the editor text is lower-case hex of its UTF-8 bytes", async () => {
  assert.equal(await textHash("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  assert.equal((await textHash("шаблон")).length, 64);
});

test("apply replaces the shown template's text only while it has the run's base hash", async () => {
  const base = "template:\n  name: Две колонки\n", value = await proposal(base);
  const same = editor(saved("generic", base), base);
  assert.equal(await applyProposal(value, false, "generic", same.port), "applied");
  assert.deepEqual(same.log, ["replace"]);
  assert.equal(same.state.text, value.text);
  // Edited during the run: nothing changes until a forced replace.
  const edited = editor(saved("generic", base), `${base}# правка\n`);
  assert.equal(await applyProposal(value, false, "generic", edited.port), "changed");
  assert.deepEqual(edited.log, []);
  assert.equal(await applyProposal(value, true, "generic", edited.port), "applied");
  assert.equal(edited.state.text, value.text);
});

test("another saved target opens first, asking only about unsaved edits, then follows the hash rule", async () => {
  const base = "template:\n  name: Две колонки\n", value = await proposal(base);
  const clean = editor(saved("compact", "x: 1\n"), "x: 1\n", { generic: base });
  assert.equal(await applyProposal(value, false, "generic", clean.port), "applied");
  assert.deepEqual(clean.log, ["open generic", "replace"]);
  const refused = editor(saved("compact", "x: 1\n"), "x: 2\n", { generic: base }, false);
  assert.equal(await applyProposal(value, false, "generic", refused.port), "cancelled");
  assert.deepEqual(refused.log, ["ask"]);
  assert.equal(refused.state.text, "x: 2\n");
  // The target was saved again after the run: it opens and the card asks for «Заменить».
  const moved = editor(saved("compact", "x: 1\n"), "x: 1\n", { generic: `${base}# сохранено позже\n` });
  assert.equal(await applyProposal(value, false, "generic", moved.port), "changed");
  assert.deepEqual(moved.log, ["open generic"]);
});

test("a new-template proposal opens an unsaved entry with the run's assets, or refines the shown one", async () => {
  const base = "template:\n  name: Две колонки\n", value = await proposal(base, { templateId: null, name: "Мой" });
  const fresh = editor(saved("generic", base), base);
  assert.equal(await applyProposal(value, false, null, fresh.port), "applied");
  assert.deepEqual(fresh.log, ["draft Мой generic"], "without a known run the shown template's assets are used");
  assert.deepEqual(fresh.state.shown, { kind: "draft", name: "Мой", assetsFrom: "generic" });
  const elsewhere = editor(saved("compact", "x: 1\n"), "x: 2\n");
  assert.equal(await applyProposal(value, false, "generic", elsewhere.port), "applied");
  assert.deepEqual(elsewhere.log, ["ask", "draft Мой generic"]);
  // A second round on the unsaved entry keeps it and its assets.
  const second = await proposal(value.text, { templateId: null, name: "Мой 2", text: "template:\n  name: Ещё крупнее\n" });
  assert.equal(await applyProposal(second, false, "generic", elsewhere.port), "applied");
  assert.deepEqual(elsewhere.log.slice(2), ["rename Мой 2", "replace"]);
  assert.deepEqual(elsewhere.state.shown, { kind: "draft", name: "Мой 2", assetsFrom: "generic" });
});

test("the step rule: target, then the hash", () => {
  const value = { templateId: "generic", baseHash: "h" };
  assert.deepEqual(applyStep(value, null, "h"), { kind: "open", ask: false });
  assert.deepEqual(applyStep(value, { templateId: "generic", draft: false, unsaved: true }, "h"), { kind: "replace" });
  assert.deepEqual(applyStep(value, { templateId: "generic", draft: false, unsaved: true }, "other"), { kind: "confirm" });
  assert.deepEqual(applyStep(value, { templateId: null, draft: true, unsaved: true }, "h"), { kind: "open", ask: true });
  assert.deepEqual(applyStep({ templateId: null, baseHash: "h" }, { templateId: "generic", draft: false, unsaved: false }, "h"), { kind: "open", ask: false });
});

test("the card offers Apply, then «Заменить» once the text changed, and nothing after a decision", () => {
  assert.deepEqual(proposalCard({ state: "proposed" }, false, false), { heading: "Предложение шаблона", notice: null, apply: true, replace: false, discard: true });
  assert.deepEqual(proposalCard({ state: "proposed" }, true, false),
    { heading: "Предложение шаблона", notice: "Текст изменился после запуска.", apply: false, replace: true, discard: true });
  assert.deepEqual(proposalCard({ state: "proposed" }, false, true), { heading: "Предложение шаблона", notice: null, apply: false, replace: false, discard: false });
  assert.equal(proposalCard({ state: "applied" }, false, false).apply, false);
  assert.deepEqual(proposalCard({ state: "discarded" }, true, false), { heading: "Отклонено", notice: null, apply: false, replace: false, discard: false });
  const names = new Map([["generic", "Две колонки"]]);
  assert.equal(proposalTarget({ templateId: "generic", name: null }, names), "Две колонки");
  assert.equal(proposalTarget({ templateId: null, name: "Мой" }, names), "новый шаблон «Мой»");
});

test("proposal and sample replies are checked before use", () => {
  const value = { id: "p", conversationId: "c", runId: "r", templateId: null, name: "Мой", baseHash: "h", text: "t", summary: "s", state: "applied" };
  assert.deepEqual(parseTemplateProposal(value), value);
  assert.throws(() => parseTemplateProposal({ ...value, state: "draft" }), /INVALID_RESULT/);
  assert.throws(() => parseTemplateProposal({ ...value, templateId: 3 }), /INVALID_RESULT/);
  assert.throws(() => parseTemplateProposal({ ...value, text: undefined }), /INVALID_RESULT/);
  assert.deepEqual(parseSample({ sampleId: "s1", name: "Образец.docx", pages: null, unitCount: 40 }), { sampleId: "s1", name: "Образец.docx", pages: null, unitCount: 40 });
  assert.deepEqual(parseSample({ sampleId: "s1", name: "a.pdf", pages: 2, unitCount: 0 }).pages, 2);
  assert.throws(() => parseSample({ sampleId: "s1", name: "a.pdf", pages: 1.5, unitCount: 0 }), /INVALID_RESULT/);
  assert.throws(() => parseSample({ sampleId: "s1", name: "a.pdf", pages: null }), /INVALID_RESULT/);
});

type Call = { url: string; method: string; body: unknown };
/** A scripted template assistant server on the frozen routes. */
function server(proposals: unknown[] = []) {
  const calls: Call[] = [];
  const conversation = { id: "conversation-1", title: "", createdAt: "2026-11-03T12:00:00+00:00", updatedAt: "2026-11-03T12:00:00+00:00" };
  const fetcher: Fetcher = (input, init) => {
    const url = String(input), method = init?.method ?? "GET";
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body ?? null;
    calls.push({ url, method, body });
    const reply = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }));
    if (url === "/v1/settings/assistant") return reply(settings);
    if (url.endsWith("/capabilities")) return reply({ ...capabilities, tools: ["read_template"] });
    if (url.endsWith("/conversations") && method === "GET") return reply({ items: [] });
    if (url.endsWith("/conversations")) return reply(conversation);
    if (url.endsWith("/messages")) return reply({ conversation, messages: [], sources: [], findings: [], runs: [], files: [] });
    if (url.endsWith("/runs")) return reply({ ...run("running", "run-7"), projectId: "templates", allowEdits: false, baseRevision: 0 });
    if (url.includes("/events/")) return reply({ run: { ...run("completed", "run-7"), projectId: "templates" }, events: [], next: 0 });
    if (url.includes("/proposals?")) return reply({ items: proposals });
    if (url.endsWith("/state")) return reply({ ...(proposals[0] as object), state: (body as { state: string }).state });
    if (url.endsWith("/samples")) return reply({ sampleId: "sample-1", name: "Образец.docx", pages: null, unitCount: 12 });
    return reply({ error: { code: "REQUEST_FAILED" } }, 404);
  };
  return { fetcher, calls };
}

test("a template run posts the editor context on the template routes with edits off and no selection", async () => {
  const { fetcher, calls } = server();
  const api = new TemplateAssistantApi(fetcher);
  const runs = new AssistantRuns<TemplateFields>(api, { applyProposal: () => Promise.reject(new AgentApiFailure("REQUEST_FAILED")) }, () => {}, 1);
  try {
    runs.flags({ allowEdits: false, allowWeb: true });
    await runs.init(); runs.draft("Сделай имя на 2 pt крупнее");
    const sample = await api.uploadSample(new File(["PK"], "Образец.docx"));
    const text = "template:\n  name: Две колонки\n";
    await runs.sendWith(async () => ({ templateId: "generic", assetsFrom: "generic", text, textHash: await textHash(text), sampleId: sample.sampleId }));
    const posted = calls.find(call => call.url.endsWith("/runs"));
    assert.equal(posted?.url, "/v2/templates/assistant/conversations/conversation-1/runs");
    const body = posted?.body as Record<string, unknown>;
    assert.equal(typeof body["clientRequestId"], "string");
    assert.deepEqual({ ...body, clientRequestId: "" }, { clientRequestId: "", message: "Сделай имя на 2 pt крупнее", allowEdits: false, allowWeb: true,
      templateId: "generic", assetsFrom: "generic", text, textHash: await textHash(text), sampleId: "sample-1" });
    assert.ok(!("selection" in body));
    assert.equal(api.runAssets.get("run-7"), "generic");
    assert.equal(api.runSamples.get("run-7"), "Образец.docx");
    const upload = calls.find(call => call.url.endsWith("/samples"));
    assert.equal(upload?.method, "POST");
    assert.ok(upload?.body instanceof FormData && upload.body.get("file") instanceof File);
    assert.ok(calls.every(call => call.url.startsWith("/v2/templates/assistant/") || call.url === "/v1/settings/assistant"), "no resume route is called");
  } finally { runs.close(); }
});

test("template proposals are listed per conversation and decided on their own route", async () => {
  const stored = { id: "proposal-1", conversationId: "conversation-1", runId: "run-7", templateId: "generic", name: null, baseHash: "h",
    text: "t", summary: "s", state: "proposed" };
  const { fetcher, calls } = server([stored]);
  const api = new TemplateAssistantApi(fetcher);
  assert.deepEqual(await api.templateProposals("conversation-1"), [stored]);
  assert.equal(calls.at(-1)?.url, "/v2/templates/assistant/proposals?conversationId=conversation-1");
  assert.equal((await api.decide("proposal-1", "applied")).state, "applied");
  assert.deepEqual(calls.at(-1), { url: "/v2/templates/assistant/proposals/proposal-1/state", method: "POST", body: { state: "applied" } });
  // The run controller's resume proposal list stays empty in this scope.
  assert.deepEqual(await api.proposals(), { items: [] });
});
