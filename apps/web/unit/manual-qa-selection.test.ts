import assert from "node:assert/strict";
import test from "node:test";
import { limitsEditToSelection } from "../src/assistant/selection-intent";

test("selection is context unless the command explicitly limits the edit", () => {
  for (const message of ["Отформатируй всё резюме", "Перепиши другой раздел", "Измени не только выделенное", "Not only the selected text", "Just format the whole resume"]) {
    assert.equal(limitsEditToSelection(message), false, message);
  }
  for (const message of ["Перепиши только выделенный текст", "Исправь лишь в выделенном", "Сократи только этот фрагмент", "Rewrite only the selected text", "Change just this passage"]) {
    assert.equal(limitsEditToSelection(message), true, message);
  }
});
