/** A block reworded on the user's request (a trial): what the preview holds and how its parts are named. */

export type RewordValue = { id: string; recordId: string; field: string; kind: string; before: string; after: string | null;
  state: "changed" | "same" | "refused" | "present"; reason: string | null; words: string[]; source: string[]; keep?: boolean };
/** reword: «Изменить формулировку», each value from its own source lines; write: «Написать заново по резюме», a text
 * block written again from the CV's lines (F6a). */
export type RewordMode = "reword" | "write";
/** A new item of a list written again (F6b): `added` when code keeps it, `refused` with the reason. */
export type WrittenItem = { id: string; text: string; lines: string[]; source: string[]; state: "added" | "refused"; reason: string | null;
  words: string[] };
export type RewordPreview = { requestId: string; blockId: string; values: RewordValue[]; touched: Record<string, string>; mode?: RewordMode;
  shape?: "text" | "items"; added?: WrittenItem[] };
/** The Apply of a list written again: the present items that go (record ids) and the new items that come. */
export type ListApply = { removed: string[]; added: { text: string; lines: string[]; edited: boolean }[] };
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
  language: "текст написан не на языке резюме", duplicate: "такой пункт уже есть" };
/** Why code did not take the model's text, in words for the user. */
export function refusalLabel(value: Pick<RewordValue, "reason" | "words">, mode: RewordMode = "reword"): string {
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

/** What the user does with a list preview (sketch L1): the present items kept («оставить»), the new items unticked, and
 * the new items' texts as edited. */
export type ListDraft = { requestId: string; keep: ReadonlySet<string>; skipped: ReadonlySet<string>; texts: Readonly<Record<string, string>> };

/** A list preview starts with «оставить» on for the user's own items and every kept new item ticked (the owner, D2b). */
export function listDraft(preview: RewordPreview): ListDraft {
  return { requestId: preview.requestId, keep: new Set(preview.values.filter(value => value.keep).map(value => value.recordId)),
    skipped: new Set(), texts: {} };
}

/** The Apply a list preview and its draft make; `ready` is false when it changes nothing or leaves the list empty. */
export function listApply(preview: RewordPreview, draft: ListDraft): ListApply & { ready: boolean } {
  const removed = preview.values.filter(value => !draft.keep.has(value.recordId)).map(value => value.recordId);
  const added = (preview.added ?? []).filter(item => item.state === "added" && !draft.skipped.has(item.id))
    .map(item => ({ item, text: (draft.texts[item.id] ?? item.text).trim() })).filter(value => value.text)
    .map(({ item, text }) => ({ text, lines: item.lines, edited: text !== item.text.trim() }));
  const left = preview.values.length - removed.length + added.length;
  return { removed, added, ready: (removed.length > 0 || added.length > 0) && left > 0 };
}

/** The note above a list preview with no new item to take; null when it has one. */
export function listNote(preview: RewordPreview): string | null {
  const added = preview.added ?? [];
  if (added.length === 0) return "Модель не написала пунктов. Измените запрос и попробуйте ещё раз.";
  if (!added.some(item => item.state === "added")) return "Ни один пункт не прошёл проверку.";
  return null;
}
