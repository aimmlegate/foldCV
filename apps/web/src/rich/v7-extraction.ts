import type { Mark, Node, ResolvedPos } from "@tiptap/pm/model";
import { TextSelection, type EditorState, type Transaction } from "@tiptap/pm/state";
import { AddMarkStep, RemoveMarkStep, ReplaceStep, Transform } from "@tiptap/pm/transform";
import { wireMarks, type EditorMarks } from "./inline";
import { containerKey, correctionRange, type ClipboardSource, type LocalContainer, type Placement, type Side, type V7Operation } from "./v7-translation";

type Styles = Extract<V7Operation, { kind: "set_marks" }>["styles"];
/** One operation in optimistic coordinates with the container texts it was expressed against. */
export type ExtractedOperation = { operation: V7Operation; prior: ReadonlyMap<string, string> };
export type Extraction = { kind: "operations"; operations: ExtractedOperation[] } | { kind: "unsupported"; reason: string };
type Located = { container: LocalContainer; node: Node; start: number; depth: number; type: string };

const structureMeta = "foldcv.v7.structure";
const identities = new Set(["templateField", "manualScope", "boundLink"]);
// Python splits and merges authored text blocks only; sections, code, tables and images keep their structure.
const textBlocks = new Set(["paragraph", "heading", "bulletListItem", "numberedListItem", "checkListItem", "toggleListItem", "quote"]);
const editable = new Set([...textBlocks, "section"]);
const flags = new Set(["bold", "italic", "underline", "strike", "code"]);

class Unsupported extends Error {}
function unsupported(reason: string): never { throw new Unsupported(reason); }

const leafText = (leaf: Node) => leaf.type.name === "hardBreak" ? "\n" : "";
function textOf(node: Node, from = 0, to = node.content.size): string { return node.textBetween(from, to, "", leafText); }

function locate(position: ResolvedPos): Located {
  let depth = position.depth;
  while (depth > 0 && !position.node(depth).isTextblock) depth--;
  if (depth < 2) return unsupported("input outside a text container");
  let cellId: string | null = null, outer = depth - 1;
  for (; outer > 0 && position.node(outer).type.name !== "blockContainer"; outer--) {
    const node = position.node(outer), id: unknown = node.attrs["foldcvNodeId"];
    if (node.type.name === "tableCell" || node.type.name === "tableHeader") cellId = typeof id === "string" && id ? id : unsupported("table cell without identity");
  }
  const block = position.node(outer), blockId: unknown = block.attrs["id"], type = block.firstChild?.type.name ?? "";
  if (outer === 0 || typeof blockId !== "string") return unsupported("input outside an identified block");
  const kind = type === "table" ? "cell" : type === "image" ? "caption" : "content";
  if (kind === "content" && !editable.has(type)) return unsupported(`text input in ${type} blocks is not a V7 operation`);
  if (kind === "cell" && cellId === null) return unsupported("table input outside a cell");
  return { container: { blockId, kind, cellId: kind === "cell" ? cellId : null }, node: position.node(depth), start: position.start(depth), depth, type };
}

function find(doc: Node, container: LocalContainer): Located | null {
  let found: Located | null = null;
  doc.descendants((node, pos) => {
    if (found) return false;
    if (node.isTextblock) {
      try {
        const value = locate(doc.resolve(pos + 1));
        if (containerKey(value.container) === containerKey(container)) found = value;
      } catch (error) { if (!(error instanceof Unsupported)) throw error; }
      return false;
    }
    return true;
  });
  return found;
}

function offset(located: Located, pos: number): number { return textOf(located.node, 0, pos - located.start).length; }
function linked(node: Node | null | undefined): boolean { return !!node?.marks.some(mark => mark.type.name === "link"); }
function literal(node: Node | null | undefined): boolean { return !!node && (node.isText || node.type.name === "hardBreak") && !linked(node); }

function stylesOf(marks: readonly Mark[]): Styles {
  const value: EditorMarks = {};
  for (const mark of marks) {
    const name = mark.type.name;
    if (name === "link") continue;
    if (name === "textColor" || name === "backgroundColor") value[name] = String(mark.attrs["stringValue"]);
    else if (name === "bold" || name === "italic" || name === "underline" || name === "strike" || name === "code") value[name] = true;
    else unsupported(`unsupported mark ${name}`);
  }
  try { return wireMarks(value); } catch { return unsupported("unsupported color"); }
}

