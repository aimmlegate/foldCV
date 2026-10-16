import { Plugin } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { WorkingFacts } from "../../contracts/generated/working_facts";
import { prototypeClass } from "./classes";

export function prototypePresentation(facts: () => WorkingFacts, selected: () => string | null = () => null): Plugin {
  return new Plugin({ props: { decorations: state => {
    const decorations: Decoration[] = [];
    const firstBlocks = new Set<string>();
    state.doc.descendants((node, position) => {
      if (node.type.name === "blockGroup" && position === 0) {
        decorations.push(Decoration.node(position, position + node.nodeSize, { class: "paper-columns uir-regions" }));
      }
      if (node.type.name !== "blockContainer" || !node.firstChild) return;
      const content = node.firstChild, resolved = state.doc.resolve(position);
      let region = "main", focus = false;
      for (let depth = 1; depth <= resolved.depth; depth++) {
        const ancestor = resolved.node(depth);
        if (ancestor.type.name !== "blockContainer") continue;
        const parent = ancestor.firstChild;
        if (parent?.type.name === "region" && typeof parent.attrs["role"] === "string") region = parent.attrs["role"];
        if (parent?.type.name === "section" && parent.attrs["presentation"] === "focus") focus = true;
      }
      if (content.type.name === "region") {
        const role: unknown = content.attrs["role"];
        const className = role === "header" ? "paper-heading uir-header" : role === "sidebar" ? "paper-sidebar uir-sidebar" : "paper-main uir-main";
        decorations.push(Decoration.node(position, position + node.nodeSize, { class: className }));
        return;
      }
      const bindings: { recordId: string; fieldKey: string }[] = [];
      content.descendants(child => {
        if (child.type.name === "factField" && typeof child.attrs["recordId"] === "string" && typeof child.attrs["fieldKey"] === "string")
          bindings.push({ recordId: child.attrs["recordId"], fieldKey: child.attrs["fieldKey"] });
      });
      const level: unknown = content.attrs["level"], presentation: unknown = content.attrs["presentation"];
      const className = prototypeClass({ type: content.type.name, region, focus, bindings,
        empty: !content.textContent.trim(), level: typeof level === "number" ? level : null,
        presentation: typeof presentation === "string" ? presentation : null }, facts());
      const first = !firstBlocks.has(region);
      firstBlocks.add(region);
      decorations.push(Decoration.node(position, position + node.nodeSize, { class: "uir-block-container",
        "data-uir-section": content.type.name === "section" ? "true" : "false", "data-uir-class": className }));
      decorations.push(Decoration.node(position + 1, position + 1 + content.nodeSize, { class: `${className}${node.attrs["id"] === selected() ? " is-selected" : ""}`,
        "data-uir-first": first ? "true" : "false",
        "data-uir-monogram": className.includes("cv-focus") ? content.textContent.slice(0, 2).toUpperCase() : "" }));
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
