import assert from "node:assert/strict";
import test from "node:test";
import { TIP_EDGE, tipPlace, type Box, type TipInput } from "../src/workbench/editor/remark-tip";
import { acceptTarget } from "../src/workbench/editor/RemarkTip";

// F1 of the tester feedback of 2026-11-23: the place of the tip of a mark. The delay is checked in the GUI only.
const box = (left: number, top: number, right: number, bottom: number): Box => ({ left, top, right, bottom });
const overlaps = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
// A tip 320 px wide is 90 px high; a narrower one is higher, as text wraps.
const heightAt = (width: number) => Math.round(90 * 320 / width);
const view = { width: 1400, height: 900 };
const tipBox = (place: ReturnType<typeof tipPlace>, input: TipInput) =>
  box(place.left, place.top, place.left + place.width, place.top + input.heightAt(place.width));
function block(paper: Box, first: Box, last: Box, button: Box | null = null, window = view): TipInput {
  return { window, heightAt, block: { first, last, paper, button } };
}
const lines = (input: TipInput) => {
  const value = input.block;
  assert.ok(value);
  return box(Math.min(value.first.left, value.last.left), value.first.top, Math.max(value.first.right, value.last.right), value.last.bottom);
};

test("a word mark: the tip stands under the hovered line, and above it when there is no room below", () => {
  const below = tipPlace({ window: view, heightAt, word: { line: box(300, 200, 500, 218), x: 360 } });
  assert.deepEqual(below, { place: "below", left: 336, top: 224, width: 320 });
  const above = tipPlace({ window: view, heightAt, word: { line: box(300, 820, 500, 838), x: 360 } });
  assert.deepEqual(above, { place: "above", left: 336, top: 820 - 6 - 90, width: 320 });
});

test("a block mark: (a) beside the block on the right of the paper, top at the top of the block", () => {
  const input = block(box(300, 0, 900, 2000), box(360, 400, 840, 418), box(360, 472, 700, 490));
  const place = tipPlace(input);
  assert.deepEqual(place, { place: "right", left: 912, top: 400, width: 320 });
  assert.equal(overlaps(tipBox(place, input), lines(input)), false);
});

test("a block mark: (a) is narrower when the room allows less than 320 px, and not under 200 px", () => {
  const narrow = tipPlace(block(box(300, 0, 1100, 2000), box(360, 400, 1040, 418), box(360, 472, 900, 490)));
  assert.deepEqual(narrow, { place: "right", left: 1112, top: 400, width: 1400 - 8 - 1112 });
  const none = tipPlace(block(box(150, 0, 1190, 2000), box(200, 400, 1100, 418), box(200, 472, 900, 490)));
  assert.notEqual(none.place, "right", "180 px of room is too little");
});

test("a block mark: (b) on the left of the paper when the right has no room", () => {
  const input = block(box(500, 0, 1250, 2000), box(560, 400, 1200, 418), box(560, 472, 900, 490));
  const place = tipPlace(input);
  assert.deepEqual(place, { place: "left", left: 500 - 12 - 320, top: 400, width: 320 });
  assert.equal(overlaps(tipBox(place, input), lines(input)), false);
});

test("a block mark: (c) above the first line, then (d) below the last line, when the paper fills the window", () => {
  const paper = box(0, -200, 1400, 3000);
  const above = block(paper, box(60, 400, 1300, 418), box(60, 472, 900, 490));
  const place = tipPlace(above);
  assert.deepEqual(place, { place: "above-block", left: 60, top: 400 - 6 - 90, width: 320 });
  assert.equal(overlaps(tipBox(place, above), lines(above)), false);
  const below = block(paper, box(60, 40, 1300, 58), box(60, 112, 900, 130));
  const second = tipPlace(below);
  assert.deepEqual(second, { place: "below-block", left: 60, top: 136, width: 320 });
  assert.equal(overlaps(tipBox(second, below), lines(below)), false);
});

test("a block mark: (e) at the top of the window when nothing else fits; there it may cover the block", () => {
  const input = block(box(0, -200, 1400, 3000), box(60, 40, 1300, 58), box(60, 830, 900, 848));
  assert.deepEqual(tipPlace(input), { place: "window-top", left: 60, top: TIP_EDGE, width: 320 });
});

test("the block's «Переписать» button: the tip stands below it", () => {
  const button = box(906, 400, 1010, 430);
  const input = block(box(300, 0, 900, 2000), box(360, 400, 840, 418), box(360, 472, 700, 490), button);
  const place = tipPlace(input);
  assert.deepEqual(place, { place: "right", left: 912, top: 436, width: 320 });
  assert.equal(overlaps(tipBox(place, input), button), false);
});

test("the tip stays 8 px inside the window on each side", () => {
  const small = { width: 600, height: 400 };
  const right = tipPlace({ window: small, heightAt, word: { line: box(500, 100, 590, 118), x: 580 } });
  assert.equal(right.left + right.width, small.width - TIP_EDGE);
  const left = tipPlace({ window: small, heightAt, word: { line: box(-40, 100, 50, 118), x: 0 } });
  assert.equal(left.left, TIP_EDGE);
  const top = tipPlace({ window: small, heightAt, word: { line: box(100, 20, 300, 38), x: 120 } });
  assert.ok(top.top >= TIP_EDGE);
  // A block that starts above the window: the tip beside it starts at the window's top edge, not above it.
  const scrolled = tipPlace(block(box(300, -900, 900, 2000), box(360, -300, 840, -282), box(360, 300, 700, 318)));
  assert.deepEqual([scrolled.place, scrolled.top], ["right", TIP_EDGE]);
  const tiny = tipPlace({ window: { width: 300, height: 400 }, heightAt, word: { line: box(10, 10, 100, 28), x: 20 } });
  assert.deepEqual([tiny.left, tiny.width], [TIP_EDGE, 300 - 2 * TIP_EDGE]);
});

test("«Принять» accepts the value of a word mark and the whole block of a block mark, only in a tip «Нет в оригинале» (D179)", () => {
  const remark = { messages: ["m"], recordId: null, added: true, blockId: null, cellId: null };
  assert.deepEqual(acceptTarget({ ...remark, cellId: "cell-1" }), { cellId: "cell-1" });
  assert.deepEqual(acceptTarget({ ...remark, blockId: "line-1" }), { blockId: "line-1" });
  assert.equal(acceptTarget({ ...remark, added: false, cellId: "cell-1" }), null, "a doubt has no «Принять»");
  assert.equal(acceptTarget(remark), null);
});
