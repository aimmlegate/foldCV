import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import { semantic } from "./fact-cells";
import { normalizedBlock } from "./normalize";
import { compactMutation } from "./compact-mutation";
import type { TemplateEditPreparationV1 } from "../contracts/generated/template_edit_preparation_v1";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import { ProjectApiFailure, type EditResult } from "./v7-connection";
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
}

/** V7 strategy (D109): ordered authored intents, one request per intent against the last verified response, the full
 * response adopted from each reply. */
export type TemplateQueueState = { kind: "ready" | "closed" } | { kind: "conflict" | "rejected" | "replaced"; reason: string };
export type TemplateDisposition = "committed" | "no_op" | "discarded" | "corrected" | "lost";
export type TemplateQueuedIntent = { intent: V7Intent; actionId: string; actionToken: number; clientMutationId: string;
  baseRevision: number; issued: TemplateEditPreparationV1 | null };
export type TemplateAdoption = { item: TemplateQueuedIntent; noOp: boolean; response: TemplateProjectResponseV1; result: EditResult | null };
export type TemplateQueuePorts = {
  edit: (preparation: TemplateEditPreparationV1, baseRevision: number) => Promise<EditResult>;
  /** The current saved state, for the lost-acknowledgment rule. */
  read: () => Promise<TemplateProjectResponseV1>;
  adopted: (adoption: TemplateAdoption) => void;
  changed: (state: TemplateQueueState) => void;
  /** An action is retained once any of its intents commits, released only after complete empty disposition. */
  retained: (actionId: string) => void;
  released: (actionId: string) => void;
  /** Intents the server neither applied nor can take any more; their text is reported before they are dropped. */
  lost: (items: readonly TemplateQueuedIntent[]) => void;
  /** The unacknowledged intents changed; the session keeps them in the pending draft. */
  pending?: (items: readonly TemplateQueuedIntent[]) => void | Promise<void>;
};
export type TemplateStrategyInput = { durable: TemplateProjectResponseV1; sessionId: string; ports: TemplateQueuePorts };
type ActionRecord = { pending: number; committed: boolean; sealed: boolean; finished: boolean };
// Refusals of the request itself; sending it again cannot succeed.
const rejectedCodes = new Set(["V7_INPUT_REJECTED", "PROJECT_TOO_LARGE", "PROJECT_READ_ONLY", "MUTATION_ID_REUSED", "REQUEST_EXPIRED",
  "DEPENDENCY_CHANGED", "INVALID_REQUEST", "HISTORY_STALE"]);

