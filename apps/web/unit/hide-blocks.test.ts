import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/contracts";
import { employment, facts as synthetic, technology } from "./support/facts";
import { panelCommandsV7, type PanelPlan } from "../src/rich/v7-panel";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { FactsPanel } = await import("../src/workbench/facts/FactsPanel");

const response = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const document = response.workspace.project!.document;
const jobs = [employment("job-a", "Alpha Works"), employment("job-b", "Beta Labs"), employment("job-c", "Gamma Group")];

function panel(plan: PanelPlan, extra: Record<string, unknown> = {}) {
  return renderToStaticMarkup(createElement(FactsPanel, { facts: synthetic([...jobs, technology("tech-1", "Python")]), document,
    submit: async () => {}, pending: [], paused: false, hidden: false, close: () => {}, plan,
    technologyTargets: [{ blockId: "view:programming", jobId: null, label: "Языки программирования", placement: { parentId: "r", afterId: null }, records: ["tech-1"] }],
    anchors: new Map([["employment", "block-1"], ["education", "block-2"]]),
    focusEntries: [{ recordId: "tech-1", display: "Python", years: 3, detail: "3 года", icon: null, chosen: false }], ...extra }));
}
function button(markup: string, label: string): string {
  const found = markup.match(new RegExp(`<button[^>]*aria-label="${label}"[^>]*>`, "u"));
  assert.ok(found, label);
  return found[0];
}
const blocks: PanelPlan["hideBlocks"] = [
  { id: "view:projects", name: "ПРОЕКТЫ", place: "group", kind: "employment", hidden: false },
  { id: "view:focus", name: "ФОКУС", place: "focus", hidden: false },
  { id: "view:programming", name: "ЯП", place: "technology", hidden: true },
  { id: "view:summary", name: "О СЕБЕ", place: "other", hidden: false },
  { id: "view:opensource", name: "OPEN SOURCE", place: "other", hidden: true },
];

test("each job with a card has an eye before the remove button; pressed and «Скрыто» while hidden; locked inside a hidden block", () => {
  const markup = panel({ jobs: { "job-a": { periods: [], eye: "shown" }, "job-b": { periods: [], eye: "hidden" }, "job-c": { periods: [], eye: "locked" } },
    offPage: ["job-b"] });
  assert.match(button(markup, "Скрыть: Alpha Works"), /aria-pressed="false"/u);
  assert.doesNotMatch(button(markup, "Скрыть: Alpha Works"), /disabled/u);
  assert.match(button(markup, "Показать: Beta Labs"), /aria-pressed="true"/u);
  assert.match(button(markup, "Скрыть: Gamma Group"), /disabled/u);
  assert.ok(markup.indexOf("Скрыть: Alpha Works") < markup.indexOf("Удалить: Alpha Works"));
  const beta = markup.slice(markup.indexOf('data-fact-id="job-b"'), markup.indexOf('data-fact-id="job-c"'));
  assert.match(beta, /data-hidden="true"/u);
  assert.match(beta, /Скрыто/u);
  // The eye says what «Не на странице» said: no second way back under the row.
  assert.ok(!beta.includes("Вернуть на страницу"));
  assert.match(markup, /data-fact-id="job-c"[^>]*data-locked="true"/u);
});

test("a job with no card of its own has no eye", () => {
  const markup = panel({ jobs: { "job-a": { periods: [] } } });
  assert.ok(!markup.includes("Скрыть: Alpha Works") && !markup.includes("Показать: Alpha Works"));
});

test("a group that shows one block carries its eye beside the jump, outside the summary; a hidden one has no jump", () => {
  const shown = panel({ hideBlocks: blocks });
  const frame = shown.slice(shown.indexOf('data-group="employment"') - 80, shown.indexOf('data-group="technology"'));
  assert.match(frame, /<span class="fact-group-eye"><button[^>]*aria-label="Скрыть: ПРОЕКТЫ"/u);
  assert.ok(frame.indexOf("</summary>") < frame.indexOf("Скрыть: ПРОЕКТЫ"));
  assert.ok(frame.includes("Показать в резюме: Опыт"));
  const hidden = panel({ hideBlocks: blocks.map(block => block.id === "view:projects" ? { ...block, hidden: true } : block) });
  const hiddenFrame = hidden.slice(hidden.indexOf('data-group="employment"') - 80, hidden.indexOf('data-group="technology"'));
  assert.ok(hiddenFrame.includes("Показать: ПРОЕКТЫ") && !hiddenFrame.includes("Показать в резюме: Опыт") && hiddenFrame.includes("Скрыто"));
  assert.match(hidden, /class="fact-group-frame" data-hidden="true"/u);
});

test("the technology group and the Focus part carry their eyes at their titles", () => {
  const markup = panel({ hideBlocks: blocks });
  const group = markup.slice(markup.indexOf('aria-label="Категория: Языки программирования"'));
  assert.match(group, /data-hidden="true"/u);
  assert.ok(group.indexOf("Показать: ЯП") < group.indexOf("Технологии категории"));
  assert.match(markup, /Фокус · лет опыта<button[^>]*aria-label="Скрыть: ФОКУС"/u);
});

test("«Другие блоки» is the last group, one row for each block, and absent when there is none", () => {
  const markup = panel({ hideBlocks: blocks });
  const other = markup.slice(markup.indexOf('data-group="blocks"'));
  assert.ok(markup.indexOf('data-group="blocks"') > markup.indexOf('data-group="language"'));
  assert.match(other, /<summary>Другие блоки<\/summary>/u);
  assert.equal(other.match(/class="fact-row fact-block-row"/gu)?.length, 2);
  assert.ok(other.includes("Скрыть: О СЕБЕ") && other.includes("Показать: OPEN SOURCE"));
  assert.match(other, /data-block="view:opensource" data-hidden="true"/u);
  assert.ok(!panel({ hideBlocks: blocks.filter(block => block.place !== "other") }).includes("Другие блоки"));
});

test("a hidden Focus block with no rows on the page keeps its part and its eye", () => {
  const markup = panel({ hideBlocks: [{ id: "view:focus", name: "ФОКУС", place: "focus", hidden: true }] }, { focusEntries: [] });
  assert.match(markup, /class="focus-years" aria-label="Фокус" data-hidden="true"/u);
  assert.match(button(markup, "Показать: ФОКУС"), /aria-pressed="true"/u);
});

test("every eye is disabled while a panel command is pending", () => {
  const markup = panel({ hideBlocks: blocks, jobs: { "job-a": { periods: [], eye: "shown" } } }, { pending: [{ operation: "hide" }] });
  for (const label of ["Скрыть: Alpha Works", "Скрыть: ПРОЕКТЫ", "Скрыть: ФОКУС", "Показать: ЯП", "Скрыть: О СЕБЕ"])
    assert.match(button(markup, label), /disabled/u, label);
});

test("the V7 path takes a hide or show of one job or one block, and nothing else of them", () => {
  const kinds = new Map([["job-a", "employment"], ["tech-1", "technology"]]);
  assert.deepEqual(panelCommandsV7({ operation: "hide", recordId: "job-a" }, kinds), [{ operation: "hide", recordId: "job-a" }]);
  assert.deepEqual(panelCommandsV7({ operation: "show", values: { view: "summary" } }, kinds), [{ operation: "show", values: { view: "summary" } }]);
  assert.equal(panelCommandsV7({ operation: "hide", recordId: "tech-1" }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "hide", recordId: "job-a", values: { view: "summary" } }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "show", values: { view: "summary", other: "x" } }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "hide" }, kinds), null);
});
