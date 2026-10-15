import type { AgentClaimResult } from "../contracts/generated/agent_claim_result";
import type { AgentCommitResult } from "../contracts/generated/agent_commit_result";
import type { AgentEditBatch } from "../contracts/generated/agent_edit_batch";
import type { AgentEditReceipt } from "../contracts/generated/agent_edit_receipt";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { SessionHistory, CellChange, CellValue, HistoryReservation } from "../rich/history";
import type { RichSaveQueue } from "../rich/save-queue";

export type PreparedEditorPort = {
  history: SessionHistory;
  queue: RichSaveQueue;
  flush: () => Promise<RichProjectResponse>;
  cells: (response: RichProjectResponse) => ReadonlyMap<string, CellValue>;
  preview: (batch: AgentEditBatch) => Promise<RichProjectResponse>;
  enter: () => void;
  leave: () => void;
  retainImages: () => Promise<void>;
  fence: (receipt: AgentEditReceipt | null) => void;
};
export type PreparedApi = {
  claim: (batchId: string) => Promise<AgentClaimResult>;
  commit: (claim: AgentClaimResult) => Promise<AgentCommitResult>;
  recover: (batchId: string) => Promise<AgentCommitResult | null>;
  report: (receipt: AgentEditReceipt) => Promise<void>;
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

  private async perform(batchId: string, api: PreparedApi): Promise<void> {
    const editor = this.editor;
    let claim: AgentClaimResult | null = null, reservation: HistoryReservation | null = null;
    let commitStarted = false, saved: AgentEditReceipt | null = null, fenced = false;
    try {
      await editor.flush();
      if (this.closed) return;
      claim = await api.claim(batchId);
      const batch = claim.batch;
      if (batch.id !== batchId || batch.mutation.capture.sessionId !== editor.history.session
        || batch.mutation.projectId !== editor.queue.baseline.workspace.projectId) throw new Error("AGENT_OWNER_MISMATCH");
      await editor.flush();
      if (this.closed) throw new Error("AGENT_CANCELLED");
      reservation = editor.history.reserve(batch.mutation.actionId);
      if (!reservation) throw new Error("AGENT_STALE_READ");
      editor.queue.beginPrepared(batch.id);
      editor.enter();
      const before = editor.cells(editor.queue.baseline);
      const preview = await editor.preview(batch);
      if (preview.workspace.projectRevision !== editor.queue.baseline.workspace.projectRevision + 1
        || preview.workspace.documentRevision !== editor.queue.baseline.workspace.documentRevision + 1) throw new Error("AGENT_STALE_READ");
      const proposed = cellChanges(before, editor.cells(preview));
      if (!editor.history.reserved(reservation) || proposed.some(change => editor.history.read(change.key) !== change.before)) throw new Error("AGENT_STALE_READ");
      if (this.closed) throw new Error("AGENT_CANCELLED");
      commitStarted = true;
      let result: AgentCommitResult | null;
      try { result = await api.commit(claim); }
      catch { result = await api.recover(batch.id).catch(() => null); }
      if (!result || !matches(result.receipt, batch) || result.receipt.disposition === "outcome_unknown") throw new Error("AGENT_OUTCOME_UNKNOWN");
      if (!result.receipt.durable) {
        this.completed.add(batch.id);
        return;
      }
      saved = result.receipt;
      const changes = cellChanges(before, editor.cells(result.project));
      const proof = result.project.workspace.mutationReplay.find(item => item.clientMutationId === batch.mutation.clientMutationId);
      if (this.closed || result.project.durability !== "durable" || result.project.workspace.projectRevision !== saved.projectRevision
        || result.project.workspace.documentRevision !== saved.documentRevision || proof?.requestSha256 !== batch.requestSha256
        || proof.resultingRevision !== saved.projectRevision || JSON.stringify(changes) !== JSON.stringify(proposed)) throw new Error("AGENT_OUTCOME_UNKNOWN");
      editor.queue.adoptPrepared(batch.id, result.project);
      if (!editor.history.publish(reservation, changes)) throw new Error("AGENT_OUTCOME_UNKNOWN");
      reservation = null;
      await editor.retainImages();
      this.completed.add(batch.id);
      await api.report(saved).catch(() => {});
    } catch (error) {
      if (commitStarted) {
        fenced = true;
        editor.queue.fencePrepared();
        editor.history.close();
        editor.fence(saved);
      } else if (claim) {
        await api.report(rejected(claim.batch)).catch(() => {});
        this.completed.add(claim.batch.id);
      }
      throw error;
    } finally {
      if (reservation && !fenced) editor.history.discard(reservation);
      if (claim && !fenced) editor.queue.endPrepared(claim.batch.id);
      if (!fenced) editor.leave();
    }
  }

  close(): void { this.closed = true; }
}
