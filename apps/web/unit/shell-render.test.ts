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
const { DeleteDialog, History } = await import("../src/workbench/layout/History");
const { enterOption } = await import("../src/workbench/facts/FocusIconDialog");
const { PreDraft } = await import("../src/workbench/import/PreDraft");
const { Composer } = await import("../src/workbench/assistant/Composer");
const { Connections, LeaveDialog, quotaText } = await import("../src/workbench/settings/Connection");
const { FileDialog } = await import("../src/workbench/files/FileDialog");

const source = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the header has no rename control, whatever a caller passes (D084)", () => {
  const props = { title: "Synthetic resume", subtitle: "Engineer", collapsed: false, expand: () => {}, status: "Сохранено", ready: true,
    busy: false, save: () => {}, exportFile: () => {}, rename: () => {} };
  const header = renderToStaticMarkup(createElement(Header, props));
  assert.ok(!header.includes("Переименовать"));
  assert.ok(header.includes("Synthetic resume"));
  assert.ok(!source("../src/workbench/App.tsx").includes("rename"));
});

test("the export dialog offers DOCX and PDF; DOCX is chosen first and the print hint waits for PDF", () => {
  const dialog = renderToStaticMarkup(createElement(FileDialog, { mode: "export", title: "Synthetic resume", subtitle: "Engineer",
    filename: "Synthetic resume.docx", error: "", busy: false, close: () => {}, download: () => Promise.resolve(null),
    print: () => Promise.resolve(false), upload: () => Promise.resolve(false) }));
  const inputs = dialog.match(/<input[^>]*>/gu) ?? [];
  assert.deepEqual(inputs.map(input => [/value="(\w+)"/u.exec(input)?.[1], input.includes('checked=""')]), [["docx", true], ["pdf", false]]);
  assert.ok(dialog.includes("Скачать DOCX"));
  assert.ok(!dialog.includes("Печать в PDF") && !dialog.includes("Откроется окно печати"));
});

test("Settings and Templates show the way back in the header; the resume screen does not", () => {
  const props = { title: "Настройки", subtitle: "foldCV Beta", collapsed: false, expand: () => {}, status: "Сохранено", ready: false,
    busy: false, save: () => {}, exportFile: () => {} };
  const away = renderToStaticMarkup(createElement(Header, { ...props, back: () => {} }));
  assert.match(away, /class="button header-back"[^>]*aria-keyshortcuts="Escape"/u);
  assert.ok(away.includes("К резюме"));
  assert.ok(!renderToStaticMarkup(createElement(Header, { ...props, ready: true })).includes("header-back"));
});

