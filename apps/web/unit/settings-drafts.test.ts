import assert from "node:assert/strict";
import test from "node:test";
import { SettingsDrafts, type SettingsApi, type SettingsPart } from "../src/workbench/settings/drafts";
import type { Preferences } from "../src/contracts/generated/preferences";
import type { RulesSettings } from "../src/contracts/generated/rules_settings";
import type { AgentSettings } from "../src/contracts/generated/agent_settings";
import { projectFilename } from "../src/workbench/files/filename";

function gate() { let release = () => {}; const wait = new Promise<void>(resolve => { release = resolve; }); return { wait, release }; }
function setup() {
  const server = {
    preferences: { schemaVersion: 1, selectedModel: "model-a", automaticAnalysis: true, theme: "light" } as Preferences,
    rules: { revision: 1, markdown: "## Preset: shorten\nShorten.\n## Preset: clarify\nClarify.\n", sha256: "a".repeat(64), presets: { shorten: "Shorten.", clarify: "Clarify." } } as RulesSettings,
    assistant: { schemaVersion: 1, revision: 1, enabled: false, selectedAgentModel: null } as AgentSettings,
  };
  const calls: { part: SettingsPart; value: unknown }[] = [], fail = new Set<SettingsPart>();
  // Like Python: a level is saved for the model rewriting runs on, and only a level that model reports.
  const levels: Record<string, string[]> = { "model-a": ["low", "medium", "high"], "model-b": ["low", "high"], "model-c": ["high"] };
  const rewriting = () => server.preferences.selectedRewriteModel ?? server.preferences.selectedModel ?? "";
  const api: SettingsApi = {
    preferences: async () => structuredClone(server.preferences), rules: async () => structuredClone(server.rules), assistant: async () => structuredClone(server.assistant),
    select: async model => { calls.push({ part: "model", value: model }); if (!model || fail.has("model")) throw new Error("unavailable"); server.preferences.selectedModel = model; return model; },
    saveReasoning: async (model, effort) => { calls.push({ part: "reasoning", value: { model, effort } });
      if (fail.has("reasoning") || model !== rewriting() || effort && !levels[model]?.includes(effort)) throw new Error("unsupported");
      server.preferences.rewriteReasoningEffort = effort; return structuredClone(server.preferences); },
    selectRewrite: async model => { calls.push({ part: "rewrite", value: model }); if (fail.has("rewrite")) throw new Error("unavailable");
      server.preferences.selectedRewriteModel = model;
      const effort = server.preferences.rewriteReasoningEffort;
      if (effort && !levels[rewriting()]?.includes(effort)) server.preferences.rewriteReasoningEffort = null;
      return structuredClone(server.preferences); },
    selectImport: async model => { calls.push({ part: "import", value: model }); if (fail.has("import")) throw new Error("unavailable");
      server.preferences.selectedImportModel = model; return structuredClone(server.preferences); },
    selectFallback: async model => { calls.push({ part: "fallback", value: model }); if (fail.has("fallback")) throw new Error("unavailable");
      server.preferences.selectedFallbackModel = model; return structuredClone(server.preferences); },
    saveLimits: async value => { calls.push({ part: "limits", value });
      if (fail.has("limits") || !Number.isInteger(value.importMinutes) || !Number.isInteger(value.projectMegabytes))
        throw Object.assign(new Error("invalid"), { code: "INVALID_REQUEST" });
      server.preferences = { ...server.preferences, ...value }; return structuredClone(server.preferences); },
    saveAssistant: async request => { calls.push({ part: "assistant", value: request });
      if (fail.has("assistant") || request.expectedRevision !== server.assistant.revision) throw Object.assign(new Error("conflict"), { code: "AGENT_SETTINGS_CONFLICT" });
      server.assistant = { schemaVersion: 1, revision: server.assistant.revision + 1, enabled: request.enabled, selectedAgentModel: request.selectedAgentModel,
        reasoningEffort: request.reasoningEffort ?? null }; return structuredClone(server.assistant); },
    saveRules: async request => { calls.push({ part: "rules", value: request });
      if (fail.has("rules") || request.baseRevision !== server.rules.revision) throw Object.assign(new Error("stale"), { code: "RULES_STALE" });
      server.rules = { ...server.rules, markdown: request.markdown, revision: server.rules.revision + 1 }; return structuredClone(server.rules); },
  };
  const changes: unknown[] = [], controller = new SettingsDrafts(api, value => changes.push(value));
  return { server, api, controller, calls, fail, changes };
}

