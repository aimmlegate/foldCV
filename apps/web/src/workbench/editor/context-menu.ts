/** The items of the page's own context menu (F5 of the tester feedback of 2026-11-23): each one shows only when it can
 * run (P1). A pure function of what the editor says about the selection and the block under the pointer. */
export type MenuItem = "cut" | "copy" | "paste" | "rewrite" | "reword" | "removeBlock";

export type MenuState = {
  /** No selection, a selection in one container, over containers, or of whole blocks. */
  selection: "none" | "one" | "range" | "blocks";
  /** The session can cut the selection: not a technology line, not over the edge of one. */
  cuttable: boolean;
  /** The editor takes input. */
  editable: boolean;
  /** The selected text can be reworded by «Изменить текст». */
  rewritable: boolean;
  /** With no selection: the caret block can be reworded by «Переписать блок». */
  rewordable: boolean;
  /** A text block under the pointer that is not a technology line. */
  block: string | null;
};

export const MENU_LABELS: Readonly<Record<MenuItem, string>> = {
  cut: "Вырезать", copy: "Копировать", paste: "Вставить", rewrite: "Изменить текст", reword: "Переписать блок",
  removeBlock: "Удалить блок",
};

export function menuItems(state: MenuState): MenuItem[] {
  const items: MenuItem[] = [], selected = state.selection !== "none";
  if (selected && state.editable && state.cuttable) items.push("cut");
  if (selected) items.push("copy");
  if (state.editable) items.push("paste");
  if (state.selection === "one" && state.editable && state.rewritable) items.push("rewrite");
  if (!selected && state.editable && state.rewordable) items.push("reword");
  if (state.editable && state.block !== null) items.push("removeBlock");
  return items;
}

const wordChar = /[\p{L}\p{N}\p{M}]/u;
// Joins two word characters into one word: a hyphen or an apostrophe («Ростов-на-Дону», «O'Neil»), and a point or a comma
// between digits (3.5, 1,5).
const joiner = (text: string, at: number): boolean => {
  const char = text.charAt(at), before = text.charAt(at - 1), after = text.charAt(at + 1);
  if (!wordChar.test(before) || !wordChar.test(after)) return false;
  return /[-‐'’]/u.test(char) || /[.,]/u.test(char) && /\d/u.test(before) && /\d/u.test(after);
};
const inWord = (text: string, at: number): boolean => at >= 0 && at < text.length && (wordChar.test(text.charAt(at)) || joiner(text, at));

/** The word of a text container at a place between two characters (remark 3 after stop 4): the word that the character
 * after the place belongs to, else the one before it; null where neither is a word character. The same limits on every
 * engine: WebKit selects a word itself before the menu event, Chromium on Windows does not. */
export function wordAt(text: string, offset: number): { start: number; end: number } | null {
  const at = inWord(text, offset) && wordChar.test(text.charAt(offset)) ? offset
    : inWord(text, offset - 1) && wordChar.test(text.charAt(offset - 1)) ? offset - 1 : -1;
  if (at < 0) return null;
  let start = at, end = at + 1;
  while (inWord(text, start - 1)) start--;
  while (inWord(text, end)) end++;
  return { start, end };
}