/** The editor node that received a collapsed insertion decides its side; text never decides ownership. */
function sideAt(doc: Node, pos: number, insertedLink: boolean): Side {
  const position = doc.resolve(pos), parent = position.parent;
  if (identities.has(parent.type.name)) {
    if (parent.type.name === "boundLink") return unsupported("collapsed input inside a bound link");
    if (parent.type.name === "templateField" && parent.attrs["complete"] !== true) return unsupported("input in an incomplete field");
    if (parent.content.size === 0) return "anchor";
    return position.parentOffset === 0 ? "after" : position.parentOffset === parent.content.size ? "before" : "interior";
  }
  // Python inserts literal text only at an addressed literal; inside a link there is none.
  if (insertedLink) return unsupported("input inside a link");
  if (position.textOffset > 0) return linked(parent.child(position.index())) ? unsupported("input inside a link") : "interior";
  const left = position.nodeBefore, right = position.nodeAfter;
  if (literal(left)) return "before";
  if (literal(right)) return "after";
  if (!left) return "before";
  if (!right) return "after";
  return unsupported("input between two non-literal nodes");
}

function replaced(doc: Node, after: Node, step: ReplaceStep): ExtractedOperation {
  const from = locate(doc.resolve(step.from)), to = locate(doc.resolve(step.to));
  if (from.start !== to.start) return unsupported("input spans several containers");
  // Open edge nodes only close partial nodes around the range; any closed node would be new structure.
  const inserted: Node[] = [], content = step.slice.content;
  content.forEach((node, _offset, index) => {
    const open = index === 0 && step.slice.openStart > 0 || index === content.childCount - 1 && step.slice.openEnd > 0;
    const leaves = open && identities.has(node.type.name) ? node.content : null;
    if (leaves) leaves.forEach(child => inserted.push(child));
    else inserted.push(node);
  });
  if (inserted.some(node => !node.isText && node.type.name !== "hardBreak")) unsupported("structured input is not typing");
  const text = step.slice.content.textBetween(0, step.slice.content.size, "", leafText);
  const prior = textOf(from.node), start = offset(from, step.from), end = offset(from, step.to);
  if (!text && start === end) return unsupported("structure-only change");
  const result = find(after, from.container);
  if (!result || textOf(result.node) !== prior.slice(0, start) + text + prior.slice(end)) return unsupported("input changed text outside its range");
  const styles = inserted.map(node => stylesOf(node.marks)), first = styles[0] ?? stylesOf([]);
  if (styles.some(value => JSON.stringify(value) !== JSON.stringify(first))) return unsupported("input with mixed styles");
  const side = start === end ? sideAt(doc, step.from, inserted.some(node => linked(node))) : null;
  return { operation: { kind: "replace_text", container: from.container, start, end, text, styles: first, side },
    prior: new Map([[containerKey(from.container), prior]]) };
}

/** Uniform style runs per container; Python sets all styles of an addressed range. */
function marked(transaction: Transaction): ExtractedOperation[] {
  const doc = transaction.doc, ranges = new Map<string, { located: Located; start: number; end: number }>();
  transaction.steps.forEach((step, index) => {
    if (!(step instanceof AddMarkStep || step instanceof RemoveMarkStep)) return;
    const name = step.mark.type.name;
    if (!flags.has(name) && name !== "textColor" && name !== "backgroundColor") unsupported(`unsupported mark ${name}`);
    const mapping = transaction.mapping.slice(index + 1), from = mapping.map(step.from, 1), to = mapping.map(step.to, -1);
    doc.nodesBetween(from, to, (node, pos) => {
      if (!node.isTextblock) return true;
      const located = locate(doc.resolve(pos + 1)), key = containerKey(located.container);
      const start = offset(located, Math.max(from, located.start)), end = offset(located, Math.min(to, located.start + node.content.size));
      const known = ranges.get(key);
      if (start < end) ranges.set(key, { located, start: Math.min(start, known?.start ?? start), end: Math.max(end, known?.end ?? end) });
      return false;
    });
  });
  const operations: ExtractedOperation[] = [];
  for (const [key, { located, start, end }] of ranges) {
    const runs: { start: number; end: number; styles: Styles }[] = [];
    let cursor = 0;
    located.node.descendants(node => {
      if (!node.isText && node.type.name !== "hardBreak") return true;
      const size = node.isText ? node.text?.length ?? 0 : 1, a = Math.max(cursor, start), b = Math.min(cursor + size, end);
      cursor += size;
      if (a >= b) return false;
      const styles = stylesOf(node.marks), last = runs.at(-1);
      if (last && last.end === a && JSON.stringify(last.styles) === JSON.stringify(styles)) last.end = b;
      else runs.push({ start: a, end: b, styles });
      return false;
    });
    // Marks never change text, so the final container text is also the prior text.
    const prior = textOf(located.node);
    for (const run of runs) operations.push({ operation: { kind: "set_marks", container: located.container, ...run },
      prior: new Map([[key, prior]]) });
  }
  return operations;
}

