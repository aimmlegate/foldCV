import assert from "node:assert/strict";
import test from "node:test";
import { pageRules, printHint, unitPages, type Unit } from "../src/workbench/files/print";
import { projectStem } from "../src/workbench/files/filename";

const unit = (top: number, bottom: number, keep = false): Unit => ({ top, bottom, keep });

test("the paper is the template's size with no print margin: each page copy carries the template's own", () => {
  assert.equal(pageRules({ width: 596, height: 842, continuation_body_top: 24, body_bottom: 770 }), "@page { size: 596pt 842pt; margin: 0; }");
});

test("blocks fill the first page down to the body's bottom and a later page from the block that did not fit", () => {
  const units = [unit(0, 100), unit(100, 200), unit(200, 300), unit(300, 400), unit(400, 500), unit(500, 600), unit(600, 700)];
  assert.deepEqual(unitPages(units, 400, 250), [0, 0, 0, 0, 1, 1, 2]);
  assert.deepEqual(unitPages([], 400, 250), []);
});

test("a heading never ends a page: it moves with the block under it", () => {
  assert.deepEqual(unitPages([unit(0, 300), unit(310, 330, true), unit(330, 420)], 400, 400), [0, 1, 1]);
  // Two headings in a row keep together with the text under the second.
  assert.deepEqual(unitPages([unit(0, 300), unit(310, 330, true), unit(330, 350, true), unit(350, 420)], 400, 400), [0, 1, 1, 1]);
});

test("overlapping units share a page, and a block taller than a page gets one of its own", () => {
  assert.deepEqual(unitPages([unit(0, 100), unit(350, 395), unit(390, 420)], 400, 400), [0, 1, 1]);
  assert.deepEqual(unitPages([unit(0, 100), unit(100, 900), unit(900, 950)], 400, 400), [0, 1, 2]);
  // The first block stays on the first page even when the header leaves it no room.
  assert.deepEqual(unitPages([unit(500, 600)], 400, 400), [0]);
});

test("the print window names the PDF after the resume, and the hint says where each window saves it", () => {
  assert.equal(projectStem(" ../CV/Name\n\u0000:*? "), "CV Name");
  assert.equal(projectStem("..."), "resume");
  assert.match(printHint("macos"), /«PDF».*«Сохранить как PDF»/u);
  assert.match(printHint("windows"), /«Microsoft Print to PDF»/u);
  assert.match(printHint("browser"), /«Сохранить как PDF»/u);
});
