import type { WorkingFacts } from "../contracts/generated/working_facts";

type Technology = Extract<WorkingFacts["records"][number], { kind: "technology" }>;
type OrderBlock = { id: string; type: string; props?: unknown; content?: unknown; children: readonly OrderBlock[] };
/** The fields technology order reads; V1 and V7 documents both provide them. */
export type OrderDocument = { regions: readonly { role: string; blocks: readonly OrderBlock[] }[] };

function field(value: unknown, key: string): unknown { return typeof value === "object" && value !== null ? Reflect.get(value, key) : undefined; }

export function documentTechnologies(facts: Pick<WorkingFacts, "records">, document: OrderDocument, jobId: string | null): Technology[] {
  const records = facts.records.filter((record): record is Technology => record.kind === "technology" && record.jobId === jobId);
  const order = new Map<string, number>();
  function visit(blocks: readonly OrderBlock[], focus = false, grouped = false, groupsOnly = false) {
    for (const block of blocks) {
      const insideFocus = focus || block.type === "section" && field(block.props, "presentation") === "focus";
      const insideGroup = grouped || block.id.startsWith("technology_group_");
      if (!insideFocus && (!groupsOnly || insideGroup) && Array.isArray(block.content)) for (const span of block.content) {
        const recordId = field(span, "recordId");
        if (field(span, "type") === "fact_field" && field(span, "fieldKey") === "display" && typeof recordId === "string" && !order.has(recordId))
          order.set(recordId, order.size);
      }
      visit(block.children, insideFocus, insideGroup, groupsOnly);
    }
  }
  const regions = [...document.regions].sort((left, right) => Number(left.role !== "main") - Number(right.role !== "main"));
  regions.forEach(region => visit(region.blocks, false, false, true));
  regions.forEach(region => visit(region.blocks));
  return records.sort((left, right) => (order.get(left.id) ?? Infinity) - (order.get(right.id) ?? Infinity));
}

export function adjacentTechnology(ids: readonly string[], id: string, direction: -1 | 1): string | null | undefined {
  const index = ids.indexOf(id);
  if (index < 0 || index + direction < 0 || index + direction >= ids.length) return undefined;
  return direction < 0 ? ids[index - 1] : ids[index + 2] ?? null;
}
