import assert from "node:assert/strict";
import test, { mock } from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/contracts";
import { employment, facts as synthetic } from "./support/facts";
import { panelCommandsV7, type PanelPlan } from "../src/rich/v7-panel";
import { dateChecker, dateCheckDelay, dateWarningLines } from "../src/workbench/facts/dateCheck";
import { parseDateWarnings, type DateWarning } from "../src/projects/api";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { FactsPanel, groupRecords } = await import("../src/workbench/facts/FactsPanel");
const { FactDialog } = await import("../src/workbench/facts/FactDialog");
const { overlapLine } = await import("../src/workbench/facts/JobWarnings");

const response = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const document = response.workspace.project!.document;
const jobs = [employment("job-a", "Alpha Works"), employment("job-b", "Beta Labs"), employment("job-c", "Gamma Group"), employment("job-d", "Delta Ltd")];
const kinds = new Map(jobs.map(job => [job.id, "employment"]));

function panel(plan: PanelPlan, pending: readonly { operation: "move_job" }[] = []) {
  return renderToStaticMarkup(createElement(FactsPanel, { facts: synthetic(jobs), document, submit: async () => {}, pending,
    paused: false, hidden: false, close: () => {}, plan }));
}
function button(markup: string, label: string): string {
  const found = markup.match(new RegExp(`<button[^>]*aria-label="${label}"[^>]*>`, "u"));
  assert.ok(found, label);
  return found[0];
}

test("Facts lists jobs in the plan's page order and a job the plan does not name after them in record order", () => {
  const ordered = groupRecords(jobs, "employment", ["job-c", "job-a"]).map(record => record.id);
  assert.deepEqual(ordered, ["job-c", "job-a", "job-b", "job-d"]);
  assert.deepEqual(groupRecords(jobs, "employment", undefined).map(record => record.id), ["job-a", "job-b", "job-c", "job-d"]);
  const markup = panel({ jobOrder: ["job-d", "job-b", "job-a", "job-c"], jobs: {} });
  const rows = [...markup.matchAll(/data-fact-id="(job-[a-d])"/gu)].map(match => match[1]);
  assert.deepEqual(rows, ["job-d", "job-b", "job-a", "job-c"]);
});

test("each job card row has arrows Python enables, and a job off the page or in a compact list has none", () => {
  const markup = panel({ jobs: { "job-a": { periods: [], move: { up: false, down: true } }, "job-b": { periods: [], move: { up: true, down: false } },
    "job-c": { periods: [] } }, offPage: ["job-c"] });
  assert.match(button(markup, "Переместить выше: Alpha Works"), /disabled/u);
  assert.doesNotMatch(button(markup, "Переместить ниже: Alpha Works"), /disabled/u);
  assert.doesNotMatch(button(markup, "Переместить выше: Beta Labs"), /disabled/u);
  assert.match(button(markup, "Переместить ниже: Beta Labs"), /disabled/u);
  assert.ok(!markup.includes("Переместить выше: Gamma Group") && !markup.includes("Переместить ниже: Delta Ltd"));
  // The arrows stand before the remove button of their row.
  assert.ok(markup.indexOf("Переместить ниже: Alpha Works") < markup.indexOf("Удалить: Alpha Works"));
});

test("the arrows and the sort button are disabled while a panel command is pending", () => {
  const markup = panel({ jobs: { "job-a": { periods: [], move: { up: true, down: true } } }, sortJobs: true }, [{ operation: "move_job" }]);
  assert.match(button(markup, "Переместить выше: Alpha Works"), /disabled/u);
  assert.match(button(markup, "Переместить ниже: Alpha Works"), /disabled/u);
  assert.match(markup, /<button[^>]*disabled[^>]*>Расставить по дате<\/button>/u);
});

