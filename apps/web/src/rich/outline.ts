/** Reads of the shown document by structure only, never by wording: a section starts at a heading of its region, and
 * an item is a `section` frame naming its record. */

export type OutlineBlock = { id: string; type: string; content?: unknown; props?: unknown; children: readonly OutlineBlock[] };
export type OutlineDocument = { regions: readonly { id: string; role: string; blocks: readonly OutlineBlock[] }[] };

export function field(value: unknown, key: string): unknown { return typeof value === "object" && value !== null ? Reflect.get(value, key) : undefined; }

const list = (value: unknown): readonly unknown[] => Array.isArray(value) ? value : [];

/** The spans a block shows itself, without its children: its text, its table cells or its image caption. */
export function ownSpans(block: OutlineBlock): readonly unknown[] {
  if (block.type === "image") return list(field(block.props, "caption"));
  if (block.type === "table") return list(field(block.content, "rows")).flatMap(row => list(field(row, "cells")).flatMap(cell => list(field(cell, "content"))));
  return list(block.content);
}

/** Every span of a list, the spans inside links included. */
export function allSpans(spans: readonly unknown[]): unknown[] {
  return spans.flatMap(span => [span, ...allSpans(list(field(span, "content")))]);
}

function ownText(block: OutlineBlock): string {
  return allSpans(ownSpans(block)).map(span => field(span, "text")).filter((text): text is string => typeof text === "string").join("");
}

/** A block and its descendants in document order. */
export function subtree(block: OutlineBlock): OutlineBlock[] {
  return [block, ...block.children.flatMap(subtree)];
}

/** An item frame shows no text of its own; its lines are its children. */
export function isFrame(block: OutlineBlock): boolean {
  return block.type === "section" && ownSpans(block).length === 0;
}

/** Where each fact group is in the resume, by record kind: the heading of the first section whose items are records of
 * that kind, else of the first section showing one of its fields outside another kind's item. A section before any
 * heading, as the header, is shown at its first text. */
export function groupAnchors(document: OutlineDocument, kinds: ReadonlyMap<string, string>): Map<string, string> {
  const items = new Map<string, string>(), fields = new Map<string, string>();
  for (const region of document.regions) {
    let heading: string | null = null;
    for (const block of region.blocks) {
      if (block.type === "heading") { heading = block.id; continue; }
      const target = heading ?? subtree(block).find(inner => ownText(inner).trim())?.id ?? block.id;
      const record = block.type === "section" ? field(block.props, "recordId") : undefined;
      const own = typeof record === "string" ? kinds.get(record) : undefined;
      if (own !== undefined) {
        if (!items.has(own)) items.set(own, target);
        continue;
      }
      for (const span of subtree(block).flatMap(inner => allSpans(ownSpans(inner)))) {
        const id = field(span, "recordId"), kind = field(span, "type") === "fact_field" && typeof id === "string" ? kinds.get(id) : undefined;
        if (kind !== undefined && !fields.has(kind)) fields.set(kind, target);
      }
    }
  }
  return new Map([...fields, ...items]);
}
