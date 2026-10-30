import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ConnectionWorkflow, type ConnectionView, type ProviderEntry } from "../src/connection/workflow";
import { capabilities, settings, view } from "./support/assistant";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { Header } = await import("../src/workbench/layout/Header");
const { DeleteDialog } = await import("../src/workbench/layout/History");
const { enterOption } = await import("../src/workbench/facts/FocusIconDialog");
const { PreDraft } = await import("../src/workbench/import/PreDraft");
const { Composer } = await import("../src/workbench/assistant/Composer");
const { Connections } = await import("../src/workbench/settings/Connection");

const source = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the header has no rename control, whatever a caller passes (D084)", () => {
  const props = { title: "Synthetic resume", subtitle: "Engineer", collapsed: false, expand: () => {}, status: "Сохранено", ready: true,
    busy: false, save: () => {}, exportFile: () => {}, rename: () => {} };
  const header = renderToStaticMarkup(createElement(Header, props));
  assert.ok(!header.includes("Переименовать"));
  assert.ok(header.includes("Synthetic resume"));
  assert.ok(!source("../src/workbench/App.tsx").includes("rename"));
});

test("a refused delete says why inside its dialog, and an open dialog carries no old error", () => {
  const dialog = (error: string) => renderToStaticMarkup(createElement(DeleteDialog, { open: true, busy: false, error, close: () => {}, confirm: () => {} }));
  const refused = dialog("REQUEST_IN_PROGRESS");
  assert.match(refused, /role="alert"/u);
  assert.match(refused, /Дождитесь/u);
  assert.ok(!refused.includes("REQUEST_IN_PROGRESS"));
  assert.ok(!dialog("").includes('role="alert"'));
});

test("Enter in the icon search picks only from a search, so an empty one keeps the chosen icon", () => {
  const options = [{ id: "" }, { id: "react" }];
  assert.equal(enterOption("", options), undefined);
  assert.equal(enterOption("   ", options), undefined);
  assert.deepEqual(enterOption("rea", options.slice(1)), { id: "react" });
  assert.equal(enterOption("rea", []), undefined);
});

test("a technology chip's dialog is the panel's own, outside the aside whose Escape closes the panel", () => {
  // No DOM in these tests: the rule is that the chip list renders no dialog and hands the record to the panel.
  const chips = source("../src/workbench/facts/TechnologySelect.tsx"), panel = source("../src/workbench/facts/FactsPanel.tsx");
  assert.ok(!chips.includes("<FactDialog"));
  assert.ok(chips.includes("edit(record.id)"));
  assert.ok(panel.indexOf("</aside>") < panel.indexOf("<FactDialog"));
});

test("a pre-draft without an operation asks for the rewrite and effort choice, with rewriting off", () => {
  const form = (ask: boolean) => renderToStaticMarkup(createElement(PreDraft, { ask, busy: false, connection: null, resume: () => {} }));
  const asked = form(true);
  assert.match(asked, /Переписывать текст/u);
  assert.match(asked, /Уровень рассуждений импорта/u);
  assert.match(asked, /Продолжить импорт/u);
  assert.ok(!/id="import-rewrite"[^>]*checked/u.test(asked) && !/checked=""[^>]*id="import-rewrite"/u.test(asked), "rewriting is not on by default");
  assert.ok(!form(false).includes("Переписывать текст"), "an operation already holds the choices");
});

test("the composer marks a saved model the service refused, in the reply the server really sends", () => {
  const composer = (code: string) => renderToStaticMarkup(createElement(Composer, { view: view({ run: null, settings: { ...settings, selectedAgentModel: "saved" },
    capabilities: { ...capabilities, ready: false, unavailable: { code, detail: [] } } }), captured: null, active: false, applying: false, title: "Resume",
    draft: () => {}, flags: () => {}, model: () => {}, send: () => {}, stop: () => {}, clear: () => {}, settings: () => {} }));
  assert.match(composer("AGENT_MODEL_UNAVAILABLE"), /saved · недоступна/u);
  assert.ok(!composer("AGENT_CONNECTION_UNAVAILABLE").includes("недоступна"), "another refusal says nothing about the model");
});

const provider: ProviderEntry = { kind: "claude_cli", display: "Claude", subscription: "Claude", publisher: "Anthropic", loginCode: true, installed: true,
  enabled: true, state: "login_required", version: null, versionStatus: null, plan: null, models: [], metadataReady: false,
  quota: { state: "unknown", usedPercent: null, resetsAt: null } };
function connections(entry: ProviderEntry | null, changes: Partial<ConnectionView> = {}): string {
  const workflow = new ConnectionWorkflow(() => {}), { view: empty } = workflow;
  const snapshot = entry ? { ...empty.snapshot, provider: entry.kind, providers: [entry] } : empty.snapshot;
  return renderToStaticMarkup(createElement(Connections, { view: { ...empty, snapshot, ...changes }, workflow, disabled: false }));
}

test("a failed read of the connection offers a retry instead of waiting for ever", () => {
  assert.match(connections(null), /Проверяем подключение/u);
  const failed = connections(null, { readFailed: true });
  assert.ok(!failed.includes("Проверяем подключение"));
  assert.match(failed, /role="alert"/u); assert.match(failed, /Повторить/u);
});

test("the error of a provider that is off shows on its card", () => {
  const card = connections({ ...provider, enabled: false }, { activity: { claude_cli: { pending: false, detaching: false, error: "PROVIDER_INACTIVE" } } });
  assert.match(card, /role="alert"/u);
  assert.match(card, /провайдер выключен/u);
});

test("a provider that is on says that sign-in and install stop model work (D119)", () => {
  assert.match(connections(provider), /останавливают работу моделей/u);
  assert.ok(!connections({ ...provider, enabled: false }).includes("останавливают работу моделей"), "nothing to stop on a provider that is off");
});
