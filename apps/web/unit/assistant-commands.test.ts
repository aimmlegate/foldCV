import assert from "node:assert/strict";
import test from "node:test";
import { commandCompletion, commandSuggestions } from "../src/assistant/commands";

test("slash suggestions require a command at the start and stop when its arguments begin", () => {
  assert.deepEqual(commandSuggestions("/").map(item => item.command), ["/skills", "/import-resume", "/format-resume"]);
  assert.deepEqual(commandSuggestions("/fo").map(item => item.command), ["/format-resume"]);
  for (const value of ["", "Use /skills", "/skills ", "/skills\n", "/unknown", "/format-resume fix it"]) {
    assert.deepEqual(commandSuggestions(value), [], value);
  }
});

test("completion follows the selected command while exact Enter sends and Tab completes", () => {
  assert.equal(commandCompletion("/", 1, "Enter", false, false), "/import-resume ");
  assert.equal(commandCompletion("/fo", 0, "Tab", false, false), "/format-resume ");
  assert.equal(commandCompletion("/skills", 0, "Enter", false, false), null);
  assert.equal(commandCompletion("/skills", 0, "Tab", false, false), "/skills ");
  assert.equal(commandCompletion("/", 50, "Enter", false, false), null);
});

test("composition, Shift+Enter and unrelated keys never choose a command", () => {
  assert.equal(commandCompletion("/", 0, "Enter", true, false), null);
  assert.equal(commandCompletion("/", 0, "Enter", false, true), null);
  assert.equal(commandCompletion("/", 0, "ArrowDown", false, false), null);
});
