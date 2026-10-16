import type { Node, ResolvedPos } from "@tiptap/pm/model";
import { AllSelection, TextSelection, type Transaction } from "@tiptap/pm/state";

type Point = { block: string; cell: string | null; offset: number };
type Caret = { kind: "text"; anchor: Point; head: Point } | { kind: "all" } | null;

function identity(position: ResolvedPos): Omit<Point, "offset"> | null {
  let block: string | null = null, cell: string | null = null;
  for (let depth = position.depth; depth > 0; depth--) {
    const node = position.node(depth);
    if (cell === null && ["tableCell", "tableHeader"].includes(node.type.name) && typeof node.attrs["foldcvNodeId"] === "string") cell = node.attrs["foldcvNodeId"];
    if (block === null && node.type.name === "blockContainer" && typeof node.attrs["id"] === "string") block = node.attrs["id"];
  }
  return block === null ? null : { block, cell };
}

function point(position: ResolvedPos): Point | null {
  const key = identity(position);
  if (!key) return null;
  for (let depth = position.depth; depth > 0; depth--) {
    if (position.node(depth).isTextblock) return { ...key, offset: position.pos - position.start(depth) };
  }
  return null;
}

export function captureCaret(tr: Transaction): Caret {
  if (tr.selection instanceof AllSelection) return { kind: "all" };
  if (!(tr.selection instanceof TextSelection)) return null;
  const anchor = point(tr.selection.$anchor), head = point(tr.selection.$head);
  return anchor && head ? { kind: "text", anchor, head } : null;
}

function locate(doc: Node, target: Point): number | null {
  let found: number | null = null;
  doc.descendants((node, pos) => {
    if (found !== null || !node.isTextblock) return;
    const key = identity(doc.resolve(pos + 1));
    if (key?.block === target.block && key.cell === target.cell) found = pos + 1 + Math.min(target.offset, node.content.size);
  });
  return found;
}

// Whole-region replacement has no useful position mapping; stable IDs retain the user's selection.
export function restoreCaret(tr: Transaction, caret: Caret): void {
  if (!caret) return;
  if (caret.kind === "all") { tr.setSelection(new AllSelection(tr.doc)); return; }
  const anchor = locate(tr.doc, caret.anchor), head = locate(tr.doc, caret.head);
  if (anchor !== null && head !== null) tr.setSelection(TextSelection.create(tr.doc, anchor, head));
  else if (anchor !== null || head !== null) tr.setSelection(TextSelection.near(tr.doc.resolve(anchor ?? head ?? 0)));
}
