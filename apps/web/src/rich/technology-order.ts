import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichBlock } from "./save-queue";

type Technology = Extract<WorkingFacts["records"][number], { kind: "technology" }>;

export function documentTechnologies(facts: WorkingFacts, document: RichDocumentV1, jobId: string | null): Technology[] {
  const records = facts.records.filter((record): record is Technology => record.kind === "technology" && record.jobId === jobId);
  const order = new Map<string, number>();
  function visit(blocks: readonly RichBlock[], focus = false, grouped = false, groupsOnly = false) {
    for (const block of blocks) {
      const insideFocus = focus || block.type === "section" && block.props.presentation === "focus";
      const insideGroup = grouped || block.id.startsWith("technology_group_");
      if (!insideFocus && (!groupsOnly || insideGroup) && Array.isArray(block.content)) for (const span of block.content)
        if (span.type === "fact_field" && span.fieldKey === "display" && !order.has(span.recordId)) order.set(span.recordId, order.size);
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
