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

/** What a doubtful value's mark says: it names the value, so the tip speaks of the place it is on (D130). */
export function doubtfulValue(rawText: unknown, what: "value" | "date" | "present" | "datedEnd" = "value"): string {
  const shown = typeof rawText === "string" && rawText.trim() ? ` «${rawText.trim()}»` : "";
  if (what === "date") return `Дата${shown} не распознана однозначно. Проверьте её в фактах.`;
  if (what === "present") return `Отметка о текущей работе${shown} не распознана однозначно. Проверьте период в фактах.`;
  if (what === "datedEnd") return `Указана дата окончания${shown}, хотя работа отмечена как текущая. Проверьте период в фактах.`;
  return `Значение${shown} не распознано однозначно. Проверьте его в фактах.`;
}
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
function doubtfulCells(facts: FactsInput | undefined): [string, string][] {
  const result: [string, string][] = [];
  const raw = (value: unknown) => field(value, "rawText");
  for (const record of facts?.records ?? []) {
    const id = field(record, "id");
    if (typeof id !== "string" || typeof record !== "object" || record === null) continue;
    for (const [key, value] of Object.entries(record)) {
      if (key === "periods") {
        for (const period of Array.isArray(value) ? value : []) {
          const periodId = field(period, "id"), present = field(field(period, "present"), "value") === true;
          if (typeof periodId !== "string") continue;
          const start = field(period, "start"), end = field(period, "end"), endText = raw(end);
          const datedEnd = present && typeof endText === "string" && endText.trim() !== "";
          const endDoubtful = datedEnd ? !currentMarker(endText) && !userCorrected(end) : needsCheck(end);
          if (needsCheck(start)) result.push([cellId(id, `period:${periodId}:start`), doubtfulValue(raw(start), "date")]);
          if (endDoubtful) result.push([cellId(id, `period:${periodId}:end`), doubtfulValue(endText, datedEnd ? "datedEnd" : "date")]);
          if (needsCheck(field(period, "present")))
            result.push([cellId(id, `period:${periodId}:present`), doubtfulValue(raw(field(period, "present")), "present")]);
        }
        continue;
      }
      // A technology's catalog key is internal; an unknown one does not make its source label doubtful.
      if (key === "canonicalId" || typeof field(value, "status") !== "string") continue;
      if (needsCheck(value)) result.push([cellId(id, key), doubtfulValue(raw(value))]);
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
  for (const [id, message] of doubtfulCells(facts)) if (shown.has(id)) add(cells, id, message);
  return { cells, blocks: marked };
}

/** The fact a cell ID names, for the tip's way into Facts; a block mark names none. */
export function remarkRecord(cellId: string): string | null {
  try {
    const parsed: unknown = JSON.parse(cellId);
    return Array.isArray(parsed) && parsed[0] === "fact" && typeof parsed[1] === "string" && parsed[1] ? parsed[1] : null;
  } catch { return null; }
}

/** The tip beside a mark reads its messages from the element; a native title stayed unseen (D127). */
export const remarkMessagesAttribute = "data-fcv-remark", remarkRecordAttribute = "data-fcv-record";
const markAttributes = (messages: readonly string[], recordId: string | null) => ({ class: "fcv-remark",
  [remarkMessagesAttribute]: JSON.stringify(messages), ...(recordId ? { [remarkRecordAttribute]: recordId } : {}) });

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
        if (messages && node.content.size) decorations.push(Decoration.node(position, position + node.nodeSize,
          markAttributes(messages, typeof cell === "string" ? remarkRecord(cell) : null)));
        return false;
      }
      if (name !== "blockContainer") return true;
      const id: unknown = node.attrs["id"], messages = typeof id === "string" ? marks.blocks.get(id) : undefined;
      const size = node.firstChild?.content.size ?? 0;
      // The block's own content starts inside its content node, one step past the container's start.
      if (messages && size) decorations.push(Decoration.inline(position + 2, position + 2 + size, markAttributes(messages, null)));
      return true;
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