test("the sidebar marks one current place: the open resume, or the Settings or Templates button", () => {
  const entry = { projectId: "p1", title: "Alex Example", updatedAt: "2026-10-01T10:00:00+00:00", tombstoned: false, cleanupStatus: "none" as const };
  const sidebar = (screen: "resume" | "settings" | "templates") => renderToStaticMarkup(createElement(History, {
    projects: { entries: [entry], errors: [] }, activeId: "p1", screen, busy: false, collapse: () => {}, fresh: () => {},
    open: () => Promise.resolve(true), remove: () => Promise.resolve(true), archive: () => Promise.resolve(true), openFile: () => {},
    settings: () => {}, templates: () => {}, connection: "Codex подключён", error: "" }));
  const current = (markup: string) => (markup.match(/<button[^>]*aria-current="page"[^>]*>.*?<\/button>/gu) ?? []).map(button => button.replace(/<[^>]+>/gu, ""));
  assert.deepEqual(current(sidebar("resume")), ["Alex Example"]);
  assert.match(sidebar("resume"), /class="project-row active"/u);
  assert.deepEqual(current(sidebar("settings")), ["Настройки"]);
  assert.deepEqual(current(sidebar("templates")), ["Шаблоны"]);
  assert.ok(!sidebar("templates").includes("project-row active"));
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

test("an update offer has its own row and the update button in the card's head (D146, D147)", () => {
  const installation = { available: true, downloadedBytes: 0, error: null, installed: "2.1.310", latest: "2.1.318", state: "idle" as const, totalBytes: 0, update: true };
  const card = connections({ ...provider, state: "connected", plan: "max", version: "2.1.310", installation });
  assert.match(card, /Доступна новая версия Claude: 2\.1\.318\. Установлена 2\.1\.310\./u);
  assert.match(card, /<div class="provider-actions">.*Обновить Claude/u);
  assert.match(card, /по подписке Claude · max · 2\.1\.310/u);
  const latest = connections({ ...provider, state: "connected", installation: { ...installation, latest: "2.1.310", update: false } });
  assert.match(latest, /Установлена последняя версия Claude/u); assert.ok(!latest.includes("Обновить Claude"));
  // A provider that is off shows its name and one line, no actions.
  assert.ok(!connections({ ...provider, enabled: false }).includes("provider-actions"));
});

test("the usage line says the share used and the reset, or that the provider reports none", () => {
  const before = Date.UTC(2026, 10, 5, 8, 0);
  assert.equal(quotaText({ state: "not_provided", usedPercent: null, resetsAt: null }, before), "Расход не сообщается");
  assert.equal(quotaText({ state: "available", usedPercent: 12, resetsAt: null }, before), "Использовано 12 %");
  assert.equal(quotaText({ state: "unknown", usedPercent: null, resetsAt: null }, before), "Расход неизвестен");
  assert.match(quotaText({ state: "exhausted", usedPercent: 100, resetsAt: Date.UTC(2026, 10, 5, 9, 0) / 1000 }, before), /^Использовано 100 % · лимит исчерпан · сброс \d+ нояб\./u);
});

test("a reading names when it was read, and once its reset has passed the use is unknown until the next one (T9)", () => {
  // Midday UTC keeps the reading and `now` on one local day in the zones the tests run in.
  const now = Date.UTC(2026, 10, 11, 12, 30), readAt = Date.UTC(2026, 10, 11, 12, 0) / 1000;
  const spent = { state: "exhausted" as const, usedPercent: 100, resetsAt: Date.UTC(2026, 10, 12, 12, 0) / 1000, readAt };
  assert.match(quotaText(spent, now), /^Использовано 100 % · лимит исчерпан · сброс \d+ нояб\., \d\d:\d\d · данные на \d\d:\d\d$/u);
  const passed = { state: "available" as const, usedPercent: 61, resetsAt: Date.UTC(2026, 10, 11, 12, 15) / 1000, readAt };
  assert.match(quotaText(passed, now), /^Расход неизвестен · сброс прошёл · данные на \d\d:\d\d$/u);
  assert.equal(quotaText({ ...spent, resetsAt: passed.resetsAt }, now), quotaText(passed, now), "a passed reset ends «лимит исчерпан» too");
  // A reading of another day carries its date.
  assert.match(quotaText({ ...passed, resetsAt: null, readAt: readAt - 86_400 }, now), /^Использовано 61 % · данные на \d+ нояб\., \d\d:\d\d$/u);
  // The card's bar shows the share while it holds and goes with the reset.
  const card = (resetsAt: number) => connections({ ...provider, state: "connected", quota: { ...passed, resetsAt } });
  assert.match(card(4_000_000_000), /quota-bar/u);
  assert.ok(!card(1_000_000_000).includes("quota-bar"));
  assert.match(card(1_000_000_000), /Расход неизвестен · сброс прошёл/u);
});

test("a signed-in card names its account and offers the sign-out; a signed-out one offers the clearing (D158)", () => {
  const account = "fictional@example.invalid · Fictional Team";
  const signedIn = connections({ ...provider, state: "connected", plan: "max", ownProfile: true, account });
  assert.match(signedIn, /<div class="provider-actions">.*Выйти из аккаунта/u);
  assert.match(signedIn, /Аккаунт: fictional@example\.invalid · Fictional Team/u);
  assert.ok(!signedIn.includes("Очистить данные") && !signedIn.includes("<dialog"), "nothing asks before a click");
  const signedOut = connections({ ...provider, ownProfile: true });
  assert.match(signedOut, /Очистить данные/u);
  assert.ok(!signedOut.includes("Выйти из аккаунта") && !signedOut.includes("Аккаунт:"));
  // Without the app's own profile the CLI would sign out the user's own: the card offers neither.
  for (const state of ["connected", "login_required"] as const) {
    const foreign = connections({ ...provider, state, ownProfile: false, account });
    assert.ok(!foreign.includes("Выйти из аккаунта") && !foreign.includes("Очистить данные"), state);
  }
  const leaving = connections({ ...provider, state: "connected", ownProfile: true },
    { activity: { claude_cli: { pending: true, detaching: false, error: null, leaving: "logout" } } });
  assert.match(leaving, /Выходим из аккаунта…/u);
  assert.ok(!leaving.includes("Проверяем…"), "the check button does not claim the sign-out");
  assert.match(connections(provider), /Вход, выход из аккаунта, установка и отключение останавливают работу моделей/u);
});

test("each new action asks once more, naming what it ends and what stays", () => {
  const entry: ProviderEntry = { ...provider, state: "connected", ownProfile: true, account: "fictional@example.invalid" };
  const question = (leaving: "logout" | "clear", value = entry) =>
    renderToStaticMarkup(createElement(LeaveDialog, { leaving, entry: value, close: () => {}, confirm: () => {} }));
  const out = question("logout");
  assert.match(out, /aria-label="Выйти из аккаунта Claude\?"/u);
  assert.match(out, /Приложение выйдет из аккаунта fictional@example\.invalid\./u);
  assert.match(out, /прервутся/u); assert.match(out, /в терминале и других программах останется/u);
  assert.match(out, /class="button quiet "[^>]*><span[^>]*>Отмена</u); assert.match(out, /class="button primary "[^>]*><span[^>]*>Выйти</u);
  assert.match(question("logout", { ...entry, account: null }), /Приложение выйдет из аккаунта\. /u);
  const clear = question("clear", { ...entry, state: "login_required", account: null });
  assert.match(clear, /aria-label="Очистить данные Claude\?"/u);
  assert.match(clear, /Резюме и шаблоны не изменятся/u); assert.match(clear, /class="button danger "[^>]*><span[^>]*>Очистить</u);
});
