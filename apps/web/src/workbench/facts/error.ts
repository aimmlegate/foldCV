import { errorMessage } from "../../errors/messages";
import { RichApiFailure } from "../../rich/api";

export function factError(error: unknown): string {
  if (error instanceof RichApiFailure) return error.code.startsWith("STALE")
    ? "Данные изменились. Откройте факт заново и повторите правку."
    : errorMessage(error, "Не удалось обновить факт. Повторите правку.");
  return errorMessage(error, "Не удалось обновить факт. Повторите правку.");
}
