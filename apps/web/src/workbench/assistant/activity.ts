import type { AssistantView } from "../../assistant/controller";
import { activityText } from "./status";

const tools: Record<string, [string, string]> = {
  web_search: ["Ищет информацию в интернете", "Поиск в интернете"], get_resume_context: ["Читает резюме", "Чтение резюме"],
  find_resume_content: ["Ищет нужный фрагмент", "Поиск в резюме"], get_working_facts: ["Читает факты", "Чтение фактов"],
  get_original_source: ["Читает исходник", "Чтение исходника"], get_conversation_context: ["Читает диалог", "Чтение диалога"],
  check_resume: ["Проверяет резюме", "Проверка резюме"], read_public_page: ["Читает страницу", "Чтение страницы"],
  publish_findings: ["Сохраняет замечания", "Сохранение замечаний"], prepare_edit_batch: ["Готовит правки", "Подготовка правок"],
  apply_edit_batch: ["Сохраняет изменения", "Сохранение изменений"],
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
    } else if (event.type === "edit.offered" || event.type === "edit.result") {
      entries.set(event.payload.batchId, { id: event.payload.batchId, label: event.payload.disposition === "saved" ? "Изменения сохранены" : "Проверка и сохранение правок",
        text: "", timestamp: event.timestamp, state: event.payload.disposition === "saved" ? "success" : event.payload.error ? "error" : "working" });
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