export class TemplateIntentStrategy implements SaveStrategy {
  private readonly entries: TemplateQueuedIntent[] = [];
  private durableResponse: TemplateProjectResponseV1;
  private readonly locals = new Map<string, string>();
  private readonly actions = new Map<string, ActionRecord>();
  private readonly recoveryRequired = new Set<string>();
  private block: { kind: "conflict" | "rejected" | "replaced"; reason: string } | null = null;
  readonly sessionId: string;
  private readonly ports: TemplateQueuePorts;
  constructor(private readonly scheduler: SchedulerState, input: TemplateStrategyInput) {
    this.durableResponse = input.durable;
    this.sessionId = input.sessionId;
    this.ports = input.ports;
  }
  get durable(): TemplateProjectResponseV1 { return this.durableResponse; }
  get localBlocks(): ReadonlyMap<string, string> { return new Map(this.locals); }
  get state(): TemplateQueueState {
    if (this.scheduler.closed) return { kind: "closed" };
    return this.block ?? { kind: "ready" };
  }
  get pending(): readonly TemplateQueuedIntent[] { return this.entries.map(entry => ({ ...entry })); }
  enqueue(intent: V7Intent, actionId: string, actionToken: number, clientMutationId = `${this.sessionId}:${crypto.randomUUID()}`): void {
    if (this.scheduler.closed) throw new Error("Редактор закрыт.");
    this.entries.push({ intent: { ...intent, prior: new Map(intent.prior) }, actionId, actionToken, clientMutationId,
      baseRevision: this.durableResponse.workspace.projectRevision, issued: null });
    const record = this.actions.get(actionId) ?? { pending: 0, committed: false, sealed: false, finished: false };
    if (record.finished) throw new Error("History action is already complete");
    record.pending++;
    this.actions.set(actionId, record);
    void this.ports.pending?.(this.pending);
  }
  /** The editor seals an action when no further input can join it. */
  seal(actionId: string): void {
    const record = this.actions.get(actionId);
    if (!record) return;
    record.sealed = true;
    this.settle(actionId);
  }
  admit(): void {
    if (this.block) throw new Error(this.block.kind === "conflict" ? "V7_INPUT_CONFLICT" : this.block.kind === "replaced" ? "EDITOR_REPLACED" : "V7_INPUT_REJECTED");
  }
  closed(): void { this.ports.changed({ kind: "closed" }); }
  /** Explicit discard after a block. */
  discardUnsaved(): TemplateQueuedIntent[] {
    if (this.scheduler.running || this.scheduler.closed) throw new Error("Дождитесь окончания сохранения");
    const discarded = this.pending.slice();
    this.dispose(this.entries.splice(0), "discarded");
    if (this.block?.kind !== "replaced") this.block = null;
    this.ports.changed(this.state);
    this.ports.pending?.(this.pending);
    return discarded;
  }
  /** Correction replaces a blocked queue with intents expressed against the verified state. A container whose saved text
   * moved since its pending input began needs the user's explicit keep choice. */
  correct(corrections: readonly V7Intent[], actionId: string, actionToken: number,
    choices: { keepEditorText?: ReadonlySet<string>; unchanged?: ReadonlySet<string> } = {}): void {
    if (!this.block || this.block.kind === "replaced" || this.scheduler.running || this.scheduler.closed) throw new Error("V7_CORRECTION_NOT_ALLOWED");
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
  /** A server history result or a fresh read becomes the base only when no input is pending. */
  adoptDurable(response: TemplateProjectResponseV1): void {
    if (this.entries.length || this.block || this.scheduler.running || this.scheduler.closed) throw new Error("V7_CORRECTION_NOT_ALLOWED");
    this.durableResponse = response;
  }
  restore(items: readonly TemplateQueuedIntent[], locals: readonly [string, string][] = []): void {
    if (this.entries.length || this.scheduler.running) throw new Error("V7_CORRECTION_NOT_ALLOWED");
    for (const [local, canonical] of locals) this.locals.set(local, canonical);
    for (const item of items) {
      this.enqueue(item.intent, item.actionId, item.actionToken, item.clientMutationId);
      const entry = this.entries.at(-1);
      if (entry) { entry.baseRevision = item.baseRevision; entry.issued = item.issued; }
      this.recoveryRequired.add(item.clientMutationId);
      this.seal(item.actionId);
    }
  }
  async recoverPending(): Promise<void> {
    for (const item of this.entries) this.recoveryRequired.add(item.clientMutationId);
    const entry = this.entries[0];
    if (entry) { await this.reconcile(entry); this.recoveryRequired.delete(entry.clientMutationId); }
    else this.durableResponse = await this.ports.read();
  }
  private dispose(items: readonly TemplateQueuedIntent[], disposition: TemplateDisposition): void {
    for (const item of items) {
      const record = this.actions.get(item.actionId);
      if (!record) continue;
      record.pending--;
      if (disposition === "committed" && !record.committed) {
        record.committed = true;
        this.ports.retained(item.actionId);
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
    if (!first || !next || first.issued || next.issued || first.actionId !== next.actionId) return;
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
  private stop(kind: "conflict" | "rejected" | "replaced", reason: string): never {
    this.block = { kind, reason };
    this.ports.changed(this.state);
    throw new Error(kind === "conflict" ? "V7_INPUT_CONFLICT" : kind === "replaced" ? "EDITOR_REPLACED" : "V7_INPUT_REJECTED");
  }
  private adopt(entry: TemplateQueuedIntent, response: TemplateProjectResponseV1, result: EditResult | null, noOp: boolean): void {
    this.durableResponse = response;
    this.entries.shift();
    this.dispose([entry], noOp ? "no_op" : "committed");
    this.ports.adopted({ item: entry, noOp, response, result });
    this.ports.pending?.(this.pending);
  }
  /** The lost-acknowledgment rule (plan 2.6): applied ids are dropped as done; an intent the current state can still take is
   * re-issued; any other is reported with its text and dropped. */
  private async reconcile(entry: TemplateQueuedIntent): Promise<void> {
    const current = await this.ports.read();
    const done = new Set((current.workspace.mutationReplay ?? []).map(row => row.clientMutationId));
    if (done.has(entry.clientMutationId)) {
      // The created blocks of a lost reply are unknown; later intents that name them conflict and keep their text.
      this.adopt(entry, current, null, false);
      return;
    }
    this.durableResponse = current;
    if (entry.baseRevision === current.workspace.projectRevision) return;
    this.entries.shift();
    this.dispose([entry], "lost");
    this.ports.lost([entry]);
    this.ports.pending?.(this.pending);
  }
  private async failed(error: unknown, entry: TemplateQueuedIntent): Promise<boolean> {
    if (!(error instanceof ProjectApiFailure)) throw error;
    if (error.code === "EDITOR_REPLACED") return this.stop("replaced", error.code);
    if (error.code === "REVISION_CONFLICT" || error.code === "EDITOR_TOKEN_UNKNOWN") {
      for (const item of this.entries) this.recoveryRequired.add(item.clientMutationId);
      await this.reconcile(entry);
      this.recoveryRequired.delete(entry.clientMutationId);
      return true;
    }
    if (error.status === 413 || error.status === 422 || rejectedCodes.has(error.code)) return this.stop("rejected", error.code);
    // No usable answer: the issued request is retried unchanged on the next flush; its id makes the retry idempotent.
    throw error;
  }
  async step(): Promise<boolean> {
    const head = this.entries[0];
    if (head && this.recoveryRequired.delete(head.clientMutationId)) {
      await this.reconcile(head);
      if (this.entries[0] !== head) return true;
    }
    if (!this.entries[0]?.issued) this.coalesce();
    const entry = this.entries[0];
    if (!entry) return false;
    if (!entry.issued) {
      const capture = { sessionId: this.sessionId, actionId: entry.actionId, actionToken: entry.actionToken, dependencies: [] };
      const translated = translateIntent(entry.intent, { response: this.durableResponse, locals: this.locals }, capture);
      if (translated.kind === "conflict") this.stop("conflict", translated.reason);
      const snapshot = this.durableResponse.snapshot;
      if (!snapshot) this.stop("rejected", "verified result has no snapshot");
      entry.issued = { schemaVersion: 1, clientMutationId: entry.clientMutationId, snapshot, capture, operations: [translated.operation] };
      entry.baseRevision = this.durableResponse.workspace.projectRevision;
      await this.ports.pending?.(this.pending);
    }
    let result: EditResult;
    try { result = await this.ports.edit(entry.issued, entry.baseRevision); }
    catch (error) { return this.failed(error, entry); }
    if (this.scheduler.closed) return false;
    const noOp = !result.replayed && result.revision === entry.baseRevision;
    const created = createdLocals(entry.intent, result.createdBlocks);
    if (!created && !result.replayed) this.stop("conflict", "created block has no single verified result");
    for (const [local, canonicalId] of created ?? []) this.locals.set(local, canonicalId);
    this.adopt(entry, result.response, result, noOp);
    return true;
  }
}
