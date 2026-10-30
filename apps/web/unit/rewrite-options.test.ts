import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RewriteOptions, type RewriteSettings } from "../src/workbench/editor/RewriteOptions";
import type { ConnectionSnapshot } from "../src/connection/workflow";

const codex = { kind: "codex_cli", display: "Codex", subscription: "ChatGPT", publisher: "OpenAI", loginCode: false, installed: true,
  enabled: true, state: "connected", version: null, versionStatus: "supported", plan: null, models: ["model-a", "model-b"],
  quota: { state: "available", usedPercent: null, resetsAt: null }, metadataReady: true };
const claude = { ...codex, kind: "claude_cli", display: "Claude", subscription: "Claude", publisher: "Anthropic", loginCode: true,
  models: ["claude-sonnet-5-5"], quota: { state: "not_provided", usedPercent: null, resetsAt: null } };
const catalog = { provider: "codex_cli", providers: [codex], versionStatus: "supported",
  state: "connected", version: null, plan: null, models: ["model-a", "model-b"], selectedModel: "model-a",
  modelReasoning: { "model-a": { supported: ["low", "medium"], default: "medium" }, "model-b": { supported: ["high"], default: "high" } },
  quota: { state: "available", usedPercent: null, resetsAt: null }, metadataReady: true, generationReady: true, experimentalMode: false } as ConnectionSnapshot;
const render = (settings: Partial<RewriteSettings>, disabled = false) => renderToStaticMarkup(createElement(RewriteOptions, { disabled,
  settings: { catalog, saved: { selectedRewriteModel: null, rewriteReasoningEffort: null }, saving: false, error: "",
    chooseModel: () => {}, chooseEffort: () => {}, ...settings } }));

test("the rewrite popover offers the listed models and the levels of the model rewriting runs on", () => {
  const html = render({});
  assert.ok(html.includes("Модель обработки · model-a") && html.includes(">model-b<"));
  assert.ok(html.includes(">Низкий<") && !html.includes(">Высокий<"));
  // model-b lacks the saved level, so the rewrite runs at its default, and the select shows that.
  const chosen = render({ saved: { selectedRewriteModel: "model-b", rewriteReasoningEffort: "low" } });
  assert.ok(chosen.includes(">Высокий<") && !chosen.includes(">Низкий<"));
  assert.match(chosen, /<option value="" selected="">По умолчанию \(высокий\)<\/option>/u);
  for (const html of [render({}, true), render({ saved: null }), render({ saving: true })]) {
    assert.equal(html.match(/<select[^>]*disabled=""/gu)?.length, 2);
  }
});

test("with both providers on, the rewrite models are grouped by provider and a stale choice stays visible", () => {
  const both = { ...catalog, providers: [codex, claude], models: ["model-a", "model-b", "claude-sonnet-5-5"],
    modelReasoning: { ...catalog.modelReasoning, "claude-sonnet-5-5": { supported: ["low", "high"], default: "high" } } } as ConnectionSnapshot;
  const html = render({ catalog: both, saved: { selectedRewriteModel: "claude-sonnet-5-5", rewriteReasoningEffort: null } });
  assert.match(html, /<optgroup label="Codex"><option value="model-a">model-a<\/option><option value="model-b">model-b<\/option><\/optgroup>/u);
  assert.match(html, /<optgroup label="Claude"><option value="claude-sonnet-5-5" selected="">claude-sonnet-5-5<\/option><\/optgroup>/u);
  assert.ok(html.includes("По умолчанию (высокий)"));
  // Claude switched off: its saved model is shown as unavailable, and Codex models are a plain list again.
  const single = render({ catalog, saved: { selectedRewriteModel: "claude-sonnet-5-5", rewriteReasoningEffort: null } });
  assert.ok(single.includes("claude-sonnet-5-5 · недоступна") && !single.includes("<optgroup"));
});
