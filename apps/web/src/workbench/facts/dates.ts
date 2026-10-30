import type { WorkingFieldPartialDate } from "../../contracts/generated/working_facts";

export type DatePrecision = "year" | "month" | "day" | "text";
const pad = (value: number) => String(value).padStart(2, "0");

export function dateText(field: WorkingFieldPartialDate): string {
  const value = field.value;
  if (field.status !== "known" || !value) return field.rawText;
  const year = String(value.year).padStart(4, "0");
  if (value.precision === "year") return year;
  if (value.month === null) return field.rawText;
  const month = `${year}-${pad(value.month)}`;
  return value.precision === "day" && value.day !== null ? `${month}-${pad(value.day)}` : month;
}

export function datePrecision(text: string): DatePrecision {
  return /^\d{4}$/.test(text) ? "year" : /^\d{4}-\d{2}$/.test(text) ? "month" : /^\d{4}-\d{2}-\d{2}$/.test(text) ? "day" : "text";
}

/** `source` is the fact's raw text: "text" shows that, never the normalized date. */
export function changePrecision(text: string, precision: DatePrecision, source = ""): string {
  if (precision === "text") return source || text;
  const current = datePrecision(text);
  if (current === "text") return "";
  const length = precision === "year" ? 4 : precision === "month" ? 7 : 10;
  return text.length >= length ? text.slice(0, length) : "";
}
