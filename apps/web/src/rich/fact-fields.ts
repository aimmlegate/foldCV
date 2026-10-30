import type { WorkingFacts, WorkingFieldPartialDate } from "../contracts/generated/working_facts";

export type RecordValue = WorkingFacts["records"][number];
export type Kind = "candidate" | "employment" | "technology" | "education" | "language" | "claim";
type Field = { key: string; label: string; text: string; checked?: boolean; date?: WorkingFieldPartialDate };
export const labels = { candidate: "Кандидат", employment: "Опыт", technology: "Технологии", education: "Образование", language: "Языки", claim: "Дополнительно" };
export const names: Record<Kind, readonly (readonly [string, string])[]> = {
  candidate: [["name", "Имя"], ["title", "Должность"], ["location", "Город"]],
  employment: [["employer", "Компания"], ["role", "Роль"]], technology: [["display", "Технология"], ["experience", "Опыт, как в резюме"]],
  education: [["institution", "Учебное заведение"], ["qualification", "Квалификация"], ["specialty", "Специальность"], ["completion", "Дата окончания"]],
  language: [["language", "Язык"], ["level", "Уровень"]],
  claim: [["value", "Текст"]],
};
export function fields(record: RecordValue): Field[] {
  if (!(record.kind in names)) return [];
  const values = Object.entries(record);
  const result: Field[] = names[record.kind as Kind].map(([key, label]) => {
    const value: unknown = values.find(([name]) => name === key)?.[1];
    return { key, label, text: typeof value === "object" && value !== null && "rawText" in value && typeof value.rawText === "string" ? value.rawText : "",
      ...(record.kind === "education" && key === "completion" ? { date: record.completion } : {}) };
  });
  if (record.kind === "employment") record.periods.forEach((period, index) => {
    result.push({ key: `period:${period.id}:start`, label: `Начало ${index + 1}`, text: period.start.rawText, date: period.start },
      { key: `period:${period.id}:end`, label: `Окончание ${index + 1}`, text: period.end.rawText, date: period.end });
  });
  return [...result, ...(record.kind === "employment" ? record.periods.map((period, index) => ({ key: `period:${period.id}:present`,
    label: `Работаю сейчас ${index + 1}`, text: period.present.rawText, checked: period.present.value === true })) : [])];
}
/** The record's fields the dialog offers: those the document shows or has a place for. */
export function offeredFields(record: RecordValue, unshown: readonly string[] = []): Field[] {
  return fields(record).filter(field => !unshown.includes(field.key));
}
export function title(record: RecordValue): string {
  if (record.kind === "employment") return record.employer.rawText || "Без названия";
  if (record.kind === "technology") return record.display.rawText || "Без названия";
  if (record.kind === "education") return record.institution.rawText || "Без названия";
  if (record.kind === "language") return record.language.rawText || "Без названия";
  if (record.kind === "claim") return record.value.rawText || "Новый факт";
  return "Кандидат";
}
/** An end label of a current period, as «по настоящее время» or «н.в.». */
export function currentMarker(text: string): boolean {
  return /^(?:present|current|now|настоящее время|по настоящее время|н\.?\s*в\.?)$/iu.test(text.trim());
}
/** Text the user wrote or corrected is authoritative, so it is never a value to check. */
export function userCorrected(value: unknown): boolean {
  return typeof value === "object" && value !== null && "userCorrected" in value && value.userCorrected === true;
}
export function needsCheck(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(needsCheck);
  if (typeof value !== "object" || value === null) return false;
  if ("status" in value && "rawText" in value) return value.rawText !== "" && value.status !== "known" && !userCorrected(value);
  const current = "present" in value && typeof value.present === "object" && value.present !== null
    && "value" in value.present && value.present.value === true;
  if (current && "end" in value && typeof value.end === "object" && value.end !== null
    && "rawText" in value.end && typeof value.end.rawText === "string" && value.end.rawText.trim()) {
    if (!currentMarker(value.end.rawText) && !userCorrected(value.end)) return true;
    return Object.entries(value).some(([key, field]) => key !== "end" && needsCheck(field));
  }
  return Object.entries(value).some(([key, field]) =>
    !(key === "canonicalId" && "kind" in value && value.kind === "technology") && needsCheck(field));
}
