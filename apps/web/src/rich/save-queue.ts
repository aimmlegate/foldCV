import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import { semantic } from "./fact-cells";
import { normalizedBlock } from "./normalize";
import { compactMutation } from "./compact-mutation";
import type { WriterPrepareEditV2 } from "../contracts/generated/background_writer_prepare_edit_v2";
import type { WriterProofV1 } from "../contracts/generated/background_writer_proof_v1";
import type { PreparedAddressMapV1 } from "../contracts/generated/template_address_map_v1";
import { jsonWireAt, parseJsonWire, type JsonWireNode } from "../contracts/lossless-json";
import type { TemplateSaveVerification } from "../contracts/template-save";
import type { BoundTemplatePreparation } from "../contracts/template-transport";
import { RichApiFailure } from "./api";
import { createdLocals, translateIntent, type V7Intent } from "./v7-translation";

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
function logical(block: RichBlock, exact: boolean): string {
  if (!exact) block = normalizedBlock(block);
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

export function documentSteps(before: RichDocumentV1, after: RichDocumentV1, exact = false): RichMutation["steps"][number][] {
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
    if (logical(previous.block, exact) !== logical(item.block, exact)) {
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
type SaveTarget = { document: RichDocumentV1; facts: WorkingFacts; actionId: string; actionToken: number; kind: RichMutation["kind"] };
/** The scheduler alone owns these; strategies only read them. */
type SchedulerState = { closed: boolean; fence: string | null; running: Promise<void> | null };
interface SaveStrategy {
  admit(): void;
  step(): Promise<boolean>;
}

class DocumentDiffStrategy implements SaveStrategy {
  target: RichDocumentV1;
  facts: WorkingFacts;
  readonly targets: SaveTarget[] = [];
  sendingTarget: SaveTarget | null = null;
  rejectedTarget: SaveTarget | null = null;
  pendingRequest: RichMutation | null = null;
  prepared: string | null = null;
  constructor(private readonly scheduler: SchedulerState, public response: RichProjectResponse, readonly sessionId: string,
    private readonly send: (request: RichMutation) => Promise<RichProjectResponse>,
    readonly acknowledged: (response: RichProjectResponse) => void) {
    if (!response.workspace.project) throw new Error("Document not created");
    this.target = response.workspace.project.document;
    this.facts = response.workspace.project.facts;
  }
  get fenced(): boolean { return this.scheduler.fence !== null; }
  admit(): void { if (this.prepared !== null || this.fenced) throw new Error("AGENT_OUTCOME_UNKNOWN"); }
  rejectTarget(target: SaveTarget): void {
    this.pendingRequest = null;
    this.sendingTarget = null;
    if (this.targets.length > 1 && this.targets[0] === target) {
      this.targets.shift();
      this.rejectedTarget = null;
    } else this.rejectedTarget = target;
  }
  async step(): Promise<boolean> {
    const target = this.sendingTarget ?? this.targets[0];
    if (!target) return false;
    const before = this.response.workspace.project?.document;
    if (!before) throw new Error("Document not created");
    const beforeFacts = this.response.workspace.project?.facts;
    if (!beforeFacts) throw new Error("Facts not created");
    const steps = [...documentSteps(before, target.document), ...factSteps(beforeFacts, target.facts)];
    const [first, ...rest] = steps;
    if (!first && !this.pendingRequest) { this.targets.shift(); return true; }
    let request: RichMutation | null = this.pendingRequest ?? (first ? { schemaVersion: 1, projectId: this.response.workspace.projectId,
      clientMutationId: crypto.randomUUID(), actionId: target.actionId, kind: target.kind,
      capture: { sessionId: this.sessionId, actionId: target.actionId, actionToken: target.actionToken, dependencies: [] }, steps: [first, ...rest] } : null);
    if (!request) return false;
    const size = (value: RichMutation) => new TextEncoder().encode(JSON.stringify(value)).length;
    if (!this.pendingRequest && size(request) > 1024 * 1024) request = compactMutation(request, before);
    if (size(request) > 1024 * 1024 || request.steps.length > 1000) {
      this.rejectTarget(target);
      throw new Error("Изменение слишком большое для сохранения (лимит 1 МБ). Сократите объём изменения.");
    }
    this.pendingRequest = request;
    this.sendingTarget = target;
    this.rejectedTarget = null;
    let response: RichProjectResponse;
    try { response = await this.send(request); }
    catch (error) {
      if (typeof error === "object" && error !== null && "status" in error && typeof error.status === "number"
        && error.status >= 400 && error.status < 500) {
        this.rejectTarget(target);
      }
      throw error;
    }
    if (this.scheduler.closed) return false;
    this.response = response;
    this.acknowledged(response);
    if (response.durability === "failed") throw new Error(response.saveError ?? "PROJECT_SAVE_FAILED");
    this.pendingRequest = null;
    this.targets.shift();
    this.sendingTarget = null;
    return true;
  }
}

/** One scheduler for V1 document saves and V7 authored intents; strategies never schedule themselves. */
export class RichSaveQueue {
  private readonly scheduler: SchedulerState = { closed: false, fence: null, running: null };
  private readonly v1: DocumentDiffStrategy | null = null;
  private readonly v7: TemplateIntentStrategy | null = null;
  readonly sessionId: string;
  constructor(response: RichProjectResponse, sessionId: string, send: (request: RichMutation) => Promise<RichProjectResponse>,
    acknowledged: (response: RichProjectResponse) => void);
  constructor(template: TemplateStrategyInput);
  constructor(first: RichProjectResponse | TemplateStrategyInput, sessionId?: string,
    send?: (request: RichMutation) => Promise<RichProjectResponse>, acknowledged?: (response: RichProjectResponse) => void) {
    if ("ports" in first) {
      this.v7 = new TemplateIntentStrategy(this.scheduler, first);
      this.sessionId = first.sessionId;
      return;
    }
    if (sessionId === undefined || !send || !acknowledged) throw new Error("Document queue needs its transport");
    this.v1 = new DocumentDiffStrategy(this.scheduler, first, sessionId, send, acknowledged);
    this.sessionId = sessionId;
  }
  private get strategy(): SaveStrategy {
    const value = this.v1 ?? this.v7;
    if (!value) throw new Error("Save strategy missing");
    return value;
  }
  private get legacy(): DocumentDiffStrategy { if (!this.v1) throw new Error("V1_QUEUE_REQUIRED"); return this.v1; }
  /** V7 strategy state and operations; scheduling stays here. */
  get template(): TemplateIntentStrategy { if (!this.v7) throw new Error("V7_QUEUE_REQUIRED"); return this.v7; }
  update(document: RichDocumentV1, actionId: string, kind: RichMutation["kind"] = "typing", facts?: WorkingFacts, actionToken = 0): void {
    const value = this.legacy;
    if (value.prepared !== null || value.fenced) throw new Error("AGENT_OUTCOME_UNKNOWN");
    if (value.rejectedTarget) {
      const index = value.targets.indexOf(value.rejectedTarget);
      if (index >= 0) value.targets.splice(index, 1);
      value.rejectedTarget = null;
    }
    value.target = document; if (facts) value.facts = facts;
    const target = { document: structuredClone(document), facts: structuredClone(value.facts), actionId, actionToken, kind };
    const last = value.targets.at(-1);
    if (last?.actionId === actionId && last !== value.sendingTarget) value.targets[value.targets.length - 1] = target;
    else value.targets.push(target);
  }
  get baseline(): RichProjectResponse { return this.legacy.response; }
  refreshMetadata(response: RichProjectResponse): void {
    const value = this.legacy, previous = value.response.workspace.project, current = response.workspace.project;
    if (this.scheduler.closed || value.fenced || value.prepared !== null || !previous || !current || response.durability !== "durable"
      || response.workspace.projectId !== value.response.workspace.projectId || documentSteps(previous.document, current.document).length
      || factSteps(previous.facts, current.facts).length) throw new Error("AGENT_STALE_READ");
    value.response = response;
    value.acknowledged(response);
  }
  close(): void { this.scheduler.closed = true; this.v7?.closed(); }
  async flush(): Promise<void> {
    this.strategy.admit();
    if (this.scheduler.running) return this.scheduler.running;
    const operation = this.drain(); this.scheduler.running = operation;
    try { await operation; } finally { if (this.scheduler.running === operation) this.scheduler.running = null; }
  }
  private async drain(): Promise<void> {
    while (!this.scheduler.closed && await this.strategy.step()) { /* one unit per step */ }
  }
  beginPrepared(key: string): void {
    const value = this.legacy, project = value.response.workspace.project;
    if (this.scheduler.closed || value.fenced || value.prepared !== null || this.scheduler.running || value.pendingRequest || value.targets.length || !project
      || documentSteps(project.document, value.target).length || factSteps(project.facts, value.facts).length) throw new Error("AGENT_STALE_READ");
    value.prepared = key;
  }
  adoptPrepared(key: string, response: RichProjectResponse): void {
    const value = this.legacy, project = response.workspace.project;
    if (this.scheduler.closed || value.fenced || value.prepared !== key || response.durability !== "durable" || !project
      || response.workspace.projectId !== value.response.workspace.projectId) throw new Error("AGENT_OUTCOME_UNKNOWN");
    value.response = response;
    value.target = project.document;
    value.facts = project.facts;
    value.pendingRequest = null;
    value.targets.length = 0;
    value.sendingTarget = value.rejectedTarget = null;
    value.acknowledged(response);
  }
  endPrepared(key: string): void { const value = this.legacy; if (value.prepared === key && !value.fenced) value.prepared = null; }
  fencePrepared(): void { if (!this.v1) throw new Error("V1_QUEUE_REQUIRED"); this.scheduler.fence = "AGENT_OUTCOME_UNKNOWN"; }
  recoverPrepared(key: string): void {
    const value = this.legacy;
    if (this.scheduler.closed || this.scheduler.running) throw new Error("AGENT_OUTCOME_UNKNOWN");
    this.scheduler.fence = null; value.prepared = key;
  }
  /** Writer recovery resolves an unknown V7 outcome; dispatch stays stopped until then. */
  resolveTemplateOutcome(read: JsonWireNode, committed: boolean): void {
    if (this.scheduler.running || this.scheduler.closed) throw new Error("V7_OUTCOME_UNKNOWN");
    this.template.resolve(read, committed);
  }
}

/** V7 strategy state: ordered authored intents, one issued head, and only server-verified adoption. */
export type TemplateQueueState = { kind: "ready" | "closed" } | { kind: "conflict" | "rejected" | "fenced"; reason: string };
export type TemplateDisposition = "committed" | "no_op" | "discarded" | "corrected";
export type TemplateQueuedIntent = { intent: V7Intent; actionId: string; actionToken: number; clientMutationId: string;
  frozen: { base: JsonWireNode; request: WriterPrepareEditV2 } | null; stage: "unsent" | "frozen" | "prepared" };
export type TemplateAdoption = { item: TemplateQueuedIntent; noOp: boolean; response: JsonWireNode;
  map: PreparedAddressMapV1 | null; verification: TemplateSaveVerification | null };
export type TemplateQueuePorts = {
  proof: () => WriterProofV1;
  prepare: (base: JsonWireNode, request: WriterPrepareEditV2) => Promise<BoundTemplatePreparation>;
  save: (preparation: BoundTemplatePreparation) => Promise<TemplateSaveVerification>;
  adopted: (adoption: TemplateAdoption) => void;
  changed: (state: TemplateQueueState) => void;
  /** An action is retained once any of its intents commits, released only after complete empty disposition. */
  retained: (actionId: string, acknowledgment: TemplateSaveVerification | null) => void;
  released: (actionId: string) => void;
};
export type TemplateStrategyInput = { durable: JsonWireNode; sessionId: string; ports: TemplateQueuePorts };
type TemplateEntry = TemplateQueuedIntent & { prepared: BoundTemplatePreparation | null };
type ActionRecord = { pending: number; committed: boolean; sealed: boolean; finished: boolean };
// A definitive server answer to frozen bytes; retrying them cannot succeed.
const rejectedCodes = new Set(["JOB_SCOPE_INVALID", "JOB_IDEMPOTENCY_CONFLICT", "PREPARATION_RESPONSE_FORM_CONFLICT",
  "REQUEST_EXPIRED", "JOB_STORAGE_FULL"]);

export class TemplateIntentStrategy implements SaveStrategy {
  private readonly entries: TemplateEntry[] = [];
  private durableWire: JsonWireNode;
  private map: PreparedAddressMapV1 | null = null;
  private readonly locals = new Map<string, string>();
  private readonly actions = new Map<string, ActionRecord>();
  private block: { kind: "conflict" | "rejected"; reason: string } | null = null;
  readonly sessionId: string;
  private readonly ports: TemplateQueuePorts;
  constructor(private readonly scheduler: SchedulerState, input: TemplateStrategyInput) {
    this.durableWire = parseJsonWire(input.durable.wire);
    this.sessionId = input.sessionId;
    this.ports = input.ports;
  }
  get durable(): JsonWireNode { return this.durableWire; }
  get localBlocks(): ReadonlyMap<string, string> { return new Map(this.locals); }
  get state(): TemplateQueueState {
    if (this.scheduler.closed) return { kind: "closed" };
    if (this.scheduler.fence !== null) return { kind: "fenced", reason: this.scheduler.fence };
    return this.block ?? { kind: "ready" };
  }
  get pending(): readonly TemplateQueuedIntent[] {
    return this.entries.map(entry => ({ intent: entry.intent, actionId: entry.actionId, actionToken: entry.actionToken,
      clientMutationId: entry.clientMutationId, frozen: entry.frozen, stage: entry.stage }));
  }
  enqueue(intent: V7Intent, actionId: string, actionToken: number): void {
    if (this.scheduler.closed) throw new Error("Редактор закрыт.");
    this.entries.push({ intent: { ...intent, prior: new Map(intent.prior) }, actionId, actionToken,
      clientMutationId: `${this.sessionId}:${crypto.randomUUID()}`, frozen: null, prepared: null, stage: "unsent" });
    const record = this.actions.get(actionId) ?? { pending: 0, committed: false, sealed: false, finished: false };
    if (record.finished) throw new Error("History action is already complete");
    record.pending++;
    this.actions.set(actionId, record);
  }
  /** The editor seals an action when no further input can join it. */
  seal(actionId: string): void {
    const record = this.actions.get(actionId);
    if (!record) return;
    record.sealed = true;
    this.settle(actionId);
  }
  admit(): void {
    if (this.scheduler.fence !== null) throw new Error("V7_OUTCOME_UNKNOWN");
    if (this.block) throw new Error(this.block.kind === "conflict" ? "V7_INPUT_CONFLICT" : "V7_INPUT_REJECTED");
  }
  closed(): void { this.ports.changed({ kind: "closed" }); }
  /** Explicit discard after a block; refused while an outcome is unknown. */
  discardUnsaved(): TemplateQueuedIntent[] {
    if (this.scheduler.running || this.scheduler.fence !== null || this.scheduler.closed) throw new Error("Дождитесь восстановления сохранения");
    const discarded = this.pending.slice();
    this.dispose(this.entries.splice(0), "discarded");
    this.block = null;
    this.ports.changed(this.state);
    return discarded;
  }
  /** Correction replaces a blocked head and its buffer with intents expressed against the canonical durable state.
   * A container whose saved text moved since its pending input began needs the user's explicit keep choice. */
  correct(corrections: readonly V7Intent[], actionId: string, actionToken: number,
    choices: { keepEditorText?: ReadonlySet<string>; unchanged?: ReadonlySet<string> } = {}): void {
    if (!this.block || this.scheduler.running || this.scheduler.fence !== null || this.scheduler.closed) throw new Error("V7_CORRECTION_NOT_ALLOWED");
    const bases = this.unsavedBase(), covered = new Set(choices.unchanged ?? []);
    for (const intent of corrections) for (const [key, prior] of intent.prior) {
      const base = bases.get(key);
      if (base === undefined) throw new Error("V7_CORRECTION_NOT_ALLOWED");
      if (base !== prior && !choices.keepEditorText?.has(key)) throw new Error("V7_CORRECTION_CONFLICT");
      covered.add(key);
    }
    // Every container with pending input is either corrected or explicitly equal to the saved text; nothing drops silently.
    if ([...bases.keys()].some(key => !covered.has(key))) throw new Error("V7_CORRECTION_NOT_ALLOWED");
    const replaced = this.entries.splice(0);
    this.block = null;
    this.dispose(replaced, "corrected");
    for (const intent of corrections) this.enqueue(intent, actionId, actionToken);
    this.ports.changed(this.state);
  }
  /** Prior text of the first unsaved intent per container: the state correction must still match. */
  unsavedBase(): Map<string, string> {
    const result = new Map<string, string>();
    for (const entry of this.entries) for (const [key, text] of entry.intent.prior) if (!result.has(key)) result.set(key, text);
    return result;
  }
  /** A server history command result becomes the new base only when no input is pending. */
  adoptDurable(response: JsonWireNode): void {
    if (this.entries.length || this.block || this.scheduler.fence !== null || this.scheduler.running || this.scheduler.closed) {
      throw new Error("V7_CORRECTION_NOT_ALLOWED");
    }
    this.durableWire = parseJsonWire(response.wire);
    this.map = null;
  }
  /** The issued head as recovery must look it up in the durable replay record. */
  headIdentity(): { clientMutationId: string; mutationWire: string | null } | null {
    const head = this.entries[0];
    if (!head?.frozen) return null;
    return { clientMutationId: head.clientMutationId, mutationWire: head.prepared?.prepared.delta.mutationWire ?? null };
  }
  resolve(read: JsonWireNode, committed: boolean): void {
    if (this.scheduler.fence === null) throw new Error("V7_OUTCOME_KNOWN");
    const head = this.entries[0], response = parseJsonWire(read.wire), snapshot = jsonWireAt(response, ["snapshot"]).wire;
    this.scheduler.fence = null;
    if (!head?.frozen) { this.durableWire = response; this.map = null; this.ports.changed(this.state); return; }
    if (committed) {
      this.entries.shift();
      const result = head.prepared;
      // The kept map still translates later input only when the read state is exactly its result.
      const mapped = result !== null && jsonWireAt(parseJsonWire(result.prepared.responseWire.wire), ["snapshot"]).wire === snapshot;
      this.durableWire = response;
      this.map = mapped ? result.address.map : null;
      const created = mapped ? createdLocals(head.intent, { response, map: this.map, locals: this.locals }) : null;
      for (const [local, canonicalId] of created ?? []) this.locals.set(local, canonicalId);
      this.dispose([head], "committed", null);
      this.ports.adopted({ item: head, noOp: false, response, map: this.map, verification: null });
      if (!mapped && this.entries.length) this.block = { kind: "conflict", reason: "committed result has no retained map" };
    } else if (jsonWireAt(head.frozen.base, ["snapshot"]).wire !== snapshot) {
      this.durableWire = response; this.map = null;
      this.block = { kind: "conflict", reason: "base changed before the head committed" };
    }
    this.ports.changed(this.state);
  }
  private dispose(items: readonly TemplateEntry[], disposition: TemplateDisposition, acknowledgment: TemplateSaveVerification | null = null): void {
    for (const item of items) {
      const record = this.actions.get(item.actionId);
      if (!record) continue;
      record.pending--;
      if (disposition === "committed" && !record.committed) {
        record.committed = true;
        this.ports.retained(item.actionId, acknowledgment);
      }
      this.settle(item.actionId);
    }
  }
  private settle(actionId: string): void {
    const record = this.actions.get(actionId);
    if (!record || !record.sealed || record.pending > 0 || record.finished) return;
    record.finished = true;
    if (!record.committed) this.ports.released(actionId);
  }
  private coalesce(): void {
    const [first, next] = this.entries;
    if (!first || !next || first.frozen || next.frozen || first.actionId !== next.actionId) return;
    const left = first.intent.operation, right = next.intent.operation;
    if (left.kind !== "replace_text" || right.kind !== "replace_text" || JSON.stringify(left.styles) !== JSON.stringify(right.styles)
      || JSON.stringify(left.container) !== JSON.stringify(right.container) || right.start !== right.end
      || right.side !== "before" || right.start !== left.start + left.text.length) return;
    // Appending at the end of pending text in one action is the transaction Python would receive in sequence.
    first.intent = { ...first.intent, operation: { ...left, text: left.text + right.text } };
    first.actionToken = next.actionToken;
    this.entries.splice(1, 1);
    const record = this.actions.get(first.actionId);
    if (record) record.pending--;
    this.coalesce();
  }
  private stop(kind: "conflict" | "rejected", reason: string): never {
    this.block = { kind, reason };
    this.ports.changed(this.state);
    throw new Error(kind === "conflict" ? "V7_INPUT_CONFLICT" : "V7_INPUT_REJECTED");
  }
  private fence(reason: string): never {
    this.scheduler.fence = reason;
    this.ports.changed(this.state);
    throw new Error("V7_OUTCOME_UNKNOWN");
  }
  private failed(error: unknown, stage: "prepare" | "save"): never {
    // A malformed or oversized request is refused before any processing; resending it cannot help.
    if (error instanceof RichApiFailure && (error.status >= 400 && error.status < 500 && rejectedCodes.has(error.code)
      || error.status === 413 || error.status === 422)) {
      return this.stop("rejected", error.code);
    }
    if (error instanceof RichApiFailure && error.status >= 400 && error.status < 500
      || error instanceof Error && error.message === "INVALID_RESULT") {
      // The server answered, but the outcome cannot be trusted or applied to this base; recovery resolves it first.
      return this.fence(error instanceof RichApiFailure ? error.code : `${stage}:INVALID_RESULT`);
    }
    // No answer: the frozen bytes stay issued for an identical retry.
    throw error;
  }
  async step(): Promise<boolean> {
    if (!this.entries[0]?.frozen) this.coalesce();
    const entry = this.entries[0];
    if (!entry) return false;
    if (!entry.frozen) {
      const capture = { sessionId: this.sessionId, actionId: entry.actionId, actionToken: entry.actionToken, dependencies: [] };
      const translated = translateIntent(entry.intent, { response: this.durableWire, map: this.map, locals: this.locals }, capture);
      if (translated.kind === "conflict") this.stop("conflict", translated.reason);
      const request: WriterPrepareEditV2 = { schemaVersion: 2, proof: structuredClone(this.ports.proof()), preparation: {
        schemaVersion: 1, clientMutationId: entry.clientMutationId, snapshot: snapshotIdentity(jsonWireAt(this.durableWire, ["snapshot"]).value),
        capture, operations: [translated.operation] } };
      entry.frozen = { base: this.durableWire, request };
      entry.stage = "frozen";
    }
    if (!entry.prepared) {
      try { entry.prepared = await this.ports.prepare(entry.frozen.base, structuredClone(entry.frozen.request)); }
      catch (error) { this.failed(error, "prepare"); }
      entry.stage = "prepared";
    }
    if (this.scheduler.closed) return false;
    const prepared = entry.prepared;
    if (prepared.prepared.delta.mutationWire === null) {
      this.map = prepared.address.map;
      this.entries.shift();
      this.dispose([entry], "no_op");
      this.ports.adopted({ item: entry, noOp: true, response: this.durableWire, map: prepared.address.map, verification: null });
      return true;
    }
    let verification: TemplateSaveVerification;
    try { verification = await this.ports.save(prepared); }
    catch (error) { this.failed(error, "save"); }
    if (this.scheduler.closed) return false;
    if (verification.kind !== "committed") this.fence(verification.kind);
    const created = createdLocals(entry.intent, { response: verification.responseWire, map: prepared.address.map, locals: this.locals });
    if (!created) this.fence("created block has no single verified result");
    for (const [local, canonicalId] of created) this.locals.set(local, canonicalId);
    this.durableWire = verification.responseWire;
    this.map = prepared.address.map;
    this.entries.shift();
    this.dispose([entry], "committed", verification);
    this.ports.adopted({ item: entry, noOp: false, response: this.durableWire, map: prepared.address.map, verification });
    return true;
  }
}

export function snapshotIdentity(value: unknown): WriterPrepareEditV2["preparation"]["snapshot"] {
  if (typeof value !== "object" || value === null) throw new Error("INVALID_RESULT");
  const field = (key: string): unknown => Reflect.get(value, key);
  const text = (key: string): string => { const item = field(key); if (typeof item !== "string") throw new Error("INVALID_RESULT"); return item; };
  const count = (key: string): number => { const item = field(key); if (typeof item !== "number") throw new Error("INVALID_RESULT"); return item; };
  return { projectId: text("projectId"), projectRevision: count("projectRevision"), documentRevision: count("documentRevision"),
    documentHash: text("documentHash"), factsHash: text("factsHash"), packageHash: text("packageHash"), presentationHash: text("presentationHash") };
}
