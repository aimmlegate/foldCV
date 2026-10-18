import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { CellChange, CellValue } from "./history";
import type { StoredBlock } from "./document-cells";
import { factsFromCells } from "./fact-cells";
import { documentSteps, factSteps, type RichBlock } from "./save-queue";

export function historyMutation(project: NonNullable<RichProjectResponse["workspace"]["project"]>, sessionId: string,
  direction: "undo" | "redo", changes: readonly CellChange[], current: ReadonlyMap<string, CellValue>,
  cache: ReadonlyMap<string, StoredBlock>): RichMutation | null {
  const next = new Map(current);
  changes.forEach(change => next.set(change.key, change.after));
  function rebuild(id: string): RichBlock {
    const key = next.get(`block:${id}`), stored = key ? cache.get(key) : undefined;
    if (!stored) throw new Error("AGENT_STALE_READ");
    return { ...stored.block, children: stored.children.map(rebuild) };
  }
  function regionValue(region: RichDocumentV1["regions"][number]) {
    const value = next.get(`region:${region.id}`), ids: unknown = value ? JSON.parse(value) : [];
    if (!Array.isArray(ids) || !ids.every((id: unknown) => typeof id === "string")) throw new Error("AGENT_STALE_READ");
    return { ...region, blocks: ids.map((id: string) => rebuild(id)) };
  }
  const document: RichDocumentV1 = { ...project.document, regions: [regionValue(project.document.regions[0]),
    regionValue(project.document.regions[1]), regionValue(project.document.regions[2])] };
  const steps = [...documentSteps(project.document, document), ...factSteps(project.facts, factsFromCells(next, project.facts))];
  const [first, ...rest] = steps;
  if (!first) return null;
  const id = `history-offer-${crypto.randomUUID()}`;
  return { schemaVersion: 1, projectId: project.projectId, clientMutationId: id, actionId: id, kind: direction,
    capture: { sessionId, actionId: id, actionToken: 0, dependencies: [] }, steps: [first, ...rest] };
}
