import assert from "node:assert/strict";
import test from "node:test";
import { importView, modelQuietSeconds, rotatingWord, stepText, type ImportEntry } from "../src/workbench/import/progress";
import type { ImportProgress, ProjectTask } from "../src/projects/api";

const POLLED = Date.parse("2026-10-28T10:00:00+00:00");
function entry(progress: Partial<ImportProgress> | null, state: ProjectTask["state"] = "running", failure: string | null = null): ImportEntry {
  const detail = progress ? { progress: { phase: "processing", done: 0, total: 3, current: [], events: [], lastEventAt: null, lastModelAt: null,
    quietSeconds: 0, quietLimitSeconds: 245, stalled: false, ...progress } } : {};
  return { projectId: "p", title: "cv.pdf", polledAt: POLLED, failure, stopping: false, retrying: false,
    task: { id: "t", projectId: "p", kind: "import", state, stage: "processing", startedAt: "2026-10-28T09:59:00+00:00", elapsed: 60, detail, error: null } };
}

test("the service's stall flag ends the spinner; a service that stops answering does too", () => {
  assert.equal(importView(entry({ quietSeconds: 30 }), POLLED + 1000).kind, "running");
  assert.deepEqual(importView(entry({ quietSeconds: 246, stalled: true }), POLLED), { kind: "stalled", code: "IMPORT_STALLED", quietSeconds: 246 });
  // No reply to polls for longer than the client's two minutes: the client stops waiting with the same error. The
  // service's own bound is the import limit (D114), so it does not apply to unanswered polls.
  assert.equal(importView(entry({ quietSeconds: 10, quietLimitSeconds: 3665 }), POLLED + 119_000).kind, "running");
  const silent = importView(entry({ quietSeconds: 10, quietLimitSeconds: 3665 }), POLLED + 121_000);
  assert.equal(silent.kind, "stalled");
  assert.equal(silent.kind === "stalled" && silent.quietSeconds, 131);
  // Before the first progress block the bound is two minutes.
  assert.equal(importView(entry(null), POLLED + 121_000).kind, "stalled");
});

test("terminal states and client failures win over the running view", () => {
  assert.deepEqual(importView(entry({ stalled: true }, "failed"), POLLED), { kind: "failed", code: "PROCESS_FAILED" });
  assert.deepEqual(importView(entry({}, "running", "REQUEST_FAILED"), POLLED), { kind: "failed", code: "REQUEST_FAILED", lost: true });
  assert.equal(importView(entry({}, "cancelled"), POLLED).kind, "cancelled");
  assert.equal(importView(entry({}, "succeeded"), POLLED).kind, "succeeded");
  const queued = importView(entry({ phase: "queued" }), POLLED);
  assert.equal(queued.kind === "running" && queued.phase, "queued");
});

test("the step line counts the current step and stays empty before the steps are known", () => {
  const progress = (done: number, total: number) => ({ phase: "processing", done, total, current: [], events: [], lastEventAt: null,
    lastModelAt: null, quietSeconds: 0, quietLimitSeconds: 245, stalled: false }) satisfies ImportProgress;
  assert.equal(stepText(null), "");
  assert.equal(stepText(progress(0, 0)), "");
  assert.equal(stepText(progress(0, 9)), "Шаг 1 из 9");
  assert.equal(stepText(progress(8, 9)), "Шаг 9 из 9");
  assert.equal(stepText(progress(9, 9)), "Все шаги готовы: 9");
});

test("rotating words change every four seconds and never stand in for the step", () => {
  assert.equal(rotatingWord("processing", 0), "Размышляем…");
  assert.equal(rotatingWord("processing", 3.9), "Размышляем…");
  assert.equal(rotatingWord("processing", 4), "Сверяем факты…");
  assert.notEqual(rotatingWord("queued", 0), rotatingWord("processing", 0));
  assert.equal(rotatingWord("publication", 8 * 3), rotatingWord("publication", 0));
});

test("the last model activity is measured from the service's last reply", () => {
  const value = entry({ lastEventAt: "2026-10-28T09:59:50+00:00", lastModelAt: "2026-10-28T09:59:40+00:00", quietSeconds: 10 });
  assert.equal(modelQuietSeconds(value, POLLED + 5000), 25);
  assert.equal(modelQuietSeconds(entry({ lastModelAt: null }), POLLED), null);
});
