import assert from "node:assert/strict";
import test from "node:test";
import { screenTitle, visit, type Screen } from "../src/workbench/templates/screen";
import { deleteControl, downloadName, draftLabel, menuActions, shownId, templateKind, unsaved, type ShownTemplate } from "../src/workbench/templates/studio";

const state = { package: { id: "generic", name: "Две колонки", revision: "1.3.0", packageHash: "a".repeat(64) }, format: "yaml" as const,
  text: "template: {}\n", bundled: true, edited: false };

test("the header names Settings and templates; the resume screen keeps the resume's title", () => {
  assert.equal(screenTitle("resume", "Синтетическое резюме"), "Синтетическое резюме");
  assert.equal(screenTitle("settings", "Синтетическое резюме"), "Настройки");
  assert.equal(screenTitle("templates", "Синтетическое резюме"), "Шаблоны");
});

test("a visited screen stays mounted: visiting again keeps the same set", () => {
  let visited: ReadonlySet<Screen> = new Set();
  visited = visit(visited, "templates");
  const again = visit(visited, "templates");
  assert.equal(again, visited);
  visited = visit(visit(visited, "resume"), "settings");
  assert.deepEqual([...visited].sort(), ["resume", "settings", "templates"]);
});

test("the list says shipped, edited or own, and the editor knows unsaved text", () => {
  assert.equal(templateKind({ bundled: true, edited: false }), "встроенный");
  assert.equal(templateKind({ bundled: true, edited: true }), "изменён");
  assert.equal(templateKind({ bundled: false, edited: false }), "свой");
  const saved: ShownTemplate = { kind: "saved", state }, draft: ShownTemplate = { kind: "draft", name: "Мой", assetsFrom: "generic" };
  assert.equal(shownId(saved), "generic");
  assert.equal(shownId(draft), null);
  assert.equal(shownId(null), null);
  assert.equal(unsaved(saved, state.text), false);
  assert.equal(unsaved(saved, `${state.text}# edit\n`), true);
  assert.equal(unsaved(draft, ""), true);
  assert.equal(unsaved(null, "x"), false);
  assert.equal(draftLabel("Мой"), "Мой (не сохранён)");
});

test("delete is hidden on shipped templates and disabled on the default; downloads are named by id", () => {
  assert.equal(deleteControl({ id: "generic", bundled: true }, "custom-moy"), "hidden");
  assert.equal(deleteControl({ id: "custom-moy", bundled: false }, "custom-moy"), "disabled");
  assert.equal(deleteControl({ id: "custom-moy", bundled: false }, "generic"), "enabled");
  assert.equal(downloadName({ kind: "saved", state }), "generic.yaml");
  assert.equal(downloadName({ kind: "draft", name: "Мой", assetsFrom: null }), "template.yaml");
});

test("the «⋯» menu offers only what applies to the shown template", () => {
  const saved = (bundled: boolean, edited: boolean, id = bundled ? "generic" : "custom-moy"): ShownTemplate =>
    ({ kind: "saved", state: { ...state, package: { ...state.package, id }, bundled, edited } });
  const offered = (shown: ShownTemplate | null, defaultId: string | null) =>
    Object.entries(menuActions(shown, defaultId)).filter(([, choice]) => choice !== "hidden").map(([action, choice]) => `${action}:${choice}`);
  // A shipped default: no reset until edited, never a delete.
  assert.deepEqual(offered(saved(true, false), "generic"), ["copy:enabled", "download:enabled"]);
  assert.deepEqual(offered(saved(true, true), "generic"), ["copy:enabled", "download:enabled", "reset:enabled"]);
  assert.deepEqual(offered(saved(true, false), "custom-moy"), ["copy:enabled", "default:enabled", "download:enabled"]);
  // An own template is deleted, except while it is the default.
  assert.deepEqual(offered(saved(false, true), "generic"), ["copy:enabled", "default:enabled", "download:enabled", "delete:enabled"]);
  assert.deepEqual(offered(saved(false, true), "custom-moy"), ["copy:enabled", "download:enabled", "delete:disabled"]);
  // A new template exists only in the editor until saved.
  assert.deepEqual(offered({ kind: "draft", name: "Мой", assetsFrom: "generic" }, "generic"), ["download:enabled"]);
  assert.deepEqual(offered(null, "generic"), []);
});
