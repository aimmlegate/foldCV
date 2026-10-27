import type { ProjectTask } from "../../projects/api";

export type TaskNotice = { id: string; state: "running" | "done" | "stopped"; text: string; startedAt: string };

/** The import task as one notification: running with Stop, or finished until closed. A failure is already in «Ошибки». */
export function taskNotice(task: ProjectTask | null, closed: string | null): TaskNotice | null {
  if (!task || task.kind !== "import" || task.id === closed) return null;
  const entry = { id: task.id, startedAt: task.startedAt };
  if (task.state === "running") return { ...entry, state: "running", text: "Идёт импорт резюме" };
  if (task.state === "succeeded") return { ...entry, state: "done", text: "Импорт завершён" };
  if (task.state === "cancelled") return { ...entry, state: "stopped", text: "Импорт остановлен" };
  return null;
}
