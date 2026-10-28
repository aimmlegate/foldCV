import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { FocusEntry } from "../workbench/facts/FocusYears";
import { technologyKey } from "./panel-intents";

type Project = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>;
type Block = Project["document"]["regions"][number]["blocks"][number];

function text(block: Block): string {
  if (!Array.isArray(block.content)) return "";
  return block.content.map(part => part.type === "bound_link" || part.type === "link"
    ? part.content.map(child => child.text).join("") : part.text).join("");
}

/** Whole years of a shown experience line ("3 года", "1 year"); null for months, other wording or no line. */
export function shownYears(detail: string): number | null {
  const match = /^\s*(\d+)\s*(?:год|года|лет|years?)\s*$/iu.exec(detail);
  return match ? Number(match[1]) : null;
}

/** The Focus rows Python's plan marks, in document order, and the technologies that can join them: one per name, a
 * general record before a job's, none whose name is already shown. */
export function focusFacts(project: Project, presentation: TemplateProjectResponseV1["presentation"]):
  { entries: FocusEntry[]; options: FocusEntry[] } {
  const plan = presentation?.editor;
  if (!presentation || !plan) return { entries: [], options: [] };
  const technologies = new Map(project.facts.records.flatMap(record => record.kind === "technology" ? [[record.id, record] as const] : []));
  const entries: FocusEntry[] = [];
  const visit = (blocks: readonly Block[]) => {
    for (const block of blocks) {
      const recordId = block.type === "section" ? block.props.recordId : null;
      const record = recordId ? technologies.get(recordId) : undefined;
      if (recordId && record && plan.blocks[block.id]?.focus) {
        const detail = block.children.slice(1).map(text).join(" ").trim();
        entries.push({ recordId, display: record.display.rawText, years: shownYears(detail), detail });
        continue;
      }
      visit(block.children);
    }
  };
  project.document.regions.forEach(region => visit(region.blocks));
  // Without a Focus view in the template nothing can join it.
  if (!Object.values(presentation.recipe.views).some(view => view.nodes.some(node => node.type === "focus_entry"))) return { entries, options: [] };
  const shown = new Set(entries.map(entry => technologyKey(entry.display)));
  const options = new Map<string, FocusEntry & { general: boolean }>();
  for (const record of technologies.values()) {
    const key = technologyKey(record.display.rawText), general = !record.jobId && !record.subprojectId;
    if (!key || shown.has(key) || options.get(key)?.general) continue;
    if (!options.has(key) || general) options.set(key, { recordId: record.id, display: record.display.rawText, years: null, detail: "", general });
  }
  return { entries, options: [...options.values()].map(({ general: _general, ...entry }) => entry)
    .sort((left, right) => left.display.localeCompare(right.display, "ru", { sensitivity: "base" })) };
}
