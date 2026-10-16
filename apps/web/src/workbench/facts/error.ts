import { RichApiFailure } from "../../rich/api";

export function factError(error: unknown): string {
  if (error instanceof RichApiFailure) return error.code.startsWith("STALE")
    ? "Данные изменились. Откройте факт заново и повторите правку."
    : "Не удалось обновить факт. Повторите правку.";
  return error instanceof Error && !(error instanceof TypeError) ? error.message : "Не удалось обновить факт. Повторите правку.";
}
