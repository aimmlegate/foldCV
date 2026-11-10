/** Closing marks of list items (D152): a semicolon after each item and a full stop after the last item of a list, as
 * the DOCX writes them (packages/resume_core/rendering/list_ends.py). They are decorations, outside the document, as
 * the numbers of numbered items are: the text keeps no mark nobody typed, and an item closing itself keeps its own. */

import type { Node } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export type ListEnd = { from: number; to: number; end: "item" | "last" };

const LISTS = new Set(["bulletListItem", "numberedListItem"]);
const CLOSING = /[.;!?:…]\s*$/u;

/** Each list item's content node with the mark it gets. Neighbouring items of one kind are one list; an empty item
 * gets no mark and one that closes itself keeps its own, which still ends its list. */
export function listEnds(doc: Node): ListEnd[] {
  const found: ListEnd[] = [];
  const visit = (group: Node, groupPosition: number) => {
    let run: { from: number; to: number; text: string }[] = [], kind: string | null = null;
    const close = () => {
      const items = run.filter(item => item.text.trim());
      items.forEach((item, index) => {
        if (!CLOSING.test(item.text)) found.push({ from: item.from, to: item.to, end: index === items.length - 1 ? "last" : "item" });
      });
      run = [];
      kind = null;
    };
    group.forEach((container, offset) => {
      const position = groupPosition + 1 + offset, content = container.firstChild;
      const name = container.type.name === "blockContainer" && content && LISTS.has(content.type.name) ? content.type.name : null;
      if (name !== kind) close();
      if (name && content) {
        kind = name;
        run.push({ from: position + 1, to: position + 1 + content.nodeSize, text: content.textContent });
      }
      container.forEach((child, childOffset) => { if (child.type.name === "blockGroup") visit(child, position + 1 + childOffset); });
    });
    close();
  };
  doc.forEach((group, offset) => { if (group.type.name === "blockGroup") visit(group, offset); });
  return found;
}

const MARKS = { item: ";", last: "." };

function widget(end: ListEnd["end"]): HTMLElement {
  const span = document.createElement("span");
  span.className = "fcv-list-end";
  span.textContent = MARKS[end];
  return span;
}

/** A widget at the end of each item's text, before the trailing break the engine keeps after an inline field node;
 * the attribute names the mark for styles and checks. */
function decorations(doc: Node): DecorationSet {
  return DecorationSet.create(doc, listEnds(doc).flatMap(item => [
    Decoration.node(item.from, item.to, { "data-fcv-list-end": item.end }),
    Decoration.widget(item.to - 1, () => widget(item.end), { side: 1, end: item.end, key: `fcv-list-end-${item.end}` }),
  ]));
}

export function listEndsPlugin(): Plugin {
  return new Plugin({ key: new PluginKey("foldcv-list-ends"),
    state: { init: (_config, state) => decorations(state.doc), apply: (tr, set) => tr.docChanged ? decorations(tr.doc) : set },
    props: { decorations: function (state) { return this.getState(state) ?? DecorationSet.empty; } } });
}
