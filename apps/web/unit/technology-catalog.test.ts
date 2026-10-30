import assert from "node:assert/strict";
import test from "node:test";
import type { WorkingFacts } from "../src/contracts/generated/working_facts";
import { technologySuggestions } from "../src/workbench/facts/technology-catalog";

function facts(display: string): WorkingFacts {
  return { records: [{ kind: "candidate", name: { rawText: "Alex Example" } }, { kind: "technology", display: { rawText: display } }] } as unknown as WorkingFacts;
}

// A blank name once kept this search spinning: the page froze on every open of the project.
for (const blank of ["", "   "]) test(`a blank technology name offers nothing and ends the search (${JSON.stringify(blank)})`, () => {
  const names = technologySuggestions(facts(blank), null, "");
  assert.ok(names.length > 0);
  assert.ok(names.every(name => name.trim()));
});

test("a named technology stays among the suggestions", () => {
  assert.ok(technologySuggestions(facts("Dart Frog"), null, "dart").includes("Dart Frog"));
});
