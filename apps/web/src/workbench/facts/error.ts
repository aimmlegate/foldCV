import { errorMessage } from "../../errors/messages";
import { ProjectApiFailure } from "../../rich/v7-connection";

export function factError(error: unknown): string {
  if (error instanceof ProjectApiFailure) return error.code.startsWith("STALE")
    ? "Факт изменился. Откройте его заново и повторите правку."
    : errorMessage(error, "Не удалось сохранить факт. Повторите правку.");
  return errorMessage(error, "Не удалось сохранить факт. Повторите правку.");
}
