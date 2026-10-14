import { Fragment, Slice, type Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, type EditorState, type Transaction } from "@tiptap/pm/state";

export function deleteAcrossRegions(state: EditorState): Transaction | null {
  const { from, to } = state.selection;
  if (from === to) return null;
  const ranges: { from: number; to: number }[] = [];
  state.doc.firstChild?.forEach((node, offset) => {
    if (node.firstChild?.type.name !== "region") return;
    const children = node.lastChild;
    if (children?.type.name !== "blockGroup") return;
    const start = 1 + offset + 1 + node.firstChild.nodeSize + 1;
    const end = start + children.content.size;
    if (from < end && to > start) ranges.push({ from: Math.max(start, from), to: Math.min(end, to) });
  });
  if (ranges.length < 2) return null;
  const tr = state.tr;
  for (const range of ranges.reverse()) tr.delete(range.from, range.to);
  return tr.scrollIntoView();
}

export function flattenPastedRegions(slice: Slice): Slice | null {
  let found = false;
  function flatten(fragment: Fragment): PMNode[] {
    const result: PMNode[] = [];
    fragment.forEach(node => {
      if (node.type.name === "blockContainer" && node.firstChild?.type.name === "region") {
        found = true; if (node.lastChild?.type.name === "blockGroup") result.push(...flatten(node.lastChild.content));
      } else if (node.type.name === "blockGroup") result.push(...flatten(node.content));
      else result.push(node.copy(Fragment.fromArray(node.content.content.map(child => child.type.name === "blockGroup"
        ? child.copy(Fragment.fromArray(flatten(child.content))) : child))));
    });
    return result;
  }
  const nodes = flatten(slice.content);
  return found ? new Slice(Fragment.fromArray(nodes), 0, 0) : null;
}

/** Pasted region wrappers carry content, never another fixed layout container. */
export function pastedRegionsPlugin() {
  return new Plugin({ key: new PluginKey("foldcv-pasted-regions"), appendTransaction: (_transactions, _before, after) => {
    const positions: { from: number; to: number; content: Fragment }[] = [];
    after.doc.descendants((node, pos) => {
      if (node.type.name !== "blockContainer" || node.firstChild?.type.name !== "region" || after.doc.resolve(pos).depth <= 1) return;
      const paragraph = after.schema.nodes["paragraph"], container = after.schema.nodes["blockContainer"];
      const content = node.lastChild?.type.name === "blockGroup" ? node.lastChild.content
        : paragraph && container ? Fragment.from(container.create(null, paragraph.create())) : Fragment.empty;
      positions.push({ from: pos, to: pos + node.nodeSize, content });
      return false;
    });
    if (!positions.length) return null;
    const tr = after.tr;
    for (const position of positions.reverse()) tr.replaceWith(position.from, position.to, position.content);
    return tr;
  } });
}
