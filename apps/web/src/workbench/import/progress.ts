import type { TemplateProjectResponseV1 } from "../../contracts/generated/template_project_response_v1";
import type { ImportPhase, ImportProgress, ProjectTask } from "../../projects/api";

/** One followed import: the last task status the service sent and how the client follows it. */
export type ImportEntry = {
  projectId: string; title: string; task: ProjectTask;
  /** Client time of the last successful status read. */
  polledAt: number;
  /** A code when the client could not follow the task (no reply, a failed resume or retry). */
  failure: string | null;
  stopping: boolean; retrying: boolean;
};

export type ImportView =
  | { kind: "running"; phase: ImportPhase; progress: ImportProgress | null; quietSeconds: number }
  | { kind: "stalled"; code: string; quietSeconds: number }
  | { kind: "failed"; code: string; lost?: boolean }
  | { kind: "cancelled" }
  | { kind: "succeeded" };

/** Without a progress block (before the first status read) the service gave no bound yet. */
const DEFAULT_QUIET_SECONDS = 120;

export function importProgress(task: ProjectTask): ImportProgress | null {
  const value = task.detail["progress"];
  return typeof value === "object" && value !== null ? value as ImportProgress : null;
}

export function operationOf(task: ProjectTask): string | null {
  const value = task.detail["operationId"];
  return typeof value === "string" && value ? value : null;
}

/** The import screen's state. A running import is stalled when the service says so from its timestamps, or when the
 * service itself has not answered for longer than that bound. */
export function importView(entry: ImportEntry, now: number): ImportView {
  const { task } = entry;
  if (task.state === "succeeded") return { kind: "succeeded" };
  if (task.state === "cancelled") return { kind: "cancelled" };
  if (task.state === "failed") return { kind: "failed", code: task.error ?? "PROCESS_FAILED" };
  // The client lost the task (no replies, a failed resume); the service may still be running it.
  if (entry.failure) return { kind: "failed", code: entry.failure, lost: true };
  const progress = importProgress(task);
  const unanswered = Math.max(0, now - entry.polledAt) / 1000;
  const quietSeconds = (progress?.quietSeconds ?? 0) + unanswered;
  if (progress?.stalled || unanswered > (progress?.quietLimitSeconds ?? DEFAULT_QUIET_SECONDS))
    return { kind: "stalled", code: "IMPORT_STALLED", quietSeconds };
  const phase: ImportPhase = progress?.phase ?? (task.stage === "queued" ? "queued" : task.stage === "publication" ? "publication"
    : task.stage === "processing" ? "processing" : "starting");
  return { kind: "running", phase, progress, quietSeconds };
}

/** «Шаг 3 из 9», or nothing before the steps are known. */
export function stepText(progress: ImportProgress | null): string {
  if (!progress || progress.total <= 0) return "";
  if (progress.done >= progress.total) return `Все шаги готовы: ${progress.total}`;
  return `Шаг ${progress.done + 1} из ${progress.total}`;
}

export function currentText(progress: ImportProgress | null): string {
  return progress?.current.length ? progress.current.map(title => `«${title}»`).join(", ") : "";
}

const words: Record<ImportPhase, readonly string[]> = {
  starting: ["Готовимся…", "Читаем исходник…", "Раскладываем страницы…"],
  queued: ["Держим место…", "Скоро начнём…", "Очередь движется…"],
  processing: ["Размышляем…", "Сверяем факты…", "Читаем строки резюме…", "Выписываем детали…", "Проверяем даты…",
    "Раскладываем по разделам…", "Уточняем формулировки…"],
  publication: ["Собираем документ…", "Расставляем блоки…", "Применяем оформление…"],
};

/** A rotating word beside the real step, like a coding harness: it changes every four seconds of the run. */
export function rotatingWord(phase: ImportPhase, elapsedSeconds: number): string {
  const list = words[phase];
  return list[Math.floor(Math.max(0, elapsedSeconds) / 4) % list.length] ?? "";
}

export function agoText(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  if (value < 5) return "только что";
  if (value < 60) return `${value} с назад`;
  return `${Math.floor(value / 60)} мин ${value % 60} с назад`;
}

/** Seconds since the last model call or reply, anchored on the service's last reply. */
export function modelQuietSeconds(entry: ImportEntry, now: number): number | null {
  const progress = importProgress(entry.task);
  const at = Date.parse(progress?.lastModelAt ?? "");
  const last = Date.parse(progress?.lastEventAt ?? "");
  if (!progress || !Number.isFinite(at)) return null;
  // The service's own quiet seconds measure from lastEventAt; the model's last event is that far or further back.
  const behind = Number.isFinite(last) ? Math.max(0, (last - at) / 1000) : 0;
  return progress.quietSeconds + behind + Math.max(0, now - entry.polledAt) / 1000;
}

/** Page count and the first lines of the pre-draft's selected source, shown until the first facts are saved. */
export function sourceSummary(response: TemplateProjectResponseV1 | null): { name: string; pages: number; excerpt: string } {
  const pre = response?.workspace.preDraft;
  const source = pre?.sources.find(item => item.id === pre.selectedSourceId) ?? pre?.sources[0];
  const units = source?.units ?? [];
  return { name: source?.originalName ?? "", pages: new Set(units.filter(unit => unit.location.kind === "page").map(unit => unit.location.index)).size,
    excerpt: units.filter(unit => unit.text.trim()).slice(0, 3).map(unit => unit.text.trim()).join("\n").slice(0, 360) };
}
