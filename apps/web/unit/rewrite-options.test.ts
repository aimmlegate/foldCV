import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RewriteOptions, type RewriteSettings } from "../src/workbench/editor/RewriteOptions";
import type { ConnectionSnapshot } from "../src/connection/workflow";

const codex = { kind: "codex_cli", display: "Codex", subscription: "ChatGPT", publisher: "OpenAI", loginCode: false, installed: true };
const catalog = { provider: "codex_cli", providers: [codex], providerNotice: null, versionStatus: "supported",
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
