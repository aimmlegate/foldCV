import assert from "node:assert/strict";
import test from "node:test";
import { taskNotice } from "../src/workbench/import/task-notice";
import type { ProjectTask } from "../src/projects/api";

const task = (state: ProjectTask["state"], kind: ProjectTask["kind"] = "import"): ProjectTask => ({ id: "task-1", projectId: "project-1",
  kind, state, stage: "processing", startedAt: "2026-10-28T00:00:00+00:00", elapsed: 3, detail: {}, error: null });

test("an import task is one notification until it is closed; a failure stays in «Ошибки» only", () => {
  assert.deepEqual(taskNotice(task("running"), null), { id: "task-1", startedAt: "2026-10-28T00:00:00+00:00", state: "running",
    text: "Идёт импорт резюме" });
  assert.equal(taskNotice(task("succeeded"), null)?.text, "Импорт завершён");
  assert.equal(taskNotice(task("cancelled"), null)?.text, "Импорт остановлен");
  assert.equal(taskNotice(task("succeeded"), "task-1"), null);
  assert.equal(taskNotice(task("failed"), null), null);
  assert.equal(taskNotice(task("running", "export"), null), null);
  assert.equal(taskNotice(null, null), null);
});

test("an import queued behind other model work says that it waits", () => {
  assert.equal(taskNotice({ ...task("running"), stage: "waiting" }, null)?.text, "Импорт ждёт очереди");
});
