import { Plugin } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
export type PresentationBlocks = NonNullable<RichProjectResponse["presentation"]>["blocks"];

export function presentationPlugin(current: () => PresentationBlocks, logos: ReadonlyMap<string, string>): Plugin {
  return new Plugin({ props: { decorations: state => {
    const decorations: Decoration[] = [], blocks = current();
    state.doc.descendants((node, position) => {
      const id: unknown = node.attrs["id"];
      if (node.type.name !== "blockContainer" || typeof id !== "string") return;
      const view = blocks[id]; if (!view) return;
      const logo = view.logo ? logos.get(view.logo) : undefined;
      const end = position + 1 + (node.firstChild?.nodeSize ?? 0);
      let bound = false;
      node.firstChild?.descendants(child => { if (child.type.name === "factField") bound = true; });
      const attributes: Record<string, string> = { "data-cv-role": view.role, "data-cv-logo": logo ? "true" : "false",
        "data-cv-bound": bound ? "true" : "false",
        "data-cv-empty": node.firstChild?.textContent.trim() ? "false" : "true",
        "data-cv-active": state.selection.from > position && state.selection.from < end ? "true" : "false" };
      if (logo) attributes["style"] = `--cv-focus-logo: url("${logo}")`;
      decorations.push(Decoration.node(position, position + node.nodeSize, attributes));
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
