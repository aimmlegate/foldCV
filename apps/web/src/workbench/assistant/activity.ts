import type { AssistantView } from "../../assistant/controller";
import { activityText } from "./status";

const tools: Record<string, [string, string]> = {
  web_search: ["Ищет в интернете", "Поиск в интернете"], read_resume: ["Читает резюме", "Чтение резюме"],
  find_text: ["Ищет в резюме", "Поиск в резюме"], read_facts: ["Читает факты", "Чтение фактов"],
  read_original: ["Читает исходник", "Чтение исходника"], read_skill: ["Читает инструкцию", "Чтение инструкции"],
  check_resume: ["Проверяет резюме", "Проверка резюме"], read_public_page: ["Читает страницу", "Чтение страницы"],
  export_document: ["Готовит файл", "Подготовка файла"], publish_findings: ["Сохраняет замечания", "Сохранение замечаний"],
  propose_changes: ["Готовит правки", "Подготовка правок"],
};
export type ActivityItem = { id: string; label: string; text: string; timestamp: string; state: "working" | "success" | "error" | "summary" };

/** Activity titles are one line of plain text. The model sometimes wraps that line in markdown. */
export function plainActivity(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/\*\*|__/g, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ *\n */g, "\n")
    .trim();
}

export function activityItems(view: Pick<AssistantView, "activity" | "run">): ActivityItem[] {
  const entries = new Map<string, ActivityItem>();
  for (const event of view.activity) {
    if (event.runId !== view.run?.id) continue;
    if (event.type === "activity.updated") {
      entries.set(event.payload.itemId, { id: event.payload.itemId, label: "Кратко от модели", text: plainActivity(event.payload.text),
        timestamp: event.timestamp, state: "summary" });
    } else if (event.type === "tool.started" || event.type === "tool.completed" || event.type === "tool.failed") {
      entries.set(event.payload.callId, { id: event.payload.callId, label: tools[event.payload.name]?.[1] ?? "Работа с резюме", text: "",
        timestamp: event.timestamp, state: event.type === "tool.started" ? "working" : event.type === "tool.completed" ? "success" : "error" });
    } else if (event.type === "proposal.ready") {
      entries.set(event.payload.id, { id: event.payload.id, label: "Правки готовы", text: "", timestamp: event.timestamp, state: "success" });
    }
  }
  return [...entries.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).slice(-12);
}

export function currentActivity(view: AssistantView, active: boolean): string {
  if (view.loading) return view.loading;
  if (view.submitting || view.pendingSend || view.run?.state !== "running" || !active) return activityText(view, active);
  const pending = activityItems(view).filter(item => item.state === "working").at(-1);
  if (pending) {
    const event = view.activity.find(event => event.type === "tool.started" && event.payload.callId === pending.id);
    return event?.type === "tool.started" ? tools[event.payload.name]?.[0] ?? "Работает с резюме" : pending.label;
  }
  if (view.partial) return "Пишет ответ";
  return "Модель готовит ответ";
}
