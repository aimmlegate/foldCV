import assert from "node:assert/strict";
import test from "node:test";
import { textChanges, type TextPart } from "../src/rich/text-changes";

const part = (text: string, changed = false): TextPart => ({ text, changed });
/** The parts of both sides; each side must give back its whole text, since the marks are laid over that text. */
function compare(before: string, after: string) {
  const result = textChanges(before, after);
  assert.equal(result.before.map(value => value.text).join(""), before);
  assert.equal(result.after.map(value => value.text).join(""), after);
  return result;
}

test("only the changed words are marked, hyphenated words stay whole and the marks do not take the spaces around them", () => {
  assert.deepEqual(compare("Собрал отчёты из Excel-таблиц, сохранив формулы.", "Собрал отчёты из общих таблиц, сохранив формулы."), {
    before: [part("Собрал отчёты из "), part("Excel-таблиц", true), part(", сохранив формулы.")],
    after: [part("Собрал отчёты из "), part("общих таблиц", true), part(", сохранив формулы.")] });
});

test("a reordered phrase is marked whole on both sides", () => {
  assert.deepEqual(compare("Хочу строить e-commerce backend и ускорять его", "Хочу строить backend для e-commerce и ускорять его"), {
    before: [part("Хочу строить "), part("e-commerce backend", true), part(" и ускорять его")],
    after: [part("Хочу строить "), part("backend для e-commerce", true), part(" и ускорять его")] });
});

test("a common comma inside a rewritten sentence does not split its marks", () => {
  assert.deepEqual(compare("Делал отчёты, выгрузки и графики", "Собрал панель, где видны итоги"), {
    before: [part("Делал отчёты, выгрузки и графики", true)], after: [part("Собрал панель, где видны итоги", true)] });
});

test("a changed sign is marked alone", () => {
  assert.deepEqual(compare("Знаю Python, Go.", "Знаю Python и Go."), {
    before: [part("Знаю Python"), part(",", true), part(" Go.")],
    after: [part("Знаю Python "), part("и", true), part(" Go.")] });
});

test("spaces and line breaks alone are no change", () => {
  assert.deepEqual(compare("Две  строки\nи пробелы", "Две строки и пробелы"), {
    before: [part("Две  строки\nи пробелы")], after: [part("Две строки и пробелы")] });
});

test("an emptied text marks all of the old one", () => {
  assert.deepEqual(compare("Текст есть", ""), { before: [part("Текст есть", true)], after: [] });
});

test("a middle past the matching limit is marked whole between the kept start and end", () => {
  const old = Array.from({ length: 1100 }, (_, index) => `старое${String(index)}`).join(" ");
  const fresh = Array.from({ length: 1000 }, (_, index) => `новое${String(index)}`).join(" ");
  assert.deepEqual(compare(`Начало ${old} конец`, `Начало ${fresh} конец`), {
    before: [part("Начало "), part(old, true), part(" конец")], after: [part("Начало "), part(fresh, true), part(" конец")] });
});
