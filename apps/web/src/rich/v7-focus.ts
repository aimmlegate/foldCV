import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { FocusEntry } from "../workbench/facts/FocusYears";
import { technologyKey } from "./panel-intents";

type Project = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>;
type Block = Project["document"]["regions"][number]["blocks"][number];
type OptionRecord = { id: string; jobId?: string | null; subprojectId?: string | null; display: { rawText: string } };

const collator = new Intl.Collator("ru", { sensitivity: "base" });

function parts(block: Block) {
  return Array.isArray(block.content)
    ? block.content.flatMap(part => part.type === "bound_link" || part.type === "link" ? part.content : [part]) : [];
}

function text(block: Block): string {
  return parts(block).map(part => part.text).join("");
}

function showsName(block: Block, recordId: string): boolean {
  return parts(block).some(part => part.type === "fact_field" && part.fieldKey === "display" && part.recordId === recordId);
}

/** The years field as Python reads it: whole years from 0 to 100, "" to clear; null for anything else (3.5, a half-typed
 * 3- the browser reports as bad input). */
export function yearsValue(value: string, badInput: boolean): string | null {
  if (badInput) return null;
  if (value === "") return "";
  const years = Number(value);
  return Number.isInteger(years) && years >= 0 && years <= 100 ? String(years) : null;
}

/** One option per name not in Focus yet, from the record a row binds best: a general record no line shows, as a removed
 * row leaves it with its years, then another general record, then a job's. */
export function focusOptions(records: Iterable<OptionRecord>, lined: ReadonlySet<string>, named: ReadonlySet<string>): FocusEntry[] {
  const rank = (record: OptionRecord) => (record.jobId || record.subprojectId ? 2 : 0) + (lined.has(record.id) ? 1 : 0);
  const options = new Map<string, { entry: FocusEntry; rank: number }>();
  for (const record of records) {
    const key = technologyKey(record.display.rawText), value = rank(record);
    if (!key || named.has(key) || (options.get(key)?.rank ?? Infinity) <= value) continue;
    options.set(key, { entry: { recordId: record.id, display: record.display.rawText, years: null, detail: "" }, rank: value });
  }
  return [...options.values()].map(value => value.entry).sort((left, right) => collator.compare(left.display, right.display));
}

/** Whole years of an experience text ("3 года", "1 year"); null for months, other wording or no text. */
export function wholeYears(experience: string): number | null {
  const match = /^\s*(\d+)\s*(?:год|года|лет|years?)\s*$/iu.exec(experience);
  return match ? Number(match[1]) : null;
}

/** The Focus rows Python's plan marks, in document order, the technologies that can join them, and the records only
 * the rows show; empty when Python cannot change this template's Focus. */
export function focusFacts(project: Project, presentation: TemplateProjectResponseV1["presentation"]):
  { entries: FocusEntry[]; options: FocusEntry[]; only: ReadonlySet<string> } {
  const plan = presentation?.editor, panel = plan?.focusPanel;
  if (!plan || !panel) return { entries: [], options: [], only: new Set() };
  const technologies = new Map(project.facts.records.flatMap(record => record.kind === "technology" ? [[record.id, record] as const] : []));
  const entries: FocusEntry[] = [], lined = new Set<string>();
  const visit = (blocks: readonly Block[]) => {
    for (const block of blocks) {
      const recordId = block.type === "section" ? block.props.recordId : null;
      const record = recordId ? technologies.get(recordId) : undefined;
      if (recordId && record && plan.blocks[block.id]?.focus) {
        // The field edits the stated experience; a line the jobs' span gives is only its placeholder.
        const stated = (record.experience?.rawText ?? "").trim(), years = wholeYears(stated);
        const name = block.children.findIndex(child => showsName(child, recordId));
        const shown = block.children.slice(name + 1).map(text).join(" ").trim();
        entries.push({ recordId, display: record.display.rawText, years, detail: years === null ? stated || shown : "" });
        continue;
      }
      for (const part of parts(block)) if (part.type === "fact_field" && part.fieldKey === "display") lined.add(part.recordId);
      visit(block.children);
    }
  };
  project.document.regions.forEach(region => visit(region.blocks));
  const named = new Set(entries.map(entry => technologyKey(entry.display)));
  return { entries, options: focusOptions(technologies.values(), lined, named), only: new Set(panel.records) };
}