/** Turn one editor transaction into V7 operations, or refuse input the server cannot express. */
export function extractOperations(transaction: Transaction): Extraction {
  try {
    const structure: unknown = transaction.getMeta(structureMeta);
    if (structure) return { kind: "operations", operations: [structure as ExtractedOperation] };
    if (!transaction.docChanged) return { kind: "operations", operations: [] };
    if (transaction.steps.every(step => step instanceof AddMarkStep || step instanceof RemoveMarkStep))
      return { kind: "operations", operations: marked(transaction) };
    return { kind: "operations", operations: transaction.steps.map((step, index) => {
      if (!(step instanceof ReplaceStep)) return unsupported("structural editor step");
      const before = transaction.docs[index], after = transaction.docs[index + 1] ?? transaction.doc;
      if (!before) return unsupported("missing step document");
      return replaced(before, after, step);
    }) };
  } catch (error) {
    if (error instanceof Unsupported) return { kind: "unsupported", reason: error.message };
    throw error;
  }
}

function collapsedText(state: EditorState): Located & { pos: number; offset: number } {
  const selection = state.selection;
  if (!(selection instanceof TextSelection) || !selection.empty) return unsupported("structure input needs a caret");
  const located = locate(selection.$from);
  return { ...located, pos: selection.from, offset: offset(located, selection.from) };
}
function textBlock(located: Located): void {
  if (located.container.kind !== "content" || !textBlocks.has(located.type)) unsupported(`${located.type} blocks keep their structure`);
}

type Structure = { transaction: Transaction; operation: ExtractedOperation } | { reason: string };
function structure(work: () => { transaction: Transaction; operation: ExtractedOperation }): Structure {
  try {
    const value = work();
    value.transaction.setMeta(structureMeta, value.operation);
    return value;
  } catch (error) {
    if (error instanceof Unsupported) return { reason: error.message };
    throw error;
  }
}

/** Enter: the right half becomes a new sibling with the same type and props; children stay left, as in Python. */
export function splitAt(state: EditorState, created: string): Structure {
  return structure(() => {
    const at = collapsedText(state), position = state.doc.resolve(at.pos), depth = at.depth;
    textBlock(at);
    const block = position.node(depth - 1), relative = at.pos - at.start;
    const blockType = state.schema.nodes["blockContainer"];
    if (!blockType) return unsupported("missing block schema");
    const tr = state.tr.replaceWith(at.start, at.start + at.node.content.size, at.node.content.cut(0, relative));
    const after = tr.mapping.map(position.after(depth - 1));
    tr.insert(after, blockType.create({ ...block.attrs, id: created }, at.node.type.create(at.node.attrs, at.node.content.cut(relative))));
    tr.setSelection(TextSelection.create(tr.doc, after + 2));
    return { transaction: tr, operation: { operation: { kind: "split_block", container: at.container, offset: at.offset, created },
      prior: new Map([[containerKey(at.container), textOf(at.node)]]) } };
  });
}

