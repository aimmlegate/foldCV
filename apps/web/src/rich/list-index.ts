/** Numbers for numbered list items. BlockNote keeps its numbering plugin inside the "numbered-list-item-shortcuts"
 * extension, which the session disables for its input rules and shortcuts; without a number the marker showed only
 * its dot. The numbers are decorations, outside the document, as the engine's own are. */

import type { Node } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export type ListIndex = { from: number; to: number; index: number };

/** Each numbered item's content node with its number: its own `start` when it has one, else one more than the item
 * before it, else 1, as the DOCX numbers them. Items nested under an item count on their own. */
export function listIndexes(doc: Node): ListIndex[] {
  const found: ListIndex[] = [];
  const visit = (group: Node, groupPosition: number) => {
    let previous: number | null = null;
    group.forEach((container, offset) => {
      const position = groupPosition + 1 + offset, content = container.firstChild;
      if (container.type.name === "blockContainer" && content?.type.name === "numberedListItem") {
        const start: unknown = content.attrs["start"];
        const index = typeof start === "number" && Number.isInteger(start) && start > 0 ? start : previous === null ? 1 : previous + 1;
        found.push({ from: position + 1, to: position + 1 + content.nodeSize, index });
        previous = index;
      } else previous = null;
      container.forEach((child, childOffset) => { if (child.type.name === "blockGroup") visit(child, position + 1 + childOffset); });
    });
  };
  doc.forEach((group, offset) => { if (group.type.name === "blockGroup") visit(group, offset); });
  return found;
}

function decorations(doc: Node): DecorationSet {
  return DecorationSet.create(doc, listIndexes(doc).map(item => Decoration.node(item.from, item.to, { "data-index": String(item.index) })));
}

export function listIndexPlugin(): Plugin {
  return new Plugin({ key: new PluginKey("foldcv-list-index"),
    state: { init: (_config, state) => decorations(state.doc), apply: (tr, set) => tr.docChanged ? decorations(tr.doc) : set },
    props: { decorations: function (state) { return this.getState(state) ?? DecorationSet.empty; } } });
}
