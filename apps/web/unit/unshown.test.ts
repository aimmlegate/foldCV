import assert from "node:assert/strict";
import test from "node:test";
import { findLine, narrowed, pdfBoxes, textIndex, unshownLabels, unshownLines, unshownRanges, withChanged, type Unshown } from "../src/workbench/editor/unshown";

const issue = (code: string, message: string, state = "active") => ({ state, message, code, targetIds: ["scope-task"], blockIds: [] });

test("the import's notices give the unshown lines: one per text line, the words to mark after a tab", () => {
  assert.deepEqual(unshownLines([
    issue("IMPORT_LINES_NO_FIELD", "Java, Kafka, управление командой\tкомандой управление\nСентябрь 2017 — по настоящее время"),
    issue("IMPORT_LINES_HIDDEN", "nina@example.org"),
    issue("IMPORT_LINES_DROPPED", "Старый стек", "retired"),
    issue("IMPORT_SOURCE_FALLBACK", "Показан исходный текст."),
  ]), [
    { reason: "no_field", text: "Java, Kafka, управление командой", words: ["командой", "управление"] },
    { reason: "no_field", text: "Сентябрь 2017 — по настоящее время", words: null },
    { reason: "hidden", text: "nina@example.org", words: null },
    { reason: "dropped", text: "Старый стек", words: null },
  ]);
});

test("the lines the present document changed join the import's lines, one row per line text", () => {
  const lines: Unshown[] = [{ reason: "no_field", text: "Java — около 5 лет, управление", words: ["около"] },
    { reason: "hidden", text: "nina@example.org", words: null }];
  assert.deepEqual(withChanged(lines, [{ text: "Java — около 5 лет, управление", words: ["около", "управление"] },
    { text: "nina@example.org", words: ["nina"] }, { text: "Перевела расчёты с Oracle", words: ["перевела", "расчеты"] },
    { text: "Старая строка", words: null }]), [
    { reason: "no_field", text: "Java — около 5 лет, управление", words: ["около", "управление"] },
    { reason: "hidden", text: "nina@example.org", words: null },
    { reason: "changed", text: "Перевела расчёты с Oracle", words: ["перевела", "расчеты"] },
    { reason: "changed", text: "Старая строка", words: null }]);
});

test("a line of a fact that left the page keeps Python's reason «removed» with its own label (D179)", () => {
  const rows = withChanged([], [{ text: "Учебный центр, 2019", words: null, reason: "removed" },
    { text: "Перевела расчёты с Oracle", words: ["перевела"], reason: "changed" }, { text: "Старая строка", words: null }]);
  assert.deepEqual(rows.map(row => row.reason), ["removed", "changed", "changed"]);
  assert.equal(unshownLabels.removed, "удалено из резюме");
});

test("a line is found across pieces whatever the spacing, and a second equal line takes the next place", () => {
  // A viewer may break a line into runs and space it otherwise than the parser did.
  const pieces = ["Опыт  работы", "Сентябрь 2017 —", " по настоящее время", "Java", "Сентябрь 2017 — по настоящее время"];
  const index = textIndex(pieces);
  assert.deepEqual(findLine(index, "Сентябрь 2017 — по настоящее время"), [{ piece: 1, start: 0, end: 15 }, { piece: 2, start: 1, end: 19 }]);
  assert.deepEqual(findLine(index, "сентябрь 2017 — по настоящее время"), [{ piece: 4, start: 0, end: 34 }], "the next place; case is form");
  assert.equal(findLine(index, "Сентябрь 2017 — по настоящее время"), null, "no third place");
  assert.equal(findLine(index, "Нет такой строки"), null);
});

test("a short line is found as whole words, never inside a longer word", () => {
  // «Java» is no part of «JavaScript»: the line found is the one that stands alone, on its own piece or between spaces.
  const pieces = ["JavaScript, TypeScript", "Java", "GitLab и Git"];
  assert.deepEqual(findLine(textIndex(pieces), "Java"), [{ piece: 1, start: 0, end: 4 }]);
  assert.deepEqual(findLine(textIndex(pieces), "Git"), [{ piece: 2, start: 9, end: 12 }]);
  assert.equal(findLine(textIndex(["JavaScript"]), "Java"), null);
  // Punctuation parts words too.
  assert.deepEqual(findLine(textIndex(["(Java)"]), "Java"), [{ piece: 0, start: 1, end: 5 }]);
});

test("a partly shown line marks only its unshown words", () => {
  const pieces = ["Java, Spring Boot, Kafka, управление командой"];
  const segments = findLine(textIndex(pieces), pieces[0] ?? "") ?? [];
  const marked = narrowed(pieces, segments, ["управление", "командой"]).map(range => (pieces[0] ?? "").slice(range.start, range.end));
  assert.deepEqual(marked, ["управление", "командой"]);
  assert.deepEqual(narrowed(pieces, segments, null), segments, "no words: the whole line");
});

test("the ranges carry each line's reason, and a PDF box takes a run's share by its characters", () => {
  const lines: Unshown[] = [{ reason: "hidden", text: "nina@example.org", words: null },
    { reason: "no_field", text: "Java, Kafka, управление", words: ["управление"] }];
  assert.deepEqual(unshownRanges(["Нина Ростова", "nina@example.org", "Java, Kafka, управление"], lines),
    [{ piece: 1, start: 0, end: 16, reason: "hidden" }, { piece: 2, start: 13, end: 23, reason: "no_field" }]);
  const run = (str: string, x: number, y: number, width: number) => ({ str, transform: [10, 0, 0, 10, x, y], width, height: 10 });
  // «управление» is the last 10 of 23 characters of a run 230 units wide that starts at x = 50.
  assert.deepEqual(pdfBoxes([run("nina@example.org", 50, 700, 160), run("Java, Kafka, управление", 50, 680, 230)], lines), [
    { reason: "hidden", left: 50, right: 210, bottom: 697.5, top: 709.5 },
    { reason: "no_field", left: 180, right: 280, bottom: 677.5, top: 689.5 },
  ]);
  // A PDF stored «2017 —» before «Сентябрь» on one baseline, and an empty run between: the line is read left to right.
  const period: Unshown[] = [{ reason: "no_field", text: "Сентябрь 2017 — по настоящее время", words: null }];
  const stored = [run("", 142, 524, 0), run("2017 —", 142, 524, 38), run("Сентябрь", 90, 524, 50), run(" ", 140, 524, 2),
    run("по настоящее время", 182, 524, 105), run("Руководитель группы", 90, 500, 120)];
  assert.deepEqual(pdfBoxes(stored, period).map(box => [box.left, box.right]), [[90, 140], [142, 180], [182, 287]]);
});