test("partial Save retains failed drafts and Cancel keeps successful writes", async () => {
  const h = setup(); await h.controller.load(); const originalRules = h.server.rules.markdown;
  h.controller.change("model", "model-b"); h.controller.change("importModel", "model-c"); h.controller.change("agentEnabled", true);
  h.controller.change("agentModel", "agent-b"); h.controller.change("markdown", `${originalRules}\nDraft rule.`);
  h.fail.add("assistant"); h.fail.add("rules"); await h.controller.save();
  assert.deepEqual(h.controller.state.saved, ["model", "import"]); assert.deepEqual(h.controller.dirty, ["assistant", "rules"]);
  assert.equal(h.controller.state.staleRules, true); assert.equal(h.server.preferences.selectedModel, "model-b"); assert.equal(h.server.preferences.selectedImportModel, "model-c");
  assert.ok(h.controller.state.draft.markdown.endsWith("Draft rule."));
  const calls = h.calls.length; h.controller.cancel(); assert.equal(h.calls.length, calls);
  assert.deepEqual(h.controller.dirty, []); assert.equal(h.controller.state.draft.model, "model-b"); assert.equal(h.controller.state.draft.importModel, "model-c");
  assert.equal(h.controller.state.draft.agentEnabled, false); assert.equal(h.controller.state.draft.markdown, originalRules);
});

test("the assistant effort is a draft saved with the assistant model", async () => {
  const h = setup(); await h.controller.load();
  assert.equal(h.controller.state.draft.agentEffort, null);
  h.controller.change("agentModel", "agent-b"); h.controller.change("agentEffort", "high");
  assert.deepEqual(h.controller.dirty, ["assistant"]);
  await h.controller.save();
  assert.deepEqual(h.calls.at(-1), { part: "assistant", value: { expectedRevision: 1, enabled: false, selectedAgentModel: "agent-b", reasoningEffort: "high" } });
  assert.deepEqual(h.controller.dirty, []);
});

test("limits show contract defaults, send numbers and keep a rejected draft for correction", async () => {
  const h = setup(); await h.controller.load();
  assert.equal(h.controller.state.draft.importMinutes, "60"); assert.equal(h.controller.state.draft.projectMegabytes, "64"); assert.deepEqual(h.controller.dirty, []);
  h.controller.change("importMinutes", "12.5"); await h.controller.save();
  assert.equal(h.controller.state.errors.limits, "Не удалось сохранить лимиты. Укажите целые числа в допустимых пределах.");
  assert.equal(h.controller.state.draft.importMinutes, "12.5"); assert.deepEqual(h.controller.dirty, ["limits"]);
  h.controller.change("importMinutes", "90"); h.controller.change("projectMegabytes", "128"); await h.controller.save();
  assert.deepEqual(h.calls.at(-1), { part: "limits", value: { importMinutes: 90, projectMegabytes: 128 } });
  assert.deepEqual(h.controller.state.saved, ["limits"]); assert.equal(h.controller.state.errors.limits, undefined); assert.deepEqual(h.controller.dirty, []);
  assert.equal(h.controller.state.preferences?.importMinutes, 90);
  h.controller.change("projectMegabytes", "20"); h.controller.cancel(); assert.equal(h.controller.state.draft.projectMegabytes, "128");
});

test("explicit retries reload conflict bases without replacing local choices or resaving accepted sections", async () => {
  const h = setup(); await h.controller.load(); h.controller.change("importModel", "model-c"); h.controller.change("agentEnabled", true);
  h.controller.change("agentModel", "agent-b"); h.controller.change("markdown", "Local rules");
  h.fail.add("assistant"); h.fail.add("rules"); await h.controller.save();
  h.fail.clear(); h.server.assistant.revision = 7; h.server.rules = { ...h.server.rules, revision: 4, markdown: "External rules" };
  await h.controller.reloadRules(); await h.controller.reloadAssistant();
  assert.equal(h.controller.state.draft.markdown, "Local rules"); assert.equal(h.controller.state.rules?.markdown, "External rules");
  assert.equal(h.controller.state.draft.agentEnabled, true); assert.equal(h.controller.state.comparison, true);
  await h.controller.save(); assert.deepEqual(h.controller.dirty, []);
  assert.equal(h.calls.filter(call => call.part === "import").length, 1);
  assert.deepEqual(h.calls.filter(call => call.part === "rules").at(-1)?.value, { baseRevision: 4, markdown: "Local rules" });
  assert.deepEqual(h.calls.filter(call => call.part === "assistant").at(-1)?.value, { expectedRevision: 7, enabled: true, selectedAgentModel: "agent-b", reasoningEffort: null });
});

test("an older Save acknowledgment keeps newer draft text for the next explicit Save", async () => {
  const h = setup(), entered = gate(), release = gate(); await h.controller.load();
  const save = h.api.saveRules; h.api.saveRules = async request => { entered.release(); await release.wait; return save(request); };
  h.controller.change("markdown", "Submitted rules"); const pending = h.controller.save(); await entered.wait;
  h.controller.change("markdown", "Newer draft"); release.release(); await pending;
  assert.equal(h.controller.state.rules?.markdown, "Submitted rules"); assert.equal(h.controller.state.draft.markdown, "Newer draft");
  assert.deepEqual(h.controller.dirty, ["rules"]); await h.controller.save(); assert.equal(h.server.rules.markdown, "Newer draft");
});

