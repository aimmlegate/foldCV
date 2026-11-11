import { errorMessage } from "../../errors/messages";
import { importView, stepText, type ImportEntry } from "./progress";

export type TaskNotice = {
  projectId: string; title: string; startedAt: string; stopping: boolean;
  state: "running" | "queued" | "stalled" | "failed" | "done" | "stopped"; text: string;
  /** What a finished import's calls spent, or "" when it made none. */
  usage: string;
};

/** `detail.usage` of a finished import (T9): its calls and tokens, summed over its record's attempts. */
export type ImportUsage = { calls: number; inputTokens: number; cachedInputTokens: number; outputTokens: number };

export function importUsage(detail: Record<string, unknown>): ImportUsage | null {
  const value = detail["usage"];
  if (typeof value !== "object" || value === null) return null;
  const count = (key: string): number | null => {
    const item: unknown = Reflect.get(value, key);
    return typeof item === "number" && Number.isSafeInteger(item) && item >= 0 ? item : null;
  };
  const calls = count("calls"), inputTokens = count("inputTokens"), cachedInputTokens = count("cachedInputTokens"),
    outputTokens = count("outputTokens");
  if (!calls || inputTokens === null || cachedInputTokens === null || outputTokens === null) return null;
  return { calls, inputTokens, cachedInputTokens, outputTokens };
}

/** The Russian form for a count: 1 вызов, 2–4 вызова, 5–20 вызовов, 21 вызов. */
export function plural(count: number, one: string, few: string, many: string): string {
  const tens = count % 100, units = count % 10;
  if (tens >= 11 && tens <= 14) return many;
  return units === 1 ? one : units >= 2 && units <= 4 ? few : many;
}

/** Whole thousands from a thousand up; a smaller count as it is. */
function tokens(count: number): string {
  return count < 1000 ? String(count) : `${String(Math.round(count / 1000))} тыс.`;
}

/** «34 вызова · 615 тыс. токенов на входе (из кэша 33 тыс.) · 31 тыс. на выходе»; no «из кэша» when nothing was read. */
export function usageText(usage: ImportUsage): string {
  const word = usage.inputTokens < 1000 ? plural(usage.inputTokens, "токен", "токена", "токенов") : "токенов";
  const cached = usage.cachedInputTokens > 0 ? ` (из кэша ${tokens(usage.cachedInputTokens)})` : "";
  return `${String(usage.calls)} ${plural(usage.calls, "вызов", "вызова", "вызовов")} · ${tokens(usage.inputTokens)} ${word} на входе${cached}`
    + ` · ${tokens(usage.outputTokens)} на выходе`;
}

/** Every followed import as one notification in «Импорт»: running and queued ones with Stop, finished ones until closed. */
export function taskNotices(entries: Iterable<ImportEntry>, now: number, titleOf: (projectId: string) => string | undefined = () => undefined): TaskNotice[] {
  return [...entries].map(entry => {
    const view = importView(entry, now);
    const base = { projectId: entry.projectId, title: titleOf(entry.projectId) || entry.title, startedAt: entry.task.startedAt,
      stopping: entry.stopping, usage: "" };
    // A failed or stopped import that made calls spent them too; only a finished task carries the numbers.
    const spent = importUsage(entry.task.detail);
    const usage = spent ? usageText(spent) : "";
    switch (view.kind) {
      case "running": {
        if (view.phase === "queued") return { ...base, state: "queued", text: "Импорт в очереди" };
        const step = stepText(view.progress);
        return { ...base, state: "running", text: step ? `Идёт импорт · ${step}` : "Идёт импорт" };
      }
      case "stalled": return { ...base, state: "stalled", text: "Импорт не отвечает" };
      case "failed": return { ...base, state: "failed", text: `${view.lost ? "Нет связи с импортом" : "Импорт не удался"}. ${errorMessage(view.code)}`, usage };
      case "cancelled": return { ...base, state: "stopped", text: "Импорт остановлен", usage };
      case "succeeded": return { ...base, state: "done", text: "Импорт завершён", usage };
    }
  });
}
