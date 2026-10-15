import type { WorkingFacts } from "../../contracts/generated/working_facts";

export type ViewBlock = { type: string; region: string; level: number | null; presentation: string | null;
  empty: boolean; focus: boolean; bindings: { recordId: string; fieldKey: string }[] };

export function prototypeClass(block: ViewBlock, facts: WorkingFacts): string {
  const records = new Map(facts.records.map(record => [record.id, record]));
  const fields = block.bindings;
  if (block.type === "section") return block.empty ? "uir-owner-title" : "cv-block cv-section";
  if (block.type === "heading") {
    if (block.region === "header" && fields.some(field => records.get(field.recordId)?.kind === "candidate" && field.fieldKey === (block.level === 1 ? "name" : "title")))
      return block.level === 1 ? "cv-block candidate-name" : "cv-block candidate-title";
    if (block.region === "main" && block.level === 2 && fields.some(field => records.get(field.recordId)?.kind === "employment" && field.fieldKey === "employer")) return "cv-block cv-job";
  }
  if (block.type === "paragraph" && fields.length) {
    if (fields.every(field => records.get(field.recordId)?.kind === "employment" && field.fieldKey.startsWith("period:"))) return "cv-block cv-caption";
    if (fields.every(field => {
      const record = records.get(field.recordId);
      return record?.kind === "technology" && field.fieldKey === "display" && (block.focus ? record.jobId === null : record.jobId !== null);
    })) return block.focus && block.region === "sidebar" ? "cv-block cv-focus" : "cv-block cv-tech";
  }
  return "cv-block";
}
