import assert from "node:assert/strict";
import test from "node:test";
import { call, removeNewerJavaScript } from "./support/old-webkit";

test("the PDF worker entry brings what pdf.js needs to the JavaScript of Safari 16.4", async () => {
  removeNewerJavaScript();
  // A worker has its own globals: the page's polyfills do not reach it. Without them old WebKit drew empty pages.
  await import("../src/workbench/editor/pdf.worker");
  const made = call(Promise, "withResolvers");
  assert.ok(typeof made === "object" && made !== null && "promise" in made && "resolve" in made && "reject" in made);
  assert.ok(made.promise instanceof Promise && typeof made.resolve === "function" && typeof made.reject === "function");
  Reflect.apply(made.resolve, undefined, ["done"]);
  assert.equal(await made.promise, "done");
  const cut = (length?: number) => {
    const moved = call(new Uint8Array([1, 2, 3]).buffer, "transferToFixedLength", ...(length === undefined ? [] : [length]));
    assert.ok(moved instanceof ArrayBuffer);
    return [...new Uint8Array(moved)];
  };
  assert.deepEqual([cut(2), cut(), cut(5)], [[1, 2], [1, 2, 3], [1, 2, 3, 0, 0]]);
  // The pdf.js worker itself loaded after them.
  assert.equal(typeof Reflect.get(globalThis, "pdfjsWorker"), "object");
});