test("retrying an incomplete load does not silently advance an already loaded rules revision", async () => {
  const h = setup(), read = h.api.preferences; h.api.preferences = async () => { throw new Error("offline"); };
  await h.controller.load(); assert.equal(h.controller.state.preferences, null); h.controller.change("markdown", "Local draft");
  h.server.rules = { ...h.server.rules, markdown: "External rules", revision: 9 }; h.api.preferences = read;
  await h.controller.load(); assert.equal(h.controller.state.rules?.revision, 1); assert.equal(h.controller.state.draft.markdown, "Local draft");
  await h.controller.save(); assert.equal(h.controller.state.staleRules, true); assert.equal(h.server.rules.markdown, "External rules");
});

test("Cancel restores a null model and never sends a rollback request", async () => {
  const h = setup(); h.server.preferences.selectedModel = null; await h.controller.load(); h.controller.change("model", "model-b");
  h.controller.cancel(); assert.equal(h.controller.state.draft.model, null); assert.deepEqual(h.calls, []);
});

test("import selection persists independently and can return to the processing model", async () => {
  const h = setup(); await h.controller.load();
  assert.equal(h.controller.state.draft.importModel, null);
  h.controller.change("importModel", "model-b"); await h.controller.save();
  assert.equal(h.server.preferences.selectedImportModel, "model-b");
  assert.equal(h.server.preferences.selectedModel, "model-a");
  assert.equal(h.server.assistant.selectedAgentModel, null);
  const reopened = new SettingsDrafts(h.api, () => {}); await reopened.load();
  assert.equal(reopened.state.draft.importModel, "model-b");
  reopened.change("importModel", null); reopened.cancel();
  assert.equal(reopened.state.draft.importModel, "model-b");
  reopened.change("importModel", null); await reopened.save();
  assert.equal(h.server.preferences.selectedImportModel, null);
  assert.deepEqual(h.calls.map(call => call.part), ["import", "import"]);
});

test("the fallback model saves on its own, clears to none and leaves the import and processing models unchanged", async () => {
  const h = setup(); await h.controller.load();
  assert.equal(h.controller.state.draft.fallbackModel, null);
  h.controller.change("fallbackModel", "model-c"); assert.deepEqual(h.controller.dirty, ["fallback"]);
  await h.controller.save();
  assert.deepEqual(h.calls, [{ part: "fallback", value: "model-c" }]);
  assert.equal(h.server.preferences.selectedFallbackModel, "model-c");
  assert.equal(h.server.preferences.selectedImportModel, undefined); assert.equal(h.server.preferences.selectedModel, "model-a");
  h.controller.change("fallbackModel", null); h.controller.cancel();
  assert.equal(h.controller.state.draft.fallbackModel, "model-c");
  h.fail.add("fallback"); h.controller.change("fallbackModel", null); await h.controller.save();
  assert.equal(h.controller.state.draft.fallbackModel, null); assert.ok(h.controller.state.errors.fallback);
  h.fail.delete("fallback"); await h.controller.save();
  assert.equal(h.server.preferences.selectedFallbackModel, null); assert.deepEqual(h.controller.dirty, []);
});

test("failed import saves keep the choice while other settings save successfully", async () => {
  const h = setup(); await h.controller.load(); h.fail.add("import");
  h.controller.change("importModel", "model-b"); h.controller.change("model", "model-c");
  h.controller.change("fallbackModel", "model-d"); await h.controller.save();
  assert.deepEqual(h.controller.state.saved, ["model", "fallback"]);
  assert.deepEqual(h.controller.dirty, ["import"]);
  assert.equal(h.controller.state.draft.importModel, "model-b");
  assert.equal(h.server.preferences.selectedImportModel, undefined);
  h.fail.clear(); await h.controller.save();
  assert.equal(h.server.preferences.selectedImportModel, "model-b");
  assert.equal(h.server.preferences.selectedModel, "model-c");
  assert.equal(h.server.preferences.selectedFallbackModel, "model-d");
});

test("an import save acknowledgment retains a newer model draft", async () => {
  const h = setup(), entered = gate(), release = gate(); await h.controller.load();
  const save = h.api.selectImport;
  h.api.selectImport = async model => { entered.release(); await release.wait; return save(model); };
  h.controller.change("importModel", "model-b"); const pending = h.controller.save(); await entered.wait;
  h.controller.change("importModel", "model-c"); release.release(); await pending;
  assert.equal(h.controller.state.preferences?.selectedImportModel, "model-b");
  assert.equal(h.controller.state.draft.importModel, "model-c");
  assert.deepEqual(h.controller.dirty, ["import"]);
});

