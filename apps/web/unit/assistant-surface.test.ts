import assert from "node:assert/strict";
import test from "node:test";
import { plainActivity } from "../src/workbench/assistant/activity";
import { choiceGroups, modelChoices } from "../src/workbench/assistant/model-choices";

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

test("the composer groups models by provider as Settings does; one provider stays a plain list", () => {
  const codex = { model: "gpt-6-luna", state: "verified", provider: "Codex" }, claude = { model: "claude-opus-5-5", state: "unverified", provider: "Claude" };
  const second = { model: "gpt-6-sol", state: "unverified", provider: "Codex" };
  assert.deepEqual(choiceGroups([codex, claude, second]), [{ label: "Codex", choices: [codex, second] }, { label: "Claude", choices: [claude] }]);
  assert.deepEqual(choiceGroups([codex, second]), [{ label: null, choices: [codex, second] }]);
  const saved = { model: "saved", state: "unavailable" };
  assert.deepEqual(choiceGroups([saved, codex, claude]), [{ label: null, choices: [saved] }, { label: "Codex", choices: [codex] }, { label: "Claude", choices: [claude] }]);
  assert.deepEqual(choiceGroups([]), [{ label: null, choices: [] }]);
});
