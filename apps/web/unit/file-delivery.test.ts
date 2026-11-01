import assert from "node:assert/strict";
import test from "node:test";
import { deliveryMessage, deliveryState } from "../src/workbench/files/delivery";

test("the dialog confirms a saved file by name and stays quiet after a cancelled save", () => {
  assert.equal(deliveryMessage({ state: "saved", name: "Alex Example.docx" }), "Файл сохранён: Alex Example.docx");
  assert.equal(deliveryMessage({ state: "started", name: "Alex Example.docx" }), "Скачивание началось.");
  assert.equal(deliveryMessage({ state: "cancelled", name: "Alex Example.docx" }), "");
  assert.equal(deliveryMessage(null), "");
});

test("a save the shell did not finish is a failure unless the user cancelled it", () => {
  assert.equal(deliveryState("completed"), "saved");
  assert.equal(deliveryState("cancelled"), "cancelled");
  assert.equal(deliveryState("interrupted"), "failed");
});