test("closing during Save invalidates late UI callbacks and unsent section writes", async () => {
  const h = setup(), entered = gate(), release = gate(); await h.controller.load();
  const select = h.api.select; h.api.select = async model => { entered.release(); await release.wait; return select(model); };
  h.controller.change("model", "model-b"); h.controller.change("importModel", "model-c");
  const pending = h.controller.save(); await entered.wait; h.controller.close(); const count = h.changes.length; release.release(); await pending;
  assert.equal(h.changes.length, count); assert.deepEqual(h.calls.map(call => call.part), ["model"]); assert.equal(h.server.preferences.selectedImportModel, undefined);
});

test("a stored automatic check choice is never a draft and Save never writes it", async () => {
  for (const stored of [true, false]) {
    const h = setup(); h.server.preferences.automaticAnalysis = stored; await h.controller.load();
    assert.deepEqual(h.controller.dirty, []); assert.equal("automatic" in h.controller.state.draft, false);
    h.controller.change("model", "model-b"); await h.controller.save(); h.controller.cancel();
    assert.deepEqual(h.calls.map(call => call.part), ["model"]); assert.equal(h.server.preferences.automaticAnalysis, stored);
  }
});

test("download names retain Unicode, remove path/control characters and stay within a filename byte limit", () => {
  assert.equal(projectFilename("Алексей Соколов", "foldcv"), "Алексей Соколов.foldcv");
  assert.equal(projectFilename(" ../CV/Name\n\u0000:*? ", "docx"), "CV Name.docx");
  assert.equal(projectFilename("...", "docx"), "resume.docx");
  assert.ok(new TextEncoder().encode(projectFilename("😀".repeat(200), "foldcv")).length <= 255);
});

test("reasoning saves with the chosen model, retains failed drafts and restores on Cancel", async () => {
  const h = setup(); await h.controller.load();
  h.controller.change("model", "model-b"); h.controller.change("reasoning", "low");
  h.fail.add("reasoning"); await h.controller.save();
  assert.equal(h.server.preferences.selectedModel, "model-b");
  assert.deepEqual(h.controller.dirty, ["reasoning"]);
  assert.equal(h.controller.state.draft.reasoning, "low");
  h.fail.clear(); await h.controller.save();
  assert.equal(h.server.preferences.rewriteReasoningEffort, "low");
  const count = h.calls.length;
  h.controller.change("reasoning", "high"); h.controller.cancel();
  assert.equal(h.controller.state.draft.reasoning, "low");
  assert.equal(h.calls.length, count);
  h.controller.change("reasoning", null); await h.controller.save();
  assert.equal(h.server.preferences.rewriteReasoningEffort, null);
});

test("the rewrite model saves before its level, which must be one that model reports", async () => {
  const h = setup(); h.server.preferences.rewriteReasoningEffort = "low"; await h.controller.load();
  h.controller.change("rewriteModel", "model-c"); assert.deepEqual(h.controller.dirty, ["rewrite", "reasoning"]);
  await h.controller.save();
  assert.deepEqual(h.calls.map(call => call.part), ["rewrite", "reasoning"]); assert.deepEqual(h.controller.state.saved, ["rewrite"]);
  assert.equal(h.server.preferences.rewriteReasoningEffort, null); assert.ok(h.controller.state.errors.reasoning);
  h.controller.change("reasoning", "high"); await h.controller.save();
  assert.deepEqual(h.calls.at(-1), { part: "reasoning", value: { model: "model-c", effort: "high" } }); assert.deepEqual(h.controller.dirty, []);
  // Back to the processing model: the level is saved again, for the model rewriting now runs on.
  h.controller.change("rewriteModel", null); await h.controller.save();
  assert.deepEqual(h.calls.slice(-2), [{ part: "rewrite", value: null }, { part: "reasoning", value: { model: "model-a", effort: "high" } }]);
  assert.equal(h.server.preferences.rewriteReasoningEffort, "high"); assert.deepEqual(h.controller.dirty, []);
});

test("reopened Settings shows rewrite choices saved in the popover and keeps its own unsaved edits", async () => {
  const h = setup(); await h.controller.load();
  h.controller.change("importModel", "model-c");
  Object.assign(h.server.preferences, { selectedRewriteModel: "model-b", rewriteReasoningEffort: "high", selectedImportModel: "model-a" });
  await h.controller.refreshPreferences();
  assert.equal(h.controller.state.draft.rewriteModel, "model-b"); assert.equal(h.controller.state.draft.reasoning, "high");
  assert.equal(h.controller.state.draft.importModel, "model-c"); assert.deepEqual(h.controller.dirty, ["import"]);
});
