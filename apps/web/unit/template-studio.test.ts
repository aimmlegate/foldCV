import assert from "node:assert/strict";
import test from "node:test";
import { screenTitle, visit, type Screen } from "../src/workbench/templates/screen";
import { draftLabel, shownId, templateKind, unsaved, type ShownTemplate } from "../src/workbench/templates/studio";

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