/** Backspace at a block start or Delete at its end joins adjacent siblings only, as Python does. */
export function mergeAt(state: EditorState, direction: "backward" | "forward"): Structure {
  return structure(() => {
    const at = collapsedText(state), position = state.doc.resolve(at.pos);
    // Away from the edge Backspace/Delete is ordinary text deletion in any container.
    if (direction === "backward" ? at.offset !== 0 : at.offset !== textOf(at.node).length) return unsupported("caret is not at the block edge");
    textBlock(at);
    const depth = at.depth;
    const group = position.node(depth - 2), index = position.index(depth - 2);
    const leadingIndex = direction === "backward" ? index - 1 : index, trailingIndex = leadingIndex + 1;
    if (leadingIndex < 0 || trailingIndex >= group.childCount) return unsupported("no adjacent sibling to merge");
    const leading = group.child(leadingIndex), trailing = group.child(trailingIndex);
    const leadingText = leading.firstChild, trailingText = trailing.firstChild;
    if (!leadingText || !trailingText || !textBlocks.has(leadingText.type.name) || !textBlocks.has(trailingText.type.name))
      return unsupported("only text blocks merge");
    // With children the visually preceding block is not the sibling Python would merge into.
    if (leading.childCount > 1) return unsupported("the leading block has children");
    const leadingId: unknown = leading.attrs["id"], trailingId: unknown = trailing.attrs["id"];
    if (typeof leadingId !== "string" || typeof trailingId !== "string") return unsupported("unidentified sibling");
    const groupStart = position.start(depth - 2);
    let from = groupStart;
    for (let item = 0; item < leadingIndex; item++) from += group.child(item).nodeSize;
    const merged = leading.type.create(leading.attrs, [leadingText.type.create(leadingText.attrs, leadingText.content.append(trailingText.content)),
      ...(trailing.childCount > 1 && trailing.lastChild ? [trailing.lastChild] : [])]);
    const tr = state.tr.replaceWith(from, from + leading.nodeSize + trailing.nodeSize, merged);
    tr.setSelection(TextSelection.create(tr.doc, from + 2 + leadingText.content.size));
    const leadingContainer: LocalContainer = { blockId: leadingId, kind: "content", cellId: null };
    const trailingContainer: LocalContainer = { blockId: trailingId, kind: "content", cellId: null };
    return { transaction: tr, operation: { operation: { kind: "merge_blocks", leading: leadingContainer, trailing: trailingContainer },
      prior: new Map([[containerKey(leadingContainer), textOf(leadingText)], [containerKey(trailingContainer), textOf(trailingText)]]) } };
  });
}

/** Composition updates stay in the editor; their net change becomes one replacement with the first update's side. */
export function foldComposition(operations: readonly ExtractedOperation[]): ExtractedOperation | { reason: string } {
  const first = operations[0];
  if (!first || first.operation.kind !== "replace_text") return { reason: "composition without text input" };
  const container = first.operation.container, key = containerKey(container), prior = first.prior.get(key);
  if (prior === undefined) return { reason: "composition without prior text" };
  let current = prior, start = first.operation.start, end = first.operation.end;
  for (const { operation, prior: expected } of operations) {
    if (operation.kind !== "replace_text" || containerKey(operation.container) !== key || expected.get(key) !== current)
      return { reason: "composition left its container" };
    if (JSON.stringify(operation.styles) !== JSON.stringify(first.operation.styles)) return { reason: "composition changed styles" };
    // Keep the addressed range: a text diff can move an insertion past repeated characters.
    end += Math.max(0, operation.end - (end + current.length - prior.length));
    start = Math.min(start, operation.start);
    current = current.slice(0, operation.start) + operation.text + current.slice(operation.end);
  }
  if (prior === current) return { reason: "composition made no change" };
  const collapsed = start === end;
  if (collapsed && first.operation.side === null) return { reason: "composition without insertion side" };
  const text = current.slice(start, current.length - (prior.length - end));
  return { operation: { ...first.operation, start, end, text, side: collapsed ? first.operation.side : null },
    prior: first.prior };
}

function charPosition(located: Located, offset: number): number {
  let cursor = 0, found = -1;
  located.node.descendants((node, pos) => {
    if (found >= 0) return false;
    if (!node.isText && node.type.name !== "hardBreak") return true;
    const size = node.isText ? node.text?.length ?? 0 : 1;
    if (offset >= cursor && offset < cursor + size) found = located.start + pos + (offset - cursor);
    cursor += size;
    return false;
  });
  return found >= 0 ? found : unsupported("offset outside the container text");
}

export type TextPoint = { container: LocalContainer; offset: number };
/** A caret as container text offset; null outside editable text containers. */
export function textPoint(doc: Node, pos: number): TextPoint | null {
  try { const located = locate(doc.resolve(pos)); return { container: located.container, offset: offset(located, pos) }; }
  catch (error) { if (error instanceof Unsupported) return null; throw error; }
}
/** Left-biased: just after the preceding character, inside its node, where typing continues after a re-projection. */
export function textPosition(doc: Node, point: TextPoint): number | null {
  const located = find(doc, point.container);
  if (!located) return null;
  try { return point.offset <= 0 ? located.start : charPosition(located, Math.min(point.offset, textOf(located.node).length) - 1) + 1; }
  catch (error) { if (error instanceof Unsupported) return located.start; throw error; }
}

