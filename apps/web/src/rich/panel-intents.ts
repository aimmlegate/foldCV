import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { PanelCommand } from "./synchronization";

export const technologyName = (value: string): string => value.trim().replace(/\s+/gu, " ");
export const technologyKey = (value: string): string => technologyName(value).toLocaleLowerCase();

export function currentPanelIntent(command: PanelCommand, facts: WorkingFacts): PanelCommand | null {
  const records = facts.records;
  if ((command.operation === "add" || command.operation === "clear_technologies") && command.jobId != null &&
      !records.some(record => record.kind === "employment" && record.id === command.jobId)) throw new Error("Работа уже удалена. Откройте факты заново.");
  if (command.operation === "add" && command.recordKind === "technology") {
    const display = technologyName(command.values?.["display"] ?? "");
    if (!display || display.length > 80) throw new Error("Введите название технологии до 80 символов.");
    if (records.some(record => record.kind === "technology" && record.jobId === (command.jobId ?? null) &&
        technologyKey(record.display.rawText) === technologyKey(display))) return null;
    return { ...command, values: { display } };
  }
  if (command.operation === "clear_technologies") return records.some(record => record.kind === "technology" &&
    record.jobId === (command.jobId ?? null)) ? command : null;
  if (command.operation === "add") {
    if (command.recordKind === "candidate" && records.some(record => record.kind === "candidate")) throw new Error("Кандидат уже добавлен.");
    return command;
  }
  const record = records.find(record => record.id === command.recordId);
  if (!record) {
    if (command.operation === "remove") return null;
    throw new Error("Факт уже удалён. Откройте его заново.");
  }
  if ((command.operation === "add_period" || command.operation === "remove_period") && record.kind !== "employment")
    throw new Error("Работа уже удалена.");
  if (command.operation === "remove_period" && record.kind === "employment" && !record.periods.some(period => period.id === command.periodId))
    throw new Error("Период уже удалён.");
  return command;
}
