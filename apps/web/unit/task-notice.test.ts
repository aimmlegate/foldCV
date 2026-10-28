import assert from "node:assert/strict";
import test from "node:test";
import { taskNotices } from "../src/workbench/import/task-notice";
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
