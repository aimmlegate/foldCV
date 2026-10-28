/** Remarks are shown in the Facts panel by resume section, never inside the document text. A section starts at each
 * heading of a region; every other top-level block of a region is one item of the section before it. */

type OutlineBlock = { id: string; type: string; content?: unknown; props?: unknown; children: readonly OutlineBlock[] };
/** The fields the section outline reads from a document. */
export type OutlineDocument = { regions: readonly { id: string; role: string; blocks: readonly OutlineBlock[] }[] };

export type Remark = { id: string; source: "import" | "check"; message: string; blockIds: readonly string[] };
export type RemarkItem = { blockId: string; focusId: string; label: string; remarks: Remark[] };
export type RemarkSection = { id: string; title: string; focusId: string | null; remarks: Remark[]; items: RemarkItem[] };
/** Sections in document order; an item is listed only when a remark concerns exactly that item. */
export type PlacedRemarks = { sections: RemarkSection[]; unplaced: Remark[]; count: number };

const REGION_TITLES: Readonly<Record<string, string>> = { header: "Шапка", sidebar: "Боковая колонка", main: "Основная колонка" };
export const EMPTY_BLOCK = "Пустой блок.";
export const LINK_WITHOUT_TARGET = "Ссылка без адреса.";

function field(value: unknown, key: string): unknown { return typeof value === "object" && value !== null ? Reflect.get(value, key) : undefined; }

function spansText(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content.map((span: unknown) => {
    const text = field(span, "text");
    return typeof text === "string" ? text : spansText(field(span, "content"));
  }).join("");
}

function ownText(block: OutlineBlock): string {
  if (block.type === "image") return spansText(field(block.props, "caption"));
  if (block.type === "table") {
    const rows = field(block.content, "rows");
    return Array.isArray(rows) ? rows.flatMap((row: unknown) => {
      const cells = field(row, "cells");
      return Array.isArray(cells) ? cells.map((cell: unknown) => spansText(field(cell, "content"))) : [];
    }).filter(text => text.trim()).join(" · ") : "";
  }
  return spansText(block.content);
}

/** The first block with text in a subtree, in document order. */
function firstText(block: OutlineBlock): OutlineBlock | null {
  if (ownText(block).trim()) return block;
  for (const child of block.children) {
    const found = firstText(child);
    if (found) return found;
  }
  return null;
}

function label(block: OutlineBlock): string {
  const found = firstText(block), text = (found ? ownText(found) : "").replace(/\s+/gu, " ").trim();
  return text.length > 80 ? `${text.slice(0, 79)}…` : text;
}

type Place = { section: number; item: string | null };
type Outline = { sections: (Omit<RemarkSection, "items"> & { items: Map<string, RemarkItem> })[]; places: Map<string, Place> };

function outline(document: OutlineDocument): Outline {
  const sections: Outline["sections"] = [], places = new Map<string, Place>();
  const mark = (block: OutlineBlock, place: Place) => { places.set(block.id, place); block.children.forEach(child => mark(child, place)); };
  for (const region of document.regions) {
    let current = -1;
    for (const block of region.blocks) {
      if (block.type === "heading") {
        sections.push({ id: block.id, title: ownText(block).trim() || "Без названия", focusId: block.id, remarks: [], items: new Map() });
        current = sections.length - 1;
        mark(block, { section: current, item: null });
        continue;
      }
      if (current < 0) {
        sections.push({ id: region.id, title: REGION_TITLES[region.role] ?? "Без названия", focusId: firstText(block)?.id ?? null,
          remarks: [], items: new Map() });
        current = sections.length - 1;
      }
      const section = sections[current];
      section?.items.set(block.id, { blockId: block.id, focusId: firstText(block)?.id ?? block.id, label: label(block), remarks: [] });
      mark(block, { section: current, item: block.id });
    }
  }
  return { sections, places };
}

/** A remark on blocks of exactly one item is shown at that item; one on several items, on a heading or on several
 * sections is shown at each section heading it touches; one whose blocks are all gone has no place. */
export function placeRemarks(document: OutlineDocument, remarks: readonly Remark[]): PlacedRemarks {
  const { sections, places } = outline(document), unplaced: Remark[] = [];
  const seen = new Set<string>();
  for (const remark of remarks) {
    if (seen.has(remark.id) || !remark.message.trim()) continue;
    seen.add(remark.id);
    const found = remark.blockIds.flatMap(id => { const place = places.get(id); return place ? [place] : []; });
    const [first] = found;
    if (!first) { unplaced.push(remark); continue; }
    if (first.item !== null && found.every(place => place.section === first.section && place.item === first.item)) {
      sections[first.section]?.items.get(first.item)?.remarks.push(remark);
      continue;
    }
    for (const index of new Set(found.map(place => place.section))) sections[index]?.remarks.push(remark);
  }
  return { count: seen.size, unplaced, sections: sections.map(section => ({ ...section,
    items: [...section.items.values()].filter(item => item.remarks.length > 0) })) };
}

type IssueInput = { id: string; state: string; message: string; blockIds: readonly string[] };
/** Active import issues with a message, as stored; their data model is not changed here. */
export function importRemarks(issues: readonly IssueInput[]): Remark[] {
  return issues.filter(issue => issue.state === "active" && issue.message.trim())
    .map(issue => ({ id: issue.id, source: "import", message: issue.message.trim(), blockIds: issue.blockIds }));
}

type CheckInput = { emptyBlocks: readonly string[]; linksWithoutTarget: readonly string[] };
/** The explicit check's own findings; its open import issues are the import remarks already shown. */
export function checkRemarks(result: CheckInput): Remark[] {
  return [...result.emptyBlocks.map(id => ({ id: `check-empty:${id}`, source: "check" as const, message: EMPTY_BLOCK, blockIds: [id] })),
    ...[...new Set(result.linksWithoutTarget)].map(id => ({ id: `check-link:${id}`, source: "check" as const,
      message: LINK_WITHOUT_TARGET, blockIds: [id] }))];
}

/** How many remarks the check found: its empty blocks, links without a target and open import issues. */
export function checkCount(result: CheckInput & { openImportIssues: readonly unknown[] }): number {
  return new Set(result.emptyBlocks).size + new Set(result.linksWithoutTarget).size + result.openImportIssues.length;
}
