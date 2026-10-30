/** Import remarks and doubtful values, marked in the resume text. A mark is an editor decoration, outside the document,
 * so saving, copying and export never see it. */

import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { currentMarker, needsCheck, userCorrected } from "./fact-fields";
import { allSpans, field, isFrame, ownSpans, subtree, type OutlineBlock, type OutlineDocument } from "./outline";

type IssueInput = { state: string; message: string; targetIds: readonly string[]; blockIds: readonly string[] };
type FactsInput = { records: readonly unknown[] };

/** The marked places with the remarks on each: shown fields by cell ID, and blocks whose own text is marked. */
export type RemarkMarks = { cells: ReadonlyMap<string, readonly string[]>; blocks: ReadonlyMap<string, readonly string[]> };

export const DOUBTFUL_VALUE = "Значение не распознано однозначно. Проверьте его.";
export const remarkMarksMeta = "foldcv-remark-marks";

const cellId = (recordId: string, key: string): string => JSON.stringify(["fact", recordId, key]);

function shownCells(block: OutlineBlock): string[] {
  return allSpans(ownSpans(block)).flatMap(span => {
    const type = field(span, "type");
    const value = type === "fact_field" ? field(span, "cellId")
      : type === "bound_link" ? field(field(span, "labelBinding") ?? field(span, "urlBinding"), "cellId") : null;
    return typeof value === "string" && value ? [value] : [];
  });
}

/** The fields Python could not read as one value (the panel's «Проверьте значение»), as fact cell IDs. A current period's
 * end label is no doubt; a dated end beside «present» is. */
function doubtfulCells(facts: FactsInput | undefined): string[] {
  const result: string[] = [];
  for (const record of facts?.records ?? []) {
    const id = field(record, "id");
    if (typeof id !== "string" || typeof record !== "object" || record === null) continue;
    for (const [key, value] of Object.entries(record)) {
      if (key === "periods") {
        for (const period of Array.isArray(value) ? value : []) {
          const periodId = field(period, "id"), present = field(field(period, "present"), "value") === true;
          if (typeof periodId !== "string") continue;
          const end = field(field(period, "end"), "rawText");
          const endDoubtful = present && typeof end === "string" && end.trim() ? !currentMarker(end) && !userCorrected(field(period, "end"))
            : needsCheck(field(period, "end"));
          if (needsCheck(field(period, "start"))) result.push(cellId(id, `period:${periodId}:start`));
          if (endDoubtful) result.push(cellId(id, `period:${periodId}:end`));
          if (needsCheck(field(period, "present"))) result.push(cellId(id, `period:${periodId}:present`));
        }
        continue;
      }
      // A technology's catalog key is internal; an unknown one does not make its source label doubtful.
      if (key === "canonicalId" || typeof field(value, "status") !== "string") continue;
      if (needsCheck(value)) result.push(cellId(id, key));
    }
  }
  return result;
}

/** What the text marks. A remark marks the fields it names where the document shows them; otherwise the blocks Python
 * placed it on, where a named heading stands for its whole section. A remark without targets names no place of its own
 * (Python then lists every imported block) and is not marked. */
export function remarkMarks(document: OutlineDocument, issues: readonly IssueInput[], facts?: FactsInput): RemarkMarks {
  const blocks = new Map<string, OutlineBlock>(), sections = new Map<string, string>(), shown = new Set<string>();
  for (const region of document.regions) {
    let heading: string | null = null;
    for (const top of region.blocks) {
      if (top.type === "heading") heading = top.id;
      for (const block of subtree(top)) {
        blocks.set(block.id, block);
        if (heading !== null) sections.set(block.id, heading);
        shownCells(block).forEach(id => shown.add(id));
      }
    }
  }
  const cells = new Map<string, string[]>(), marked = new Map<string, string[]>();
  const add = (into: Map<string, string[]>, id: string, message: string) => {
    const messages = into.get(id) ?? [];
    if (!messages.includes(message)) into.set(id, [...messages, message]);
  };
  // A frame's own line is hidden, so its lines carry its mark.
  const lines = (block: OutlineBlock): string[] => isFrame(block) ? block.children.flatMap(lines) : [block.id];
  for (const issue of issues) {
    const message = issue.message.trim();
    if (issue.state !== "active" || !message || !issue.targetIds.length) continue;
    const fields = issue.targetIds.filter(id => shown.has(id));
    if (fields.length) { fields.forEach(id => add(cells, id, message)); continue; }
    const named = issue.blockIds.flatMap(id => { const block = blocks.get(id); return block ? [block] : []; });
    const headings = new Set(named.filter(block => block.type === "heading").map(block => block.id));
    for (const block of named) {
      const heading = sections.get(block.id);
      if (heading !== undefined && heading !== block.id && headings.has(heading)) continue;
      lines(block).forEach(id => add(marked, id, message));
    }
  }
  for (const id of doubtfulCells(facts)) if (shown.has(id)) add(cells, id, DOUBTFUL_VALUE);
  return { cells, blocks: marked };
}

const markAttributes = (messages: readonly string[]) => ({ class: "fcv-remark", title: messages.join("\n") });

/** Decorations for the marks `current` returns; null shows none. */
export function remarkMarksPlugin(current: () => RemarkMarks | null): Plugin {
  return new Plugin({ key: new PluginKey(remarkMarksMeta), props: { decorations: state => {
    const marks = current();
    if (!marks || (!marks.cells.size && !marks.blocks.size)) return DecorationSet.empty;
    const decorations: Decoration[] = [];
    state.doc.descendants((node, position) => {
      const name = node.type.name;
      if (name === "templateField" || name === "boundLink") {
        const cell: unknown = node.attrs["cellId"], messages = typeof cell === "string" ? marks.cells.get(cell) : undefined;
        if (messages && node.content.size) decorations.push(Decoration.node(position, position + node.nodeSize, markAttributes(messages)));
        return false;
      }
      if (name !== "blockContainer") return true;
      const id: unknown = node.attrs["id"], messages = typeof id === "string" ? marks.blocks.get(id) : undefined;
      const size = node.firstChild?.content.size ?? 0;
      // The block's own content starts inside its content node, one step past the container's start.
      if (messages && size) decorations.push(Decoration.inline(position + 2, position + 2 + size, markAttributes(messages)));
      return true;
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
