/** A block reworded on the user's request (a trial): what the preview holds and how its parts are named. */

export type RewordValue = { id: string; recordId: string; field: string; kind: string; before: string; after: string | null;
  state: "changed" | "same" | "refused"; reason: string | null; words: string[]; source: string[] };
export type RewordPreview = { requestId: string; blockId: string; values: RewordValue[]; touched: Record<string, string> };
export type RewordChange = { recordId: string; field: string; value: string };
/** The longest value the service takes in an Apply (RewordChange.value in Python). */
export const valueLimit = 4000;

const kinds: Readonly<Record<string, string>> = { tasks: "Задача", results: "Результат", "project.description": "Описание проекта",
  "role_details.scope": "Зона ответственности", "role_details.involvement": "Вовлечённость", text: "Текст", items: "Пункт" };
export function kindLabel(kind: string): string { return kinds[kind] ?? kind; }

const reasons: Readonly<Record<string, string>> = { long: "текст стал слишком длинным",
  number: "появилось число, которого нет в тексте и в оригинале", name: "появилось название, которого нет в тексте и в оригинале",
  mixed: "слово написано буквами двух алфавитов" };
/** Why code did not take the model's text, in words for the user. */
export function refusalLabel(value: RewordValue): string {
  const reason = reasons[value.reason ?? ""] ?? "текст не прошёл проверку";
  return value.words.length ? `${reason}: ${value.words.join(", ")}` : reason;
}

/** The block the pointer is over that can be reworded: the nearest ancestor with one of the ids. */
export function rewordTarget(target: Element | null, ids: ReadonlySet<string>): HTMLElement | null {
  for (let element = target?.closest<HTMLElement>("[data-id]") ?? null; element; element = element.parentElement?.closest<HTMLElement>("[data-id]") ?? null) {
    if (ids.has(element.getAttribute("data-id") ?? "")) return element;
  }
  return null;
}
