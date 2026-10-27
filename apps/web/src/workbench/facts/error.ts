import { errorMessage } from "../../errors/messages";
import { ProjectApiFailure } from "../../rich/v7-connection";

export function factError(error: unknown): string {
  if (error instanceof ProjectApiFailure) return error.code.startsWith("STALE")
    ? "Данные изменились. Откройте факт заново и повторите правку."
    : errorMessage(error, "Не удалось обновить факт. Повторите правку.");
  return errorMessage(error, "Не удалось обновить факт. Повторите правку.");
}
