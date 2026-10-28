export type RewriteStage = "saving" | "queued" | "starting" | "running" | "applying" | "cancelling"
  | "preview" | "saved" | "no_change" | "cancelled" | "failed" | "review";
export type RewriteActivity = { actionId: string; stage: RewriteStage; startedAt: number; finishedAt: number | null; detail: string | null };

export function rewriteCancellable(stage: RewriteStage): boolean {
  return ["saving", "queued", "starting", "running"].includes(stage);
}
export const rewriteLabels: Record<RewriteStage, string> = {
  saving: "Сохраняем правки", queued: "В очереди", starting: "Начинаем",
  running: "Готовим новый текст", applying: "Применяем", cancelling: "Останавливаем",
  saved: "Текст изменён", no_change: "Без изменений", cancelled: "Отменено",
  failed: "Не удалось изменить текст", review: "Проверьте результат",
  preview: "Новый текст готов",
};
