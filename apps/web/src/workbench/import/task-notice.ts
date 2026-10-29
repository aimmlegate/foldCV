import { errorMessage } from "../../errors/messages";
import { importView, stepText, type ImportEntry } from "./progress";

export type TaskNotice = {
  projectId: string; title: string; startedAt: string; stopping: boolean;
  state: "running" | "queued" | "stalled" | "failed" | "done" | "stopped"; text: string;
};

/** Every followed import as one notification in «Импорт»: running and queued ones with Stop, finished ones until closed. */
export function taskNotices(entries: Iterable<ImportEntry>, now: number, titleOf: (projectId: string) => string | undefined = () => undefined): TaskNotice[] {
  return [...entries].map(entry => {
    const view = importView(entry, now);
    const base = { projectId: entry.projectId, title: titleOf(entry.projectId) || entry.title, startedAt: entry.task.startedAt,
      stopping: entry.stopping };
    switch (view.kind) {
      case "running": {
        if (view.phase === "queued") return { ...base, state: "queued", text: "Импорт в очереди" };
        const step = stepText(view.progress);
        return { ...base, state: "running", text: step ? `Идёт импорт · ${step}` : "Идёт импорт" };
      }
      case "stalled": return { ...base, state: "stalled", text: "Импорт не отвечает" };
      case "failed": return { ...base, state: "failed", text: `${view.lost ? "Нет связи с импортом" : "Импорт не удался"}. ${errorMessage(view.code)}` };
      case "cancelled": return { ...base, state: "stopped", text: "Импорт остановлен" };
      case "succeeded": return { ...base, state: "done", text: "Импорт завершён" };
    }
  });
}
