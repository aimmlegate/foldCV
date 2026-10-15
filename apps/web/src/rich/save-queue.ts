import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import { semantic } from "./fact-cells";
import { normalizedBlock } from "./normalize";

export type RichBlock = RichDocumentV1["regions"][number]["blocks"][number];
type Placement = { block: RichBlock; parentId: string; afterId: string | null };
function placements(document: RichDocumentV1): Map<string, Placement> {
  const result = new Map<string, Placement>();
  function visit(blocks: RichBlock[], parentId: string) {
    let afterId: string | null = null;
    for (const block of blocks) {
      result.set(block.id, { block, parentId, afterId }); visit(block.children, block.id); afterId = block.id;
    }
  }
  document.regions.forEach(region => visit(region.blocks, region.id));
  return result;
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item: unknown) => canonical(item)).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}
function logical(block: RichBlock): string {
  block = normalizedBlock(block);
  const content = block.type === "table" ? { ...block.content, rows: block.content.rows.map(row => ({ ...row,
    cells: row.cells.map(({ revision: _revision, ...cell }) => cell) })) } : block.content;
  return canonical(semantic({ type: block.type, props: block.props, content, provenance: block.provenance }));
}

export function factSteps(before: WorkingFacts, after: WorkingFacts): RichMutation["steps"][number][] {
  const old = new Map(before.records.map(record => [record.id, record]));
  const current = new Map(after.records.map(record => [record.id, record]));
  return [...before.records.filter(record => !current.has(record.id)).map(record => ({ kind: "remove_record" as const,
    recordId: record.id, beforeRevision: record.revision })), ...after.records.flatMap(record => {
    const previous = old.get(record.id);
    return previous && canonical(semantic(previous)) === canonical(semantic(record)) ? [] : [{ kind: "put_record" as const,
      beforeRevision: previous?.revision ?? before.tombstones.find(item => item.recordId === record.id)?.revision ?? null, record }];
  })];
}

export function documentSteps(before: RichDocumentV1, after: RichDocumentV1): RichMutation["steps"][number][] {
  const old = placements(before), current = placements(after);
  const steps: RichMutation["steps"][number][] = [];
  const parents = new Map([...old].map(([id, item]) => [id, item.parentId]));
  const children = new Map<string, string[]>();
  for (const [id, item] of old) children.set(item.parentId, [...(children.get(item.parentId) ?? []), id]);
  function place(id: string, parent: string, previous: string | null) {
    const oldParent = parents.get(id), siblings = oldParent ? children.get(oldParent) : undefined;
    if (siblings) { const index = siblings.indexOf(id); if (index >= 0) siblings.splice(index, 1); }
    const target = children.get(parent) ?? [];
    target.splice(previous === null ? 0 : target.indexOf(previous) + 1, 0, id);
    children.set(parent, target); parents.set(id, parent);
  }
  // New siblings keep their relative order while retained children escape deleted ancestors.
  const lastNew = new Map<string, string>();
  for (const [id, item] of current) if (!old.has(id)) {
    const afterId = lastNew.get(item.parentId) ?? null;
    steps.push({ kind: "put_block", parentId: item.parentId, afterId, beforeRevision: null, block: { ...item.block, children: [] } });
    place(id, item.parentId, afterId); lastNew.set(item.parentId, id);
  }
  for (const [id, item] of current) {
    const previous = old.get(id);
    if (previous && previous.parentId !== item.parentId) {
      steps.push({ kind: "move_block", blockId: id, beforeRevision: previous.block.revision, parentId: item.parentId, afterId: null });
      place(id, item.parentId, null);
    }
  }
  for (const [id, item] of old) if (!current.has(id) && !(!current.has(item.parentId) && old.has(item.parentId))) {
    steps.push({ kind: "remove_block", blockId: id, beforeRevision: item.block.revision });
    const siblings = children.get(item.parentId), index = siblings?.indexOf(id);
    if (siblings && index !== undefined && index >= 0) siblings.splice(index, 1);
  }
  for (const [id, item] of current) {
    const previous = old.get(id);
    if (!previous) continue;
    if (logical(previous.block) !== logical(item.block)) {
      steps.push({ kind: "put_block", parentId: item.parentId, afterId: null,
        beforeRevision: previous.block.revision, block: { ...item.block, children: [] }, keepChildren: true });
    }
    const siblings = children.get(item.parentId) ?? [], index = siblings.indexOf(id);
    const actualPrevious = index > 0 ? siblings[index - 1] : null;
    if (parents.get(id) !== item.parentId || actualPrevious !== item.afterId) {
      steps.push({ kind: "move_block", blockId: id, beforeRevision: previous.block.revision,
        parentId: item.parentId, afterId: item.afterId });
      place(id, item.parentId, item.afterId);
    }
  }
  return steps;
}

