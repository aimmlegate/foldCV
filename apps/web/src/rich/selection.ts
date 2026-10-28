import { Selection, TextSelection, type EditorState, type Transaction } from "@tiptap/pm/state";
import type { ResolvedPos } from "@tiptap/pm/model";
import type { BlockKind } from "./v7-translation";

export function selectionLocation(tr: Transaction): string | null {
  const position = tr.selection.$head;
  let cell: string | null = null;
  for (let depth = position.depth; depth > 0; depth--) {
    const node = position.node(depth), id: unknown = node.attrs["id"], cellId: unknown = node.attrs["foldcvNodeId"];
    if ((node.type.name === "tableCell" || node.type.name === "tableHeader") && typeof cellId === "string") cell = cellId;
    if (node.type.name === "blockContainer" && typeof id === "string") return JSON.stringify([id, cell]);
  }
  return null;
}

// An item section's own line is hidden in the editor (`.cv-section-title`): text there would not show.
const hidden = ($pos: ResolvedPos) => $pos.parent.type.name === "section";

function shownFrom(state: EditorState, $pos: ResolvedPos, direction: -1 | 1): ResolvedPos | null {
  let at = $pos;
  for (let step = 0; step < 1000; step++) {
    if (at.parent.isTextblock && !hidden(at)) return at;
    // Inside a hidden line the search starts past it; a gap position searches from itself.
    const from = at.parent.isTextblock ? state.doc.resolve(direction > 0 ? at.after() : at.before()) : at;
    const found = Selection.findFrom(from, direction, true);
    if (!found || found.$head.pos === at.pos) return null;
    at = found.$head;
  }
  return null;
}

/** A caret in a hidden section line or in a gap between blocks, moved on to shown text the way it went; a click (no
 * previous selection) goes into the item. Ranges stay: one from an item's line to the next names whole items. Null when
 * nothing moves. */
export function shownSelection(previous: Selection | null, state: EditorState): Selection | null {
  const selection = state.selection;
  if (!selection.empty || selection instanceof TextSelection && !hidden(selection.$head)) return null;
  const direction = previous && selection.head < previous.head ? -1 : 1;
  const head = shownFrom(state, selection.$head, direction) ?? shownFrom(state, selection.$head, direction > 0 ? -1 : 1);
  return head ? TextSelection.between(head, head) : null;
}

/** Editor content node names of the block kinds `format_blocks` changes. */
const KINDS: Readonly<Record<string, BlockKind["type"]>> = { paragraph: "paragraph", heading: "heading",
  bulletListItem: "bullet_list", numberedListItem: "numbered_list" };
export type TextBlock = { id: string; type: BlockKind["type"]; level: number | null };
export type BlockStyle = "p" | "h2" | "h3" | "list" | "numbered";

/** The text blocks a selection reaches into, in document order; a caret names its own block. A range that ends at
 * the start of a block, as a whole-block selection does, does not reach that block. */
export function selectedTextBlocks(state: EditorState): TextBlock[] {
  const { from, to, empty } = state.selection, blocks: TextBlock[] = [];
  state.doc.nodesBetween(Math.max(0, from - 1), Math.min(state.doc.content.size, to + 1), (node, pos) => {
    if (node.type.name !== "blockContainer") return true;
    const content = node.firstChild, id: unknown = node.attrs["id"], type = content ? KINDS[content.type.name] : undefined;
    if (!content || !type || typeof id !== "string") return true;
    // Text runs from `start` to `end`; an empty block is reached when the range passes over it.
    const start = pos + 2, end = start + content.content.size;
    const reached = empty ? from >= start && from <= end : start === end ? from <= start && to > start : from < end && to > start;
    const level: unknown = content.attrs["level"];
    if (reached) blocks.push({ id, type, level: type === "heading" && typeof level === "number" ? level : null });
    return true;
  });
  return blocks;
}

/** The kind a toolbar style gives the selected blocks: a list button on blocks that are all that list turns them back
 * into paragraphs. */
export function styledKind(style: BlockStyle, blocks: readonly TextBlock[]): BlockKind {
  if (style === "h2" || style === "h3") return { type: "heading", level: style === "h2" ? 2 : 3 };
  const list = style === "list" ? "bullet_list" : style === "numbered" ? "numbered_list" : null;
  if (!list || blocks.length > 0 && blocks.every(block => block.type === list)) return { type: "paragraph" };
  return list === "bullet_list" ? { type: "bullet_list" } : { type: "numbered_list", start: null };
}

/** Blocks a kind would change; a block that already has it is left out of the request. */
export function changedBy(kind: BlockKind, blocks: readonly TextBlock[]): string[] {
  return blocks.filter(block => block.type !== kind.type || kind.type === "heading" && block.level !== kind.level)
    .map(block => block.id);
}

/** The style select value of a text block: headings of level 1 and 2 read as «Заголовок». */
export function blockStyle(block: TextBlock | undefined): "p" | "h2" | "h3" {
  if (block?.type !== "heading") return "p";
  return block.level === 3 ? "h3" : "h2";
}
