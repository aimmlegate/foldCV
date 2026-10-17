import { Fragment, Slice, type Node } from "@tiptap/pm/model";

const restricted = new Set(["table", "codeBlock", "quote", "divider", "checkListItem", "toggleListItem"]);

export function allowsBasicEdit(before: Node, after: Node): boolean {
  const inventory = (document: Node) => {
    const result = new Map<string, number>();
    document.descendants(node => {
      if (node.type.name !== "blockContainer" || !node.firstChild || !restricted.has(node.firstChild.type.name)) return;
      const id: unknown = node.attrs["id"];
      const key = `${typeof id === "string" ? id : ""}:${node.firstChild.type.name}`;
      result.set(key, (result.get(key) ?? 0) + 1);
    });
    return result;
  };
  const previous = inventory(before);
  return [...inventory(after)].every(([id, count]) => count <= (previous.get(id) ?? 0));
}

export function basicPastedSlice(slice: Slice): Slice {
  const visit = (node: Node): Node => {
    if (restricted.has(node.type.name)) {
      const paragraph = node.type.schema.nodes["paragraph"];
      if (!paragraph) return node;
      const text = node.textBetween(0, node.content.size, "\n");
      return paragraph.create(null, node.inlineContent ? node.content : text ? node.type.schema.text(text) : undefined);
    }
    if (node.isLeaf) return node;
    return node.copy(Fragment.fromArray(node.content.content.map(visit)));
  };
  const content = Fragment.fromArray(slice.content.content.map(visit));
  const maxOpen = Slice.maxOpen(content, false);
  return new Slice(content, Math.min(slice.openStart, maxOpen.openStart), Math.min(slice.openEnd, maxOpen.openEnd));
}
