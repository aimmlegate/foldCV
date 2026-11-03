import type { Node } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { technologyLine } from "./v7-extraction";

const key = new PluginKey<DecorationSet>("foldcv-technology-lock");
const technologyName = '[data-fcv-technology-line] [data-field-key="display"][data-record-id]';

function locked(doc: Node): DecorationSet {
  const decorations: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true;
    if (technologyLine(node)) decorations.push(Decoration.node(pos, pos + node.nodeSize, { contenteditable: "false", "data-fcv-technology-line": "true" }));
    return false;
  });
  return DecorationSet.create(doc, decorations);
}

/** Technology lines change only in Facts (D131): the page shows them read-only, so the browser takes no input there, and a
 * click on a technology opens its record in Facts. */
export function technologyLockPlugin(open: (recordId: string) => void): Plugin<DecorationSet> {
  return new Plugin<DecorationSet>({ key,
    state: { init: (_config, state) => locked(state.doc), apply: (tr, value) => tr.docChanged ? locked(tr.doc) : value },
    props: {
      decorations: state => key.getState(state) ?? DecorationSet.empty,
      handleClick: (_view, _pos, event) => {
        const recordId = event.target instanceof Element ? event.target.closest(technologyName)?.getAttribute("data-record-id") : null;
        if (!recordId) return false;
        open(recordId);
        return true;
      },
    } });
}
