import assert from "node:assert/strict";
import test from "node:test";
import { plainActivity } from "../src/workbench/assistant/activity";
import { modelChoices } from "../src/workbench/assistant/model-choices";

test("activity titles drop markdown marks and keep the words", () => {
  assert.equal(plainActivity("**Кратко** про `резюме`"), "Кратко про резюме");
  assert.equal(plainActivity("# Заголовок\n\n__ещё__"), "Заголовок\n\nещё");
  assert.equal(plainActivity("```\nкод\n``` осталось"), "осталось");
  assert.equal(plainActivity("file_name и обычный текст"), "file_name и обычный текст");
  assert.equal(plainActivity("   "), "");
  assert.equal(plainActivity("**"), "");
  assert.equal(plainActivity("строка # не заголовок"), "строка # не заголовок");
  assert.equal(plainActivity("***жирное***"), "*жирное*");
});

test("a saved model is unavailable only when a ready catalog lists other models", () => {
  const catalog = [{ model: "gpt-6-luna", state: "verified" }];
  assert.deepEqual(modelChoices("gpt-6-luna", catalog, true), catalog);
  assert.deepEqual(modelChoices("gpt-6-luna", catalog, false), catalog);
  assert.deepEqual(modelChoices("saved", [], false), [{ model: "saved", state: "unverified" }]);
  assert.deepEqual(modelChoices("saved", [], true), [{ model: "saved", state: "unverified" }]);
  assert.deepEqual(modelChoices("saved", catalog, false), [{ model: "saved", state: "unverified" }, ...catalog]);
  assert.deepEqual(modelChoices("saved", catalog, true), [{ model: "saved", state: "unavailable" }, ...catalog]);
  assert.deepEqual(modelChoices("", catalog, true), catalog);
});