export function containerText(doc: Node, container: LocalContainer): string | null {
  const located = find(doc, container);
  return located ? textOf(located.node) : null;
}

/** Show retained text in an editor container (recovery display); structure stays the server's after re-projection. */
export function showText(tr: Transaction, container: LocalContainer, text: string): boolean {
  const located = find(tr.doc, container);
  if (!located) return false;
  const range = correctionRange(textOf(located.node), text);
  if (!range) return true;
  const from = range.start < range.end ? charPosition(located, range.start)
    : range.start === 0 ? located.start : charPosition(located, range.start - 1) + 1;
  const to = range.start < range.end ? charPosition(located, range.end - 1) + 1 : from;
  if (range.text) tr.insertText(range.text, from, to); else tr.delete(from, to);
  return true;
}

/** Retry after a block: the canonical-to-editor change of one container; an insertion takes its side from the editor node holding it. */
export function correctionOperation(doc: Node, container: LocalContainer, canonical: string): ExtractedOperation | { reason: string } | null {
  try {
    const located = find(doc, container) ?? unsupported("container is not in the editor");
    const range = correctionRange(canonical, textOf(located.node));
    if (!range) return null;
    const prior = new Map([[containerKey(container), canonical]]);
    if (!range.text) return { operation: { kind: "replace_text", container, start: range.start, end: range.end, text: "", styles: stylesOf([]), side: null }, prior };
    const from = charPosition(located, range.start), to = charPosition(located, range.start + range.text.length - 1) + 1;
    const inserted: Node[] = [];
    doc.nodesBetween(from, to, node => { if (node.isText || node.type.name === "hardBreak") inserted.push(node); return true; });
    const styles = inserted.map(node => stylesOf(node.marks)), first = styles[0] ?? stylesOf([]);
    if (styles.some(value => JSON.stringify(value) !== JSON.stringify(first))) return unsupported("correction with mixed styles");
    let side: Side | null = null;
    if (range.start === range.end) {
      if (doc.resolve(from).parent !== doc.resolve(to).parent) return unsupported("inserted text spans several nodes");
      side = sideAt(new Transform(doc).delete(from, to).doc, from, inserted.some(node => linked(node)));
    }
    return { operation: { kind: "replace_text", container, start: range.start, end: range.end, text: range.text, styles: first, side }, prior };
  } catch (error) {
    if (error instanceof Unsupported) return { reason: error.message };
    throw error;
  }
}

/** Whole sibling blocks under a text selection: from the start of the first to the end of the last (two or more),
 * or to the start of the next sibling. Anything else is text, not structure. */
export function selectedBlocks(state: EditorState): string[] | null {
  const selection = state.selection;
  if (!(selection instanceof TextSelection) || selection.empty) return null;
  try {
    // Text offsets, not node positions: a caret at a block start may sit inside its first field node.
    const from = locate(selection.$from), to = locate(selection.$to);
    if (from.container.kind !== "content" || to.container.kind !== "content" || offset(from, selection.from) !== 0) return null;
    const $from = state.doc.resolve(selection.from), $to = state.doc.resolve(selection.to);
    const groupDepth = from.depth - 2;
    if (to.depth - 2 !== groupDepth || $to.start(groupDepth) !== $from.start(groupDepth)) return null;
    const group = $from.node(groupDepth), first = $from.index(groupDepth), end = offset(to, selection.to);
    let last = $to.index(groupDepth);
    if (end === 0 && last > first) last--;
    else if (end !== textOf(to.node).length || last === first || group.child(last).childCount > 1) return null;
    const ids: string[] = [];
    for (let index = first; index <= last; index++) {
      const id: unknown = group.child(index).attrs["id"];
      if (typeof id !== "string") return null;
      ids.push(id);
    }
    return ids;
  } catch (error) { if (error instanceof Unsupported) return null; throw error; }
}

