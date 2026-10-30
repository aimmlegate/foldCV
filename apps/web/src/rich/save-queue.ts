import type { TemplateEditPreparationV1 } from "../contracts/generated/template_edit_preparation_v1";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import { ProjectApiFailure, type EditResult } from "./v7-connection";
import { createdLocals, translateIntent, type V7Intent } from "./v7-translation";

/** The scheduler alone owns these; the strategy only reads them. */
type SchedulerState = { closed: boolean; running: Promise<void> | null };

/** One scheduler over the V7 strategy; the strategy never schedules itself. */
export class RichSaveQueue {
  private readonly scheduler: SchedulerState = { closed: false, running: null };
  /** V7 strategy state and operations; scheduling stays here. */
  readonly template: TemplateIntentStrategy;
  readonly sessionId: string;
  constructor(input: TemplateStrategyInput) {
    this.template = new TemplateIntentStrategy(this.scheduler, input);
    this.sessionId = input.sessionId;
  }
  close(): void { this.scheduler.closed = true; this.template.closed(); }
  async flush(): Promise<void> {
    this.template.admit();
    if (this.scheduler.running) return this.scheduler.running;
    const operation = this.drain(); this.scheduler.running = operation;
    try { await operation; } finally { if (this.scheduler.running === operation) this.scheduler.running = null; }
  }
  private async drain(): Promise<void> {
    while (!this.scheduler.closed && await this.template.step()) { /* one unit per step */ }
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
// A refusal of the request itself (4xx: rejected input, a deleted project, a fenced import), so sending it again cannot
// succeed. No answer, a timeout or a server failure (5xx, for example a full disk) is sent again.
function refused(error: ProjectApiFailure): boolean {
  return error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
}

export class TemplateIntentStrategy {
  private readonly entries: TemplateQueuedIntent[] = [];
  private durableResponse: TemplateProjectResponseV1;
  private readonly locals = new Map<string, string>();
  private readonly actions = new Map<string, ActionRecord>();
  // Intents queued before a lost acknowledgment: an issued one is checked against the saved state before it is sent again,
  // and one the current state cannot take is reported with its text instead of blocking the queue (plan 2.6).
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
    if (entry) await this.reconcile(entry);
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
  /** The lost-acknowledgment rule (plan 2.6) for the head: an applied id is done; an issued intent is sent again at the same
   * revision; any other issued one is reported with its text and dropped. An unsent intent is never dropped here: it is
   * translated against the current state at its turn. */
  private async reconcile(entry: TemplateQueuedIntent): Promise<void> {
    const current = await this.ports.read();
    const done = new Set((current.workspace.mutationReplay ?? []).map(row => row.clientMutationId));
    if (done.has(entry.clientMutationId)) {
      // The created blocks of a lost reply are unknown; later intents that name them conflict and keep their text.
      this.recoveryRequired.delete(entry.clientMutationId);
      this.adopt(entry, current, null, false);
      return;
    }
    this.durableResponse = current;
    const issued = entry.issued, workspace = current.workspace;
    if (!issued) return;
    if (entry.baseRevision === workspace.projectRevision) { this.recoveryRequired.delete(entry.clientMutationId); return; }
    // Only commits outside the document (an export record, a rename) moved the revision: translate it again at its turn.
    if (issued.snapshot.documentRevision === workspace.documentRevision) { entry.issued = null; return; }
    this.drop(entry);
  }
  private drop(entry: TemplateQueuedIntent): void {
    this.recoveryRequired.delete(entry.clientMutationId);
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
      return true;
    }
    if (refused(error)) return this.stop("rejected", error.code);
    // No usable answer: the issued request is sent again unchanged; its id makes the retry idempotent.
    throw error;
  }
  async step(): Promise<boolean> {
    const head = this.entries[0];
    if (head?.issued && this.recoveryRequired.has(head.clientMutationId)) {
      await this.reconcile(head);
      if (this.entries[0] !== head) return true;
    }
    if (!this.entries[0]?.issued) this.coalesce();
    const entry = this.entries[0];
    if (!entry) return false;
    if (!entry.issued) {
      const capture = { sessionId: this.sessionId, actionId: entry.actionId, actionToken: entry.actionToken, dependencies: [] };
      const translated = translateIntent(entry.intent, { response: this.durableResponse, locals: this.locals }, capture);
      if (translated.kind === "conflict") {
        if (this.recoveryRequired.has(entry.clientMutationId)) { this.drop(entry); return true; }
        this.stop("conflict", translated.reason);
      }
      this.recoveryRequired.delete(entry.clientMutationId);
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
    if (!created) {
      if (!result.replayed) this.stop("conflict", "created block has no single verified result");
      // A replay after a restart may not name the created block: the saved state settles this intent, and later input
      // on that block is reported with its text instead of blocking the queue.
      for (const item of this.entries) this.recoveryRequired.add(item.clientMutationId);
      await this.reconcile(entry);
      return true;
    }
    for (const [local, canonicalId] of created) this.locals.set(local, canonicalId);
    this.adopt(entry, result.response, result, noOp);
    return true;
  }
}
