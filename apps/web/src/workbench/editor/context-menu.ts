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