export type Insertion = { container: LocalContainer; start: number; end: number; side: Side | null; prior: string };
/** One container's selected range, or a caret with the side Python addresses for an insertion there. */
export function insertionAt(state: EditorState): Insertion | { reason: string } {
  try {
    const selection = state.selection;
    if (!(selection instanceof TextSelection)) return unsupported("input needs a text selection");
    const from = locate(selection.$from), to = locate(selection.$to);
    if (from.start !== to.start) return unsupported("input spans several containers");
    const start = offset(from, selection.from), end = offset(from, selection.to);
    return { container: from.container, start, end, side: start === end ? sideAt(state.doc, selection.from, false) : null, prior: textOf(from.node) };
  } catch (error) {
    if (error instanceof Unsupported) return { reason: error.message };
    throw error;
  }
}

/** What a copy names for Python: whole sibling blocks, or a text range inside one block. */
export function copySource(state: EditorState): ClipboardSource | null {
  const blocks = selectedBlocks(state);
  if (blocks) return { kind: "blocks", blockIds: blocks };
  const at = insertionAt(state);
  if ("reason" in at || at.start === at.end || at.container.kind !== "content") return null;
  return { kind: "range", container: at.container, start: at.start, end: at.end, prior: at.prior };
}

/** Where a block sits: its parent block or region and the sibling before it. Regions themselves have none. */
export function placementOf(doc: Node, blockId: string): Placement | null {
  let done = false, found: Placement | null = null;
  doc.descendants((node, pos) => {
    if (done) return false;
    if (node.type.name !== "blockContainer" || node.attrs["id"] !== blockId) return true;
    done = true;
    const position = doc.resolve(pos), index = position.index();
    const owner = position.depth >= 2 ? position.node(position.depth - 1) : null;
    const parentId: unknown = owner?.attrs["id"], afterId: unknown = index > 0 ? position.parent.child(index - 1).attrs["id"] : null;
    if (owner?.type.name === "blockContainer" && typeof parentId === "string" && (afterId === null || typeof afterId === "string"))
      found = { parentId, afterId };
    return false;
  });
  return found;
}

/** The item section whose children are exactly these blocks, in order, with its sibling order. */
export function itemOf(doc: Node, ids: readonly string[]): { id: string; parentId: string; siblings: string[] } | null {
  let found: { id: string; parentId: string; siblings: string[] } | null = null;
  doc.descendants((node, pos) => {
    if (found) return false;
    const group = node.lastChild;
    if (node.type.name !== "blockContainer" || node.firstChild?.type.name !== "section" || node.childCount < 2 || !group) return true;
    const children: unknown[] = [];
    group.forEach(child => children.push(child.attrs["id"]));
    if (children.length !== ids.length || children.some((id, index) => id !== ids[index])) return true;
    const position = doc.resolve(pos), owner = position.depth >= 2 ? position.node(position.depth - 1) : null;
    const id: unknown = node.attrs["id"], parentId: unknown = owner?.attrs["id"], siblings: string[] = [];
    position.parent.forEach(child => siblings.push(String(child.attrs["id"])));
    if (owner?.type.name === "blockContainer" && typeof id === "string" && typeof parentId === "string") found = { id, parentId, siblings };
    return false;
  });
  return found;
}

/** The innermost block holding the caret. */
export function blockAt(state: EditorState): string | null {
  const position = state.selection.$head;
  for (let depth = position.depth; depth > 0; depth--) {
    const node = position.node(depth);
    if (node.type.name === "blockContainer") { const id: unknown = node.attrs["id"]; return typeof id === "string" ? id : null; }
  }
  return null;
}

/** Styles and insertion side for replacing [start, end) of a container: taken from the editor text being replaced,
 * or, for an insertion, from the node that would receive it. */
export function replacementAt(doc: Node, container: LocalContainer, start: number, end: number): { styles: Styles; side: Side | null } | { reason: string } {
  try {
    const located = find(doc, container) ?? unsupported("container is not in the editor");
    if (start < end) {
      const from = charPosition(located, start), node = doc.resolve(from).nodeAfter;
      return { styles: stylesOf(node?.marks ?? []), side: null };
    }
    const pos = start === 0 ? located.start : charPosition(located, start - 1) + 1;
    const node = doc.resolve(pos).nodeBefore ?? doc.resolve(pos).nodeAfter;
    return { styles: stylesOf(node?.isText ? node.marks : []), side: sideAt(doc, pos, false) };
  } catch (error) {
    if (error instanceof Unsupported) return { reason: error.message };
    throw error;
  }
}