test("warning lines stand under the row: out of order, and overlaps with two names and «и ещё N»", () => {
  const markup = panel({ jobs: { "job-a": { periods: [], outOfOrder: true, overlaps: ["job-b", "job-c", "job-d"] }, "job-b": { periods: [], overlaps: ["job-a"] } } });
  assert.match(markup, /Стоит не по дате/u);
  assert.ok(markup.includes("Пересекается с «Beta Labs», «Gamma Group» и ещё 1"));
  assert.ok(markup.includes("Пересекается с «Alpha Works»"));
  assert.ok(markup.indexOf('data-fact-id="job-a"') < markup.indexOf("Стоит не по дате"));
  assert.ok(markup.indexOf("Стоит не по дате") < markup.indexOf('data-fact-id="job-b"'));
  assert.equal(overlapLine(["One", "Two"]), "Пересекается с «One», «Two»");
  assert.equal(overlapLine(["One", "Two", "Three", "Four"]), "Пересекается с «One», «Two» и ещё 2");
  assert.ok(!panel({ jobs: { "job-a": { periods: [] } } }).includes("fact-warning"));
});

test("«Расставить по дате» stands beside «+ Место работы» only when a card is out of order", () => {
  const sorted = panel({ addKinds: ["employment"], sortJobs: true });
  assert.ok(sorted.indexOf("+ Место работы") < sorted.indexOf("Расставить по дате"));
  assert.match(sorted, /<div class="fact-add-row">/u);
  assert.ok(!panel({ addKinds: ["employment"] }).includes("Расставить по дате"));
  // Without an add the sort button still has its place.
  assert.ok(panel({ sortJobs: true }).includes("Расставить по дате"));
});

test("the V7 path takes a move with one direction and the sort, and nothing else of them", () => {
  assert.deepEqual(panelCommandsV7({ operation: "move_job", recordId: "job-a", values: { direction: "up" } }, kinds),
    [{ operation: "move_job", recordId: "job-a", values: { direction: "up" } }]);
  assert.deepEqual(panelCommandsV7({ operation: "sort_jobs", recordKind: "employment" }, kinds), [{ operation: "sort_jobs", recordKind: "employment" }]);
  assert.equal(panelCommandsV7({ operation: "move_job", recordId: "job-a", values: { direction: "left" } }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "move_job", recordId: "job-a", values: { direction: "up", extra: "x" } }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "move_job", recordId: "tech", values: { direction: "up" } }, new Map([["tech", "technology"]])), null);
  assert.equal(panelCommandsV7({ operation: "sort_jobs", recordId: "job-a" }, kinds), null);
  assert.equal(panelCommandsV7({ operation: "sort_jobs", recordKind: "technology" }, kinds), null);
});

