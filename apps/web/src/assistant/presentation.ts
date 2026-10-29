import { errorMessage } from "../errors/messages";
import type { AssistantView } from "./controller";

export function errorText(code: string | null): string {
  return code ? errorMessage(code, "Помощник не закончил работу. Готовое осталось в диалоге.") : "";
}
export function runText(view: AssistantView): string {
  if (view.submitting) return "Отправляем…";
  if (view.pendingSend) return "Нет ответа на отправку. Отправьте ещё раз или остановите.";
  const labels = { queued: "В очереди", running: "Работает",
    cancelling: "Останавливаем…", cancelled: "Остановлено", interrupted: "Прервано", failed: "Не удалось", completed: "Завершено" };
  return view.run ? labels[view.run.state] : "";
}
export function canSend(view: AssistantView, applying = false): boolean {
  return !view.submitting && !view.loading && !applying && (!view.run || ["completed", "failed", "cancelled", "interrupted"].includes(view.run.state))
    && (view.pendingSend || view.capabilities?.ready === true) && !!view.draft.trim() && [...view.draft].length <= 8000;
}
export function submitKey(key: string, shift: boolean, composing: boolean, nativeComposing: boolean, keyCode: number): boolean {
  return key === "Enter" && !shift && !composing && !nativeComposing && keyCode !== 229;
}
export function sourceUrl(value: string): string | null {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}
export type DrawerSize = { collapsed: boolean; height: number };
export function drawerSize(value: unknown): DrawerSize {
  if (typeof value !== "object" || value === null) return { collapsed: true, height: 320 };
  return { collapsed: "collapsed" in value && typeof value.collapsed === "boolean" ? value.collapsed : true,
    height: "height" in value && typeof value.height === "number" && Number.isFinite(value.height) ? Math.max(200, Math.min(520, value.height)) : 320 };
}
