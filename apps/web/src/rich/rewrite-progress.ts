export type RewriteStage = "saving" | "queued" | "starting" | "running" | "applying" | "cancelling"
  | "preview" | "saved" | "no_change" | "cancelled" | "failed" | "review";
export type RewriteActivity = { actionId: string; stage: RewriteStage; startedAt: number; finishedAt: number | null; detail: string | null };

export function rewriteCancellable(stage: RewriteStage): boolean {
  return ["saving", "queued", "starting", "running"].includes(stage);
}
export const rewriteLabels: Record<RewriteStage, string> = {
  saving: "Сохраняем ваши изменения", queued: "Правка в очереди", starting: "Начинаем правку",
  running: "Готовим новый текст", applying: "Применяем и сохраняем правку", cancelling: "Останавливаем запрос",
  saved: "Текст изменён и сохранён", no_change: "Правка завершена без изменений", cancelled: "Правка отменена",
  failed: "Не удалось изменить текст", review: "Результат требует проверки",
  preview: "Новый текст готов к просмотру",
};