test("the add form has «по настоящее время», the warning region and an enabled Save", () => {
  const markup = renderToStaticMarkup(createElement(FactDialog, { target: { kind: "employment", record: null }, close: () => {},
    submit: async () => {}, checkDates: async () => [] }));
  assert.match(markup, /<label for="fact-present">по настоящее время<\/label><input id="fact-present"[^>]*type="checkbox"[^>]*name="present"/u);
  assert.match(markup, /class="fact-warnings" role="status"/u);
  assert.doesNotMatch(markup, /<button[^>]*type="submit"[^>]*disabled/u);
  // No browser check refuses a date at Save.
  assert.doesNotMatch(markup, /name="start"[^>]*required|min="0001/u);
  const edit = renderToStaticMarkup(createElement(FactDialog, { target: { kind: "employment", record: jobs[0]! }, close: () => {},
    submit: async () => {}, checkDates: async () => [] }));
  assert.match(edit, /role="status"/u);
  const language = renderToStaticMarkup(createElement(FactDialog, { target: { kind: "language", record: null }, close: () => {},
    submit: async () => {}, checkDates: async () => [] }));
  assert.ok(!language.includes('role="status"') && !language.includes("по настоящее время"));
});

function fakeTimers() {
  const queue: { run: () => void; at: number; id: number }[] = [];
  let now = 0, next = 0;
  return {
    timers: { set: (run: () => void, delay: number) => { const id = ++next; queue.push({ run, at: now + delay, id }); return id; },
      clear: (id: unknown) => { const index = queue.findIndex(item => item.id === id); if (index >= 0) queue.splice(index, 1); } },
    advance(by: number) { now += by; for (const item of queue.filter(value => value.at <= now)) { queue.splice(queue.indexOf(item), 1); item.run(); } },
  };
}
const overlap: DateWarning = { kind: "overlap", recordId: "job-b", period: "05.2022 – 03.2024" };

test("the dialog asks once after the last change, not before the delay and not when no date changed", async () => {
  const clock = fakeTimers(), shown: (readonly DateWarning[])[] = [];
  const check = mock.fn(async (_values: Record<string, string>) => [overlap]);
  const checker = dateChecker({ check, show: value => shown.push(value), timers: clock.timers });
  checker.schedule(() => ({ values: { start: "2021" }, changed: true }));
  clock.advance(dateCheckDelay - 1);
  checker.schedule(() => ({ values: { start: "2022" }, changed: true }));
  clock.advance(dateCheckDelay - 1);
  assert.equal(check.mock.callCount(), 0);
  clock.advance(1);
  assert.equal(check.mock.callCount(), 1);
  assert.deepEqual(check.mock.calls[0]!.arguments[0], { start: "2022" });
  await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(shown.slice(), [[overlap]]);
  checker.schedule(() => ({ values: { start: "" }, changed: false }));
  clock.advance(dateCheckDelay);
  assert.equal(check.mock.callCount(), 1);
  assert.deepEqual(shown.at(-1), []);
});

test("a late answer to older values and a failed check show nothing; a closed dialog takes no answer", async () => {
  const clock = fakeTimers(), shown: (readonly DateWarning[])[] = [];
  const answers: ((value: DateWarning[]) => void)[] = [];
  const checker = dateChecker({ check: () => new Promise<DateWarning[]>(resolve => answers.push(resolve)), show: value => shown.push(value), timers: clock.timers });
  checker.schedule(() => ({ values: { start: "2019" }, changed: true }));
  clock.advance(dateCheckDelay);
  checker.schedule(() => ({ values: { start: "2020" }, changed: true }));
  clock.advance(dateCheckDelay);
  answers[1]!([]);
  answers[0]!([overlap]);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(shown.slice(), [[]]);
  const failing = dateChecker({ check: () => Promise.reject<DateWarning[]>(new Error("offline")), show: value => shown.push(value), timers: clock.timers });
  failing.schedule(() => ({ values: { start: "2020" }, changed: true }));
  clock.advance(dateCheckDelay);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(shown.at(-1), []);
  const closing = dateChecker({ check: () => new Promise<DateWarning[]>(resolve => answers.push(resolve)), show: value => shown.push(value), timers: clock.timers });
  closing.schedule(() => ({ values: { start: "2020" }, changed: true }));
  clock.advance(dateCheckDelay);
  const count = shown.length;
  closing.dispose();
  answers.at(-1)!([overlap]);
  closing.schedule(() => null);
  clock.advance(dateCheckDelay);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(shown.length, count);
});

test("the dialog's lines name the other job and its period, and an end before the start", () => {
  const lines = dateWarningLines([overlap, { kind: "reversed" }, overlap], id => id === "job-b" ? "Beta Labs" : "?", overlapLine);
  assert.deepEqual(lines, ["Пересекается с «Beta Labs» (05.2022 – 03.2024)", "Окончание раньше начала"]);
  assert.deepEqual(parseDateWarnings({ schemaVersion: 1, warnings: [overlap, { kind: "reversed", periodId: "p" }] }), [overlap, { kind: "reversed" }]);
  assert.throws(() => parseDateWarnings({ schemaVersion: 1, warnings: [{ kind: "overlap" }] }));
  assert.throws(() => parseDateWarnings({ schemaVersion: 2, warnings: [] }));
});
