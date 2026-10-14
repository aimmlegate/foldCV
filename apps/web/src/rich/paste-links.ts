import type { Slice } from "@tiptap/pm/model";
import type { EditorState } from "@tiptap/pm/state";

/** Plain paste rules must not replace an authored target with a detected email. */
export function authoredPasteTransaction(state: EditorState, slice: Slice) {
  let linked = false;
  slice.content.descendants(node => { if (node.marks.some(mark => mark.type.name === "link")) linked = true; });
  return linked ? state.tr.replaceSelection(slice).scrollIntoView() : null;
}
