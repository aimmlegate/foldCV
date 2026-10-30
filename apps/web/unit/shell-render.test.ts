import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { Header } = await import("../src/workbench/layout/Header");
const { DeleteDialog } = await import("../src/workbench/layout/History");
const { enterOption } = await import("../src/workbench/facts/FocusIconDialog");
const { PreDraft } = await import("../src/workbench/import/PreDraft");

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
