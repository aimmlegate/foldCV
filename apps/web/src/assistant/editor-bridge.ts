import type { AgentClaimResult } from "../contracts/generated/agent_claim_result";
import type { AgentCommitResult } from "../contracts/generated/agent_commit_result";
import type { AgentEditBatch } from "../contracts/generated/agent_edit_batch";
import type { AgentEditReceipt } from "../contracts/generated/agent_edit_receipt";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { SessionHistory, CellChange, CellValue, HistoryReservation } from "../rich/history";
import type { RichSaveQueue } from "../rich/save-queue";
import type { WriterAdvanceV1 } from "../contracts/generated/background_writer_advance_v1";
import type { AssistantProjectActionClaimV1 } from "../contracts/generated/assistant_project_action_claim_v1";
import type { AssistantProjectActionResultV1 } from "../contracts/generated/assistant_project_action_result_v1";

export type PreparedEditorPort = {
  history: SessionHistory;
  queue: RichSaveQueue;
  flush: () => Promise<RichProjectResponse>;
  cells: (response: RichProjectResponse) => ReadonlyMap<string, CellValue>;
  preview: (batch: AgentEditBatch) => Promise<RichProjectResponse>;
  enter: () => void;
  leave: () => void;
  retainImages: () => Promise<void>;
  fence: (receipt: AgentEditReceipt | null, savedAction?: boolean) => void;
  reviewedAuthority?: (batch?: AgentEditBatch) => Promise<WriterAdvanceV1 | null>;
  reviewedSaved?: (project: RichProjectResponse) => Promise<void>;
};
export type PreparedApi = {
  resolve?: (reviewKey: string) => Promise<string>;
  claim: (batchId: string) => Promise<AgentClaimResult>;
  commit: (claim: AgentClaimResult, writer?: WriterAdvanceV1 | null) => Promise<AgentCommitResult>;
  recover: (batchId: string) => Promise<{ receipt: AgentEditReceipt; project: RichProjectResponse | null } | null>;
  report: (receipt: AgentEditReceipt) => Promise<void>;
};
export type PreparedActionApi = {
  claim: () => Promise<AssistantProjectActionClaimV1>;
  commit: (claim: AssistantProjectActionClaimV1, writer: WriterAdvanceV1 | null) => Promise<AssistantProjectActionResultV1>;
  recover: () => Promise<AssistantProjectActionResultV1>;
  cancel?: () => Promise<void>;
};

export function cellChanges(before: ReadonlyMap<string, CellValue>, after: ReadonlyMap<string, CellValue>): CellChange[] {
  return [...new Set([...before.keys(), ...after.keys()])].filter(key => !key.startsWith("request:"))
    .map(key => ({ key, before: before.get(key) ?? null, after: after.get(key) ?? null })).filter(change => change.before !== change.after);
}

function matches(receipt: AgentEditReceipt, batch: AgentEditBatch): boolean {
  return receipt.batchId === batch.id && receipt.runId === batch.runId && receipt.toolKey === batch.toolKey
    && receipt.clientMutationId === batch.mutation.clientMutationId && receipt.requestSha256 === batch.requestSha256;
}

function rejected(batch: AgentEditBatch): AgentEditReceipt {
  return { batchId: batch.id, runId: batch.runId, toolKey: batch.toolKey,
    clientMutationId: batch.mutation.clientMutationId, requestSha256: batch.requestSha256,
    disposition: "stale", projectRevision: null, documentRevision: null, factsRevision: null,
    durable: false, error: { code: "AGENT_STALE_READ" } };
}

/** The canonical save finishes before any cells enter mounted history or autosave. */
export class PreparedEditorBridge {
  private readonly completed = new Set<string>();
  private readonly active = new Map<string, Promise<void>>();
  private closed = false;
  constructor(private readonly editor: PreparedEditorPort) {}

  apply(batchId: string, api: PreparedApi): Promise<void> {
    if (this.completed.has(batchId) || this.closed) return Promise.resolve();
    const running = this.active.get(batchId);
    if (running) return running;
    if (this.active.size) return Promise.reject(new Error("AGENT_BUSY"));
    const operation = this.perform(batchId, api);
    this.active.set(batchId, operation);
    void operation.finally(() => this.active.delete(batchId)).catch(() => {});
    return operation;
  }

