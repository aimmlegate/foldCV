/** A block reworded on the user's request (a trial): what the preview holds and how its parts are named. */

export type RewordValue = { id: string; recordId: string; field: string; kind: string; before: string; after: string | null;
  state: "changed" | "same" | "refused"; reason: string | null; words: string[]; source: string[] };
/** reword: «Изменить формулировку», each value from its own source lines; write: «Написать заново по резюме», a text
 * block written again from the CV's lines (F6a). */
export type RewordMode = "reword" | "write";
export type RewordPreview = { requestId: string; blockId: string; values: RewordValue[]; touched: Record<string, string>; mode?: RewordMode };
/** The blocks the panel can work on: the request text «По правилам» puts in, and the ones that can be written again. */
export type RewordBlocks = { rules: Record<string, string>; write: string[] };
/** `edited`: the user changed the text the preview gave; an unchanged value stays the model's (D179). */
export type RewordChange = { recordId: string; field: string; value: string; edited: boolean };
/** The longest value the service takes in an Apply (RewordChange.value in Python). */
export const valueLimit = 4000;

const kinds: Readonly<Record<string, string>> = { tasks: "Задача", results: "Результат", "project.description": "Описание проекта",
  "role_details.scope": "Зона ответственности", "role_details.involvement": "Вовлечённость", text: "Текст", items: "Пункт" };
export function kindLabel(kind: string): string { return kinds[kind] ?? kind; }

const reasons: Readonly<Record<string, string>> = { long: "текст стал слишком длинным",
  number: "появилось число, которого нет в тексте и в оригинале", name: "появилось название, которого нет в тексте и в оригинале",
  mixed: "слово написано буквами двух алфавитов" };
// A text written from the CV is checked against the CV's lines that were sent, not against a present text.
const written: Readonly<Record<string, string>> = { long: "текст слишком длинный", number: "появилось число, которого нет в резюме",
  name: "появилось название, которого нет в резюме", mixed: "слово написано буквами двух алфавитов",
  lines: "текст не назвал ни одной строки резюме", empty: "модель не написала текст",
  language: "текст написан не на языке резюме" };
/** Why code did not take the model's text, in words for the user. */
export function refusalLabel(value: RewordValue, mode: RewordMode = "reword"): string {
  const reason = (mode === "write" ? written : reasons)[value.reason ?? ""] ?? "текст не прошёл проверку";
  return value.words.length ? `${reason}: ${value.words.join(", ")}` : reason;
}

/** The block the pointer is over that can be reworded: the nearest ancestor with one of the ids. */
export function rewordTarget(target: Element | null, ids: ReadonlySet<string>): HTMLElement | null {
  for (let element = target?.closest<HTMLElement>("[data-id]") ?? null; element; element = element.parentElement?.closest<HTMLElement>("[data-id]") ?? null) {
    if (ids.has(element.getAttribute("data-id") ?? "")) return element;
  }
  return null;
}

/** The two actions of the panel with the one line that says what each does (F6a, sketch A1). */
export const REWORD_MODES: readonly { mode: RewordMode; label: string; line: string }[] = [
  { mode: "reword", label: "Изменить формулировку", line: "Тот же смысл, другие слова. Новых фактов нет." },
  { mode: "write", label: "Написать заново по резюме", line: "Новый текст по всему резюме, без контактов." },
];

/** The request a switch to another action leaves in the field: the block's rules where the field is empty or holds a
 * ready request of the other action, else what the user wrote. */
export function instructionFor(mode: RewordMode, instruction: string, rules: string, presets: readonly string[]): string {
  if (mode === "write" && rules && (!instruction.trim() || presets.includes(instruction))) return rules;
  return instruction;
}

/** What the panel says above a preview of «Написать заново по резюме» that has nothing to apply; null when it has. */
export function writeNote(preview: RewordPreview): string | null {
  const value = preview.values[0];
  if (!value || value.state === "changed") return null;
  if (value.state === "same") return "Модель вернула прежний текст.";
  if (value.reason === "empty") return "Модель не написала текст. Измените запрос и попробуйте ещё раз.";
  return null;
}