/** Replies update the save baseline; the mounted typing buffer always stays current. */
export class RichSaveQueue {
  private target: RichDocumentV1;
  private facts: WorkingFacts;
  private actionId: string;
  private kind: RichMutation["kind"] = "typing";
  private running: Promise<void> | null = null;
  private closed = false;
  private pendingRequest: RichMutation | null = null;
  private prepared: string | null = null;
  private fenced = false;
  constructor(private response: RichProjectResponse, readonly sessionId: string,
    private readonly send: (request: RichMutation) => Promise<RichProjectResponse>,
    private readonly acknowledged: (response: RichProjectResponse) => void) {
    if (!response.workspace.project) throw new Error("Document not created");
    this.target = response.workspace.project.document;
    this.facts = response.workspace.project.facts;
    this.actionId = `${sessionId}:initial`;
  }
  update(document: RichDocumentV1, actionId: string, kind: RichMutation["kind"] = "typing", facts?: WorkingFacts): void {
    if (this.prepared !== null || this.fenced) throw new Error("AGENT_OUTCOME_UNKNOWN");
    this.target = document; this.actionId = actionId; this.kind = kind; if (facts) this.facts = facts;
  }
  get baseline(): RichProjectResponse { return this.response; }
  refreshMetadata(response: RichProjectResponse): void {
    const previous = this.response.workspace.project, current = response.workspace.project;
    if (this.closed || this.fenced || this.prepared !== null || !previous || !current || response.durability !== "durable"
      || response.workspace.projectId !== this.response.workspace.projectId || documentSteps(previous.document, current.document).length
      || factSteps(previous.facts, current.facts).length) throw new Error("AGENT_STALE_READ");
    this.response = response;
    this.acknowledged(response);
  }
  close(): void { this.closed = true; }
  async flush(): Promise<void> {
    if (this.prepared !== null || this.fenced) throw new Error("AGENT_OUTCOME_UNKNOWN");
    if (this.running) return this.running;
    const operation = this.drain(); this.running = operation;
    try { await operation; } finally { this.running = null; }
  }
  beginPrepared(key: string): void {
    const project = this.response.workspace.project;
    if (this.closed || this.fenced || this.prepared !== null || this.running || this.pendingRequest || !project
      || documentSteps(project.document, this.target).length || factSteps(project.facts, this.facts).length) throw new Error("AGENT_STALE_READ");
    this.prepared = key;
  }
  adoptPrepared(key: string, response: RichProjectResponse): void {
    const project = response.workspace.project;
    if (this.closed || this.fenced || this.prepared !== key || response.durability !== "durable" || !project
      || response.workspace.projectId !== this.response.workspace.projectId) throw new Error("AGENT_OUTCOME_UNKNOWN");
    this.response = response;
    this.target = project.document;
    this.facts = project.facts;
    this.pendingRequest = null;
    this.acknowledged(response);
  }
  endPrepared(key: string): void { if (this.prepared === key && !this.fenced) this.prepared = null; }
  fencePrepared(): void { this.fenced = true; }
  private async drain(): Promise<void> {
    while (!this.closed) {
      const before = this.response.workspace.project?.document;
      if (!before) throw new Error("Document not created");
      const beforeFacts = this.response.workspace.project?.facts;
      if (!beforeFacts) throw new Error("Facts not created");
      const steps = [...documentSteps(before, this.target), ...factSteps(beforeFacts, this.facts)];
      const [first, ...rest] = steps;
      if (!first && !this.pendingRequest) return;
      const request: RichMutation | null = this.pendingRequest ?? (first ? { schemaVersion: 1, projectId: this.response.workspace.projectId,
        clientMutationId: crypto.randomUUID(), actionId: this.actionId, kind: this.kind,
        capture: { sessionId: this.sessionId, actionId: this.actionId, actionToken: 0, dependencies: [] }, steps: [first, ...rest] } : null);
      if (!request) return;
      if (new TextEncoder().encode(JSON.stringify(request)).length > 1024 * 1024) throw new Error("RICH_MUTATION_LIMIT");
      this.pendingRequest = request;
      let response: RichProjectResponse;
      try { response = await this.send(request); }
      catch (error) {
        if (typeof error === "object" && error !== null && "status" in error && typeof error.status === "number"
          && error.status >= 400 && error.status < 500) this.pendingRequest = null;
        throw error;
      }
      if (this.closed) return;
      this.response = response;
      this.acknowledged(response);
      if (response.durability === "failed") throw new Error(response.saveError ?? "PROJECT_SAVE_FAILED");
      this.pendingRequest = null;
    }
  }
}