  private async perform(reviewKey: string, api: PreparedApi): Promise<void> {
    const editor = this.editor;
    let claim: AgentClaimResult | null = null, reservation: HistoryReservation | null = null;
    let commitStarted = false, saved: AgentEditReceipt | null = null, fenced = false;
    try {
      await editor.flush();
      if (this.closed) return;
      const batchId = api.resolve ? await api.resolve(reviewKey) : reviewKey;
      claim = await api.claim(batchId);
      const batch = claim.batch;
      if (batch.id !== batchId || batch.mutation.capture.sessionId !== editor.history.session
        || batch.mutation.projectId !== editor.queue.baseline.workspace.projectId) throw new Error("AGENT_OWNER_MISMATCH");
      await editor.flush();
      if (this.closed) throw new Error("AGENT_CANCELLED");
      const direction = batch.mutation.kind === "undo" || batch.mutation.kind === "redo" ? batch.mutation.kind : null;
      if (direction && editor.history.navigation(direction)?.actionId !== batch.mutation.actionId) throw new Error("AGENT_STALE_READ");
      reservation = editor.history.reserve(direction ? `history-review:${batch.id}` : batch.mutation.actionId);
      if (!reservation) throw new Error("AGENT_STALE_READ");
      editor.queue.beginPrepared(batch.id);
      editor.enter();
      const before = editor.cells(editor.queue.baseline);
      const preview = await editor.preview(batch);
      if (preview.workspace.projectRevision !== editor.queue.baseline.workspace.projectRevision + 1
        || preview.workspace.documentRevision !== editor.queue.baseline.workspace.documentRevision + 1) throw new Error("AGENT_STALE_READ");
      const proposed = cellChanges(before, editor.cells(preview));
      if (!editor.history.reserved(reservation) || proposed.some(change => editor.history.read(change.key) !== change.before)) throw new Error("AGENT_STALE_READ");
      if (direction && !editor.history.navigationMatches(direction, proposed)) throw new Error("AGENT_STALE_READ");
      if (this.closed) throw new Error("AGENT_CANCELLED");
      const writer = await editor.reviewedAuthority?.(batch);
      if (this.closed) throw new Error("AGENT_CANCELLED");
      commitStarted = true;
      let result: Awaited<ReturnType<PreparedApi["recover"]>>;
      try { result = await api.commit(claim, writer); }
      catch { result = await api.recover(batch.id).catch(() => null); }
      if (!result || !matches(result.receipt, batch) || result.receipt.disposition === "outcome_unknown") throw new Error("AGENT_OUTCOME_UNKNOWN");
      if (!result.receipt.durable) {
        this.completed.add(reviewKey);
        return;
      }
      saved = result.receipt;
      if (!result.project) throw new Error("AGENT_OUTCOME_UNKNOWN");
      const changes = cellChanges(before, editor.cells(result.project));
      const proof = result.project.workspace.mutationReplay.find(item => item.clientMutationId === batch.mutation.clientMutationId);
      if (this.closed || result.project.durability !== "durable" || result.project.workspace.projectRevision !== saved.projectRevision
        || result.project.workspace.documentRevision !== saved.documentRevision || proof?.requestSha256 !== batch.requestSha256
        || proof.resultingRevision !== saved.projectRevision || JSON.stringify(changes) !== JSON.stringify(proposed)) throw new Error("AGENT_OUTCOME_UNKNOWN");
      editor.queue.adoptPrepared(batch.id, result.project);
      if (!(direction ? editor.history.publishNavigation(reservation, direction, changes) : editor.history.publish(reservation, changes))) throw new Error("AGENT_OUTCOME_UNKNOWN");
      reservation = null;
      await editor.reviewedSaved?.(result.project);
      await editor.retainImages();
      this.completed.add(reviewKey);
      await api.report(saved).catch(() => {});
    } catch (error) {
      if (commitStarted) {
        fenced = true;
        editor.queue.fencePrepared();
        editor.history.close();
        editor.fence(saved);
      } else if (claim) {
        await api.report(rejected(claim.batch)).catch(() => {});
        this.completed.add(reviewKey);
      }
      throw error;
    } finally {
      if (reservation && !fenced) editor.history.discard(reservation);
      if (claim && !fenced) editor.queue.endPrepared(claim.batch.id);
      if (!fenced) editor.leave();
    }
  }

  applyAction(key: string, api: PreparedActionApi): Promise<void> {
    if (this.completed.has(key) || this.closed) return Promise.resolve();
    const running = this.active.get(key);
    if (running) return running;
    if (this.active.size) return Promise.reject(new Error("AGENT_BUSY"));
    const operation = this.performAction(key, api);
    this.active.set(key, operation);
    void operation.finally(() => this.active.delete(key)).catch(() => {});
    return operation;
  }

  private async performAction(key: string, api: PreparedActionApi): Promise<void> {
    const editor = this.editor;
    let started = false, saved = false, fenced = false;
    try {
      await editor.flush();
      if (this.closed) return;
      const claim = await api.claim();
      await editor.flush();
      if (this.closed) throw new Error("AGENT_CANCELLED");
      editor.queue.beginPrepared(key); editor.enter();
      const before = editor.cells(editor.queue.baseline), writer = await editor.reviewedAuthority?.() ?? null;
      if (this.closed) throw new Error("AGENT_CANCELLED");
      started = true;
      let result: AssistantProjectActionResultV1;
      try { result = await api.commit(claim, writer); }
      catch { result = await api.recover(); }
      if (["applying", "outcome_unknown"].includes(result.proposal.state)) throw new Error("AGENT_OUTCOME_UNKNOWN");
      if (!result.operation?.durable) { this.completed.add(key); return; }
      saved = true;
      if (result.project) {
        if (this.closed || cellChanges(before, editor.cells(result.project)).length) throw new Error("AGENT_OUTCOME_UNKNOWN");
        editor.queue.endPrepared(key);
        editor.queue.refreshMetadata(result.project);
        await editor.reviewedSaved?.(result.project);
        await editor.retainImages();
      }
      this.completed.add(key);
    } catch (error) {
      if (started) {
        fenced = true; editor.queue.fencePrepared(); editor.history.close(); editor.fence(null, saved);
      } else await api.cancel?.().catch(() => {});
      throw error;
    } finally {
      if (!fenced) { editor.queue.endPrepared(key); editor.leave(); }
    }
  }

  close(): void { this.closed = true; }
}
