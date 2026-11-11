import assert from "node:assert/strict";
import test from "node:test";
import { importUsage, plural, taskNotices, usageText } from "../src/workbench/import/task-notice";
import type { ImportEntry } from "../src/workbench/import/progress";
import type { ProjectTask } from "../src/projects/api";

const NOW = Date.parse("2026-10-28T00:01:00+00:00");
const task = (projectId: string, state: ProjectTask["state"], detail: ProjectTask["detail"] = {}, error: string | null = null): ProjectTask => ({
  id: `task-${projectId}`, projectId, kind: "import", state, stage: "processing", startedAt: "2026-10-28T00:00:00+00:00", elapsed: 3, detail, error });
const entry = (value: ProjectTask): ImportEntry => ({ projectId: value.projectId, title: `${value.projectId}.pdf`, task: value, polledAt: NOW,
  failure: null, stopping: false, retrying: false });
const progress = (phase: string, done: number, total: number, stalled = false) => ({ progress: { phase, done, total, current: [], events: [],
  lastEventAt: null, lastModelAt: null, quietSeconds: 1, quietLimitSeconds: 245, stalled } });

test("every followed import is its own notice, named by its resume and state", () => {
  const notices = taskNotices([entry(task("a", "running", progress("processing", 2, 9))), entry(task("b", "running", progress("queued", 0, 0))),
    entry(task("c", "running", progress("processing", 1, 9, true))), entry(task("d", "failed", {}, "IMPORT_EFFORT_UNSUPPORTED")),
    entry(task("e", "cancelled")), entry(task("f", "succeeded"))], NOW, id => id === "a" ? "Резюме A" : undefined);
  assert.deepEqual(notices.map(notice => [notice.projectId, notice.title, notice.state]), [["a", "Резюме A", "running"], ["b", "b.pdf", "queued"],
    ["c", "c.pdf", "stalled"], ["d", "d.pdf", "failed"], ["e", "e.pdf", "stopped"], ["f", "f.pdf", "done"]]);
  assert.equal(notices[0]?.text, "Идёт импорт · Шаг 3 из 9");
  assert.match(notices[3]?.text ?? "", /^Импорт не удался\. Выбранный уровень рассуждений недоступен/);
});

const spent = (calls: number, inputTokens: number, cachedInputTokens: number, outputTokens: number) =>
  ({ usage: { calls, inputTokens, cachedInputTokens, outputTokens } });

test("a finished import's line names its calls and tokens: whole thousands, the cached part only when read (T9)", () => {
  assert.equal(usageText({ calls: 34, inputTokens: 615_234, cachedInputTokens: 33_456, outputTokens: 30_900 }),
    "34 вызова · 615 тыс. токенов на входе (из кэша 33 тыс.) · 31 тыс. на выходе");
  assert.equal(usageText({ calls: 1, inputTokens: 999, cachedInputTokens: 0, outputTokens: 1_499 }),
    "1 вызов · 999 токенов на входе · 1 тыс. на выходе");
  assert.equal(usageText({ calls: 2, inputTokens: 1_500, cachedInputTokens: 512, outputTokens: 0 }),
    "2 вызова · 2 тыс. токенов на входе (из кэша 512) · 0 на выходе");
  assert.equal(usageText({ calls: 21, inputTokens: 1, cachedInputTokens: 0, outputTokens: 22 }), "21 вызов · 1 токен на входе · 22 на выходе");
  assert.equal(usageText({ calls: 5, inputTokens: 23, cachedInputTokens: 0, outputTokens: 5 }), "5 вызовов · 23 токена на входе · 5 на выходе");
  assert.equal(usageText({ calls: 26, inputTokens: 1_273_205, cachedInputTokens: 0, outputTokens: 999_500 }),
    "26 вызовов · 1273 тыс. токенов на входе · 1000 тыс. на выходе");
});

test("the count takes its Russian form: 1 вызов, 2–4 вызова, 5–20 вызовов, 21 вызов", () => {
  const forms: [number, string][] = [[1, "вызов"], [2, "вызова"], [4, "вызова"], [5, "вызовов"], [11, "вызовов"], [12, "вызовов"],
    [14, "вызовов"], [20, "вызовов"], [21, "вызов"], [22, "вызова"], [25, "вызовов"], [101, "вызов"], [111, "вызовов"], [112, "вызовов"],
    [122, "вызова"]];
  for (const [count, word] of forms) assert.equal(plural(count, "вызов", "вызова", "вызовов"), word, String(count));
});

test("a failed or stopped import that made calls shows its line after the message; one without calls shows none", () => {
  const notices = taskNotices([entry(task("a", "succeeded", spent(34, 615_234, 33_456, 30_900))),
    entry(task("b", "failed", spent(3, 40_000, 0, 2_000), "QUOTA_EXHAUSTED")), entry(task("c", "cancelled", spent(1, 900, 0, 50))),
    entry(task("d", "succeeded")), entry(task("e", "running", { ...progress("processing", 2, 9), ...spent(2, 10, 0, 1) }))], NOW);
  assert.deepEqual(notices.map(notice => notice.usage), ["34 вызова · 615 тыс. токенов на входе (из кэша 33 тыс.) · 31 тыс. на выходе",
    "3 вызова · 40 тыс. токенов на входе · 2 тыс. на выходе", "1 вызов · 900 токенов на входе · 50 на выходе", "", ""]);
  assert.equal(notices[0]?.text, "Импорт завершён");
  assert.match(notices[1]?.text ?? "", /^Импорт не удался\. /u);
  assert.equal(notices[2]?.text, "Импорт остановлен");
});

test("usage the service did not send whole is not shown", () => {
  for (const detail of [{ usage: null }, { usage: { ...spent(0, 0, 0, 0).usage } }, { usage: { ...spent(2, 10, 0, 1).usage, inputTokens: -1 } },
    { usage: { ...spent(2, 10, 0, 1).usage, calls: "2" } }, { usage: { calls: 2, inputTokens: 10, outputTokens: 1 } }, { usage: { ...spent(2.5, 10, 0, 1).usage } }])
    assert.equal(importUsage(detail), null, JSON.stringify(detail));
  assert.deepEqual(importUsage(spent(2, 10, 0, 1)), { calls: 2, inputTokens: 10, cachedInputTokens: 0, outputTokens: 1 });
});
