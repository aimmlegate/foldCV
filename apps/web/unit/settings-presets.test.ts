import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { commandsProblem, mergeCommands, presetBodies, withPresetBody } from "../src/workbench/settings/presets";

const defaults = readFileSync(new URL("../../../packages/resume_core/default_rules.md", import.meta.url), "utf8");

test("the default rules split into the two commands and come back byte for byte (D147)", () => {
  const bodies = presetBodies(defaults);
  assert.match(bodies.shorten ?? "", /^Сократи выбранный текст\..*новые сведения\.$/su);
  assert.match(bodies.clarify ?? "", /^Напиши выбранный текст яснее\..*новые сведения\.$/su);
  assert.equal(withPresetBody(defaults, "shorten", bodies.shorten ?? ""), defaults);
  // An edit keeps the file's layout: a blank line after the heading and before the next one.
  const edited = withPresetBody(defaults, "shorten", "Короче.");
  assert.equal(edited, defaults.replace(/(## Preset: shorten\n\n)[^#]*?(\n\n## Preset: clarify)/u, "$1Короче.$2"));
  assert.deepEqual({ ...presetBodies(edited), repeated: false }, { shorten: "Короче.", clarify: bodies.clarify, repeated: false });
  assert.equal(presetBodies(withPresetBody(edited, "clarify", "  Яснее.\n\n")).clarify, "Яснее.");
});

test("text outside the commands keeps every byte: a leading paragraph, a third heading and the end", () => {
  const text = "Мои заметки.\n\n## Preset: clarify\n\nЯснее.\n\n## Свой раздел\nНе трогать.\n\n## Preset: shorten\nКороче.";
  assert.deepEqual(presetBodies(text), { shorten: "Короче.", clarify: "Яснее.", repeated: false });
  const clarify = withPresetBody(text, "clarify", "Новое яснее.");
  assert.ok(clarify.startsWith("Мои заметки.\n\n## Preset: clarify\n\nНовое яснее.\n\n## Свой раздел\nНе трогать.\n\n## Preset: shorten\nКороче."));
  // The last body ended the file without a line break; its heading line keeps its own.
  const shorten = withPresetBody(text, "shorten", "Новое короче.");
  assert.equal(shorten, "Мои заметки.\n\n## Preset: clarify\n\nЯснее.\n\n## Свой раздел\nНе трогать.\n\n## Preset: shorten\n\nНовое короче.\n");
  assert.equal(presetBodies(shorten).shorten, "Новое короче.");
});

test("a heading inside a code fence is body text, as in rules.py", () => {
  const text = "## Preset: shorten\n\n```\n## Preset: clarify\n```\nКороче.\n\n## Preset: clarify\n\nЯснее.\n";
  assert.deepEqual(presetBodies(text), { shorten: "```\n## Preset: clarify\n```\nКороче.", clarify: "Яснее.", repeated: false });
  assert.equal(withPresetBody(text, "clarify", "Иначе."), "## Preset: shorten\n\n```\n## Preset: clarify\n```\nКороче.\n\n## Preset: clarify\n\nИначе.\n");
  // An unclosed fence swallows the next heading: that command is gone, which Python refuses.
  assert.equal(presetBodies("## Preset: shorten\n~~~\nКороче.\n## Preset: clarify\nЯснее.\n").clarify, null);
});

test("CRLF text reads like Python's splitlines, and untouched bytes stay CRLF", () => {
  const text = "Вступление.\r\n\r\n## Preset: shorten\r\n\r\nКороче.\r\nЕщё.\r\n\r\n## Preset: clarify\r\n\r\nЯснее.\r\n";
  assert.deepEqual(presetBodies(text), { shorten: "Короче.\nЕщё.", clarify: "Яснее.", repeated: false });
  assert.equal(withPresetBody(text, "shorten", "Короче.\nЕщё."), text);
  const edited = withPresetBody(text, "clarify", "Иначе.");
  assert.ok(edited.startsWith("Вступление.\r\n\r\n## Preset: shorten\r\n\r\nКороче.\r\nЕщё.\r\n\r\n## Preset: clarify\r\n"));
  assert.equal(presetBodies(edited).clarify, "Иначе.");
});

test("a missing command goes to the end; a repeated heading is reported", () => {
  assert.equal(withPresetBody("## Preset: shorten\n\nКороче.\n", "clarify", "Яснее."), "## Preset: shorten\n\nКороче.\n\n## Preset: clarify\n\nЯснее.\n");
  assert.equal(withPresetBody("", "shorten", "Короче."), "## Preset: shorten\n\nКороче.\n");
  assert.deepEqual(presetBodies("Только текст.\n"), { shorten: null, clarify: null, repeated: false });
  assert.equal(presetBodies("## Preset: shorten\nA\n## Preset: shorten\nB\n## Preset: clarify\nC\n").repeated, true);
});

test("a field that would break its command is caught before the save", () => {
  const typed = (shorten: string, clarify: string) => commandsProblem(withPresetBody(withPresetBody(defaults, "shorten", shorten), "clarify", clarify), { shorten, clarify });
  assert.equal(typed("Короче.", "Яснее."), null);
  assert.equal(typed("Короче.   ", "Яснее.\n"), null);
  assert.match(typed(" ", "Яснее.") ?? "", /Заполните обе команды/u);
  assert.match(typed("Короче.\n## Пример", "Яснее.") ?? "", /разрывает команду/u);
  assert.match(typed("```\nКороче.", "Яснее.") ?? "", /разрывает команду/u);
  assert.equal(typed("```\n## Пример\n```", "Яснее."), null);
});

test("after another window saved, the edits here go onto its text: its own changes and outside text stay", () => {
  const theirs = `Заметки другого окна.\n\n${withPresetBody(defaults, "shorten", "Их короче.")}\n## Свой раздел\nТекст.\n`;
  const mine = withPresetBody(defaults, "clarify", "Моё яснее.");
  const merged = mergeCommands(theirs, defaults, mine);
  assert.deepEqual(presetBodies(merged), { shorten: "Их короче.", clarify: "Моё яснее.", repeated: false });
  assert.ok(merged.startsWith("Заметки другого окна.\n\n") && merged.endsWith("## Свой раздел\nТекст.\n"));
  // Nothing changed here: the saved text as it is.
  assert.equal(mergeCommands(theirs, defaults, defaults), theirs);
});
