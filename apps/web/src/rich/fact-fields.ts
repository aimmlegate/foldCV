import type { WorkingFacts } from "../contracts/generated/working_facts";

export type RecordValue = WorkingFacts["records"][number];
export type Kind = "candidate" | "employment" | "technology" | "education" | "language";
type Field = { key: string; label: string; text: string; checked?: boolean };
export const labels = { candidate: "Кандидат", employment: "Опыт", technology: "Технологии", education: "Образование", language: "Языки" };
export const names: Record<Kind, readonly (readonly [string, string])[]> = {
  candidate: [["name", "Имя"], ["title", "Должность"], ["location", "Город"]],
  employment: [["employer", "Компания"], ["role", "Роль"]], technology: [["display", "Технология"]],
  education: [["institution", "Учебное заведение"], ["qualification", "Квалификация"], ["specialty", "Специальность"], ["completion", "Дата окончания"]],
  language: [["language", "Язык"], ["level", "Уровень"]],
};
export function fields(record: RecordValue): Field[] {
  if (!(record.kind in names)) return [];
  const values = Object.entries(record);
  const result = names[record.kind as Kind].map(([key, label]) => {
    const value: unknown = values.find(([name]) => name === key)?.[1];
    return { key, label, text: typeof value === "object" && value !== null && "rawText" in value && typeof value.rawText === "string" ? value.rawText : "" };
  });
  if (record.kind === "employment") record.periods.forEach((period, index) => {
    result.push({ key: `period:${period.id}:start`, label: `Начало ${index + 1}`, text: period.start.rawText },
      { key: `period:${period.id}:end`, label: `Окончание ${index + 1}`, text: period.end.rawText });
  });
  return [...result, ...(record.kind === "employment" ? record.periods.map((period, index) => ({ key: `period:${period.id}:present`,
    label: `Работаю сейчас ${index + 1}`, text: period.present.rawText, checked: period.present.value === true })) : [])];
}
export function title(record: RecordValue): string {
  if (record.kind === "employment") return record.employer.rawText || "Без названия";
  if (record.kind === "technology") return record.display.rawText || "Без названия";
  if (record.kind === "education") return record.institution.rawText || "Без названия";
  if (record.kind === "language") return record.language.rawText || "Без названия";
  return "Кандидат";
}
export function needsCheck(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(needsCheck);
  if (typeof value !== "object" || value === null) return false;
  if ("status" in value && "rawText" in value) return value.rawText !== "" && value.status !== "known";
  return Object.values(value).some(needsCheck);
}
