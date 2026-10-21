import { errorMessage } from "../errors/messages";
import type { JobSummaryV1 } from "../contracts/generated/background_summary_v1";
import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";

export function jobKey(job: Pick<JobSummaryV1, "projectId" | "lineage" | "jobId">): string {
  return JSON.stringify([job.projectId, job.lineage, job.jobId]);
}
export function summary(job: JobSnapshotV1, title: string): JobSummaryV1 {
  return { schemaVersion: 1, projectId: job.submission.identity.projectId, lineage: job.submission.identity.lineage,
    jobId: job.id, projectTitle: title, kind: job.submission.kind, stage: job.attempts.at(-1)?.stage ?? null,
    execution: job.execution, publication: job.publication, executionGeneration: job.executionGeneration,
    eventCursor: job.eventCursor, allowEdits: job.submission.allowEdits, saved: job.receipt !== null,
    error: job.error, publicationError: job.publicationError ?? null, updatedAt: job.updatedAt,
    ...(job.submission.approvalRequired ? { approvalRequired: true } : {}) };
}
export function active(job: JobSummaryV1): boolean {
  if (job.approvalRequired && job.execution === "completed" && ["ready", "waiting_for_sync"].includes(job.publication)) return false;
  return !["completed", "failed", "cancelled", "interrupted"].includes(job.execution)
    || ["ready", "waiting_for_sync", "committing", "outcome_unknown"].includes(job.publication);
}
export function attention(job: JobSummaryV1): boolean {
  return ["needs_review", "save_failed", "outcome_unknown"].includes(job.publication)
    || ["failed", "interrupted"].includes(job.execution);
}
export function operationLabel(job: JobSummaryV1): string {
  if (job.kind === "agent") return job.allowEdits ? "Помощник" : "Проверка резюме";
  if (job.kind === "rewrite") return "Правка фрагмента";
  if (job.kind === "reconciliation") return "Связанные изменения";
  return job.stage === "extraction" ? "Извлекаем факты" : "Обработка исходника";
}
export function statusLabel(job: JobSummaryV1): string {
  if (job.saved) return job.execution === "cancelled" || job.execution === "cancelling" ? "Сохранено · выполнение остановлено"
    : job.execution === "failed" || job.execution === "interrupted" ? "Сохранено · выполнение не завершилось"
    : active(job) ? "Сохранено · задача ещё работает" : "Сохранено";
  if (job.publication === "needs_review") return "Нужна проверка результата";
  if (job.publication === "outcome_unknown") return "Сохранение пока не подтверждено";
  if (job.publication === "save_failed") return "Не удалось сохранить результат";
  if (job.execution === "failed") return "Не удалось завершить";
  if (job.execution === "interrupted") return "Выполнение прервано";
  if (job.approvalRequired && ["ready", "waiting_for_sync"].includes(job.publication)) return "Ожидает применения";
  if (job.publication === "waiting_for_sync" || job.publication === "ready") return "Ожидает синхронизации";
  if (job.publication === "committing") return "Сохраняется";
  if (job.publication === "discarded") return "Результат отброшен";
  if (job.execution === "cancelled" || job.publication === "cancelled") return "Отменено";
  if (job.execution === "cancelling") return "Останавливается";
  if (job.execution === "queued") return "В очереди";
  if (job.execution === "starting") return "Подготавливаем модель";
  if (job.execution === "completed") return job.allowEdits ? "Завершено без изменений" : "Проверка завершена";
  return job.stage === "extraction" ? "Извлекаем факты" : job.stage === "rewrite" ? "Переписываем фрагмент"
    : job.stage === "assessment" ? "Читаем исходник" : job.stage === "reconciliation" ? "Проверяем связанные изменения" : "Модель выполняет задачу";
}
export function projectActivity(jobs: readonly JobSummaryV1[]): ReadonlyMap<string, string> {
  const groups = new Map<string, { active: number; attention: number }>();
  for (const job of jobs) {
    const value = groups.get(job.projectId) ?? { active: 0, attention: 0 };
    if (active(job)) value.active++;
    if (attention(job)) value.attention++;
    groups.set(job.projectId, value);
  }
  return new Map([...groups].filter(([, value]) => value.active || value.attention)
    .map(([id, value]) => [id, value.attention ? `Требуют проверки: ${String(value.attention)}` : `В фоне: ${String(value.active)}`]));
}
export function failureLabel(code: string | null | undefined): string | null {
  if (!code || ["CANCELLED", "PROJECT_DELETED"].includes(code)) return null;
  return errorMessage(code);
}
