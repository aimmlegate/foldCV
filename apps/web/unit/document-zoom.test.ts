import assert from "node:assert/strict";
import test from "node:test";
import { fittedZoom, parseZoom } from "../src/workbench/editor/document-zoom";

test("the page follows the free width and never grows past the reading scale", () => {
  assert.equal(fittedZoom(800, 800), 1);
  assert.equal(fittedZoom(2000, 800), 1.25);
  assert.equal(fittedZoom(100, 800), 0.5);
  assert.equal(fittedZoom(-200, 800), 0.5, "a pane narrower than the Facts strip still shows the page");
});

test("a stored scale outside the offered levels means fit", () => {
  assert.equal(parseZoom("0.75"), 0.75);
  assert.equal(parseZoom("3"), "fit");
  assert.equal(parseZoom(null), "fit");
});
