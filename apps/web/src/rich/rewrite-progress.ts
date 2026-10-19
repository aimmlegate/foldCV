import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";
import type { RichSelection } from "../contracts/generated/rich_selection";

export type RewriteStage = "saving" | "queued" | "starting" | "running" | "applying" | "cancelling"
  | "preview" | "saved" | "no_change" | "cancelled" | "failed" | "review";
export type RewriteActivity = { actionId: string; stage: RewriteStage; startedAt: number; finishedAt: number | null; detail: string | null };
export type RewritePreview = { actionId: string; source: string; text: string; instruction: string; selection: RichSelection };

export function rewriteActive(stage: RewriteStage): boolean {
  return ["saving", "queued", "starting", "running", "applying", "cancelling"].includes(stage);
}
export function rewriteCancellable(stage: RewriteStage): boolean {
  return ["saving", "queued", "starting", "running"].includes(stage);
}
export function rewriteStage(job: JobSnapshotV1): RewriteStage {
  if (job.receipt) return "saved";
  if (["needs_review", "save_failed", "outcome_unknown"].includes(job.publication)) return "review";
  if (job.publication === "cancelled" || job.execution === "cancelled") return "cancelled";
  if (job.publication === "discarded") return "cancelled";
  if (job.submission.approvalRequired && job.proposalId && ["ready", "waiting_for_sync"].includes(job.publication)) return "preview";
  if (["ready", "waiting_for_sync", "committing"].includes(job.publication)) return "applying";
  if (["failed", "interrupted"].includes(job.execution)) return "failed";
  if (job.execution === "cancelling") return "cancelling";
  if (job.execution === "queued") return "queued";
  if (job.execution === "starting") return "starting";
  return job.execution === "completed" ? "no_change" : "running";
}
export const rewriteLabels: Record<RewriteStage, string> = {
  saving: "Сохраняем ваши изменения", queued: "Правка в очереди", starting: "Начинаем правку",
  running: "Готовим новый текст", applying: "Применяем и сохраняем правку", cancelling: "Останавливаем запрос",
  saved: "Текст изменён и сохранён", no_change: "Правка завершена без изменений", cancelled: "Правка отменена",
  failed: "Не удалось изменить текст", review: "Результат требует проверки",
  preview: "Новый текст готов к просмотру",
};
