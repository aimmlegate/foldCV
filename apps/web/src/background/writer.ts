import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { WriterAdvanceV1 } from "../contracts/generated/background_writer_advance_v1";
import type { AgentEditBatch } from "../contracts/generated/agent_edit_batch";
import type { AssistantHistoryOfferV1 } from "../contracts/generated/assistant_history_offer_v1";
import type { WriterViewV1 } from "../contracts/generated/background_writer_view_v1";
import type { WriterProofV1 } from "../contracts/generated/background_writer_proof_v1";
import { validateBackgroundShape } from "../contracts/background-validate";
import { RichApiFailure } from "../rich/api";
import type { WriterHistoryRequestV1 } from "../contracts/generated/background_writer_history_request_v1";
import type { DraftPayloadV1 } from "../contracts/generated/background_draft_payload_v1";
import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";
import type { ProposalBindingV1 } from "../contracts/generated/background_proposal_v1";
import type { UndoOwnershipV1 } from "../contracts/generated/background_undo_v1";
import { documentSteps, factSteps, type RichSaveQueue } from "../rich/save-queue";
import { cellChanges, type CellValue, type HistoryReservation, type SessionHistory } from "../rich/history";
import { retainResume, type AttachedWriter } from "./connection";
import { sha256, sameValue, containsSubmitted } from "./wire";
import type { LocalDraft } from "./drafts";
import { timers, WriterLifecycle, type WriterMode, type WriterObserver, type WriterTimers } from "./writer-lifecycle";

export type { WriterMode, WriterObserver, WriterTimers };

export type EditorSnapshot = { document: RichDocumentV1; facts: WorkingFacts; assets: { id: string; sha256: string }[] };
export type WriterEditorPort = { queue: RichSaveQueue; history: SessionHistory; snapshot: () => EditorSnapshot;
  cells: (response: RichProjectResponse) => ReadonlyMap<string, CellValue>; flushLocal: () => Promise<void>;
  compositionEnd: () => Promise<void>; lock: (locked: boolean) => void; changed: (mode: WriterMode, error: string | null) => void;
  saved: (job: JobSnapshotV1) => void; applyHistory: (direction: "undo" | "redo") => boolean };
type Touch = NonNullable<WriterAdvanceV1["touches"]>[number];

/** Canonical replies only advance proof; accepted local input has its own durable buffer. */
export class BackgroundWriter extends WriterLifecycle {
  cursor: number;
  private sequence: number;
  private touches: Touch[] = [];
  private outbox: RichMutation[] = [];
  private historyOutbox: NonNullable<DraftPayloadV1["historyOutbox"]> = [];
  private local: LocalDraft | null;
  private last: EditorSnapshot;
  private durableCursor = -1;
  private readonly completed = new Set<string>();
  private readonly expiredHistory = new Set<string>();
  private readonly actions = new Map<string, { job: string; proposal: string; transfer: string }>();
  private readonly writes = new Set<Promise<void>>();
  private readonly reservations = new Set<HistoryReservation>();
  private flushingInput = false;
  private capacityLocked = false;
  private checkpoints: Promise<void> = Promise.resolve();
  private heartbeatProof: WriterProofV1 | null = null;
  private recoveryJob: { job: JobSnapshotV1; proposal: ProposalBindingV1; cursor: number } | null = null;

  constructor(readonly connection: AttachedWriter, private readonly editor: WriterEditorPort, time = timers,
    observe: WriterObserver = () => Promise.resolve()) {
    super(time, observe);
    this.local = connection.local?.record ?? null;
    this.cursor = this.local?.cursor ?? connection.view.writer.acknowledgedCursor;
    this.sequence = Math.max(this.local?.sequence ?? 0, connection.view.writer.draftSequenceFloor ?? 0);
    this.durableCursor = this.local?.cursor ?? connection.view.writer.acknowledgedCursor;
    this.last = editor.snapshot();
    if (connection.local) {
      this.touches = connection.local.payload.touches ?? [];
      this.outbox = connection.local.payload.outbox;
      this.historyOutbox = connection.local.payload.historyOutbox ?? [];
      this.durableCursor = this.local?.cursor ?? -1;
    }
    this.mode = !connection.proof ? "read_only" : connection.view.writer.status === "attached" && !connection.local ? "normal" : "recovering";
    this.editor.changed(this.mode, connection.error);
  }

  get writable(): boolean { return ["normal", "recovering"].includes(this.mode) && this.touches.length < 100 && this.outbox.length + this.historyOutbox.length < 100; }
  get needsUnloadGuard(): boolean { return this.durableCursor < this.cursor && this.mode !== "detached" && this.mode !== "closed"; }
  get retainsDraft(): boolean { return this.local !== null || this.writes.size > 0 || this.outbox.length > 0
    || this.historyOutbox.length > 0 || this.cursor > this.view.writer.acknowledgedCursor; }
  get proof() { const proof = this.connection.proof; if (!proof) throw new Error("WRITER_READ_ONLY"); return proof; }
  get view(): WriterViewV1 { return this.connection.view; }
  private header(): WriterAdvanceV1 {
    return { schemaVersion: 1, proof: this.proof, canonicalRevision: this.view.response.workspace.projectRevision,
      canonicalSha256: this.view.workspaceSha256, actionCursor: this.cursor, touches: structuredClone(this.touches) };
  }
  historyTarget(direction: "undo" | "redo"): AssistantHistoryOfferV1["undoBackend"] {
    const action = this.editor.history.actionFor(direction), owned = action ? this.actions.get(action) : null;
    if (!owned) return null;
    const inverse = this.view.inverses?.find(item => item.jobId === owned.job && item.proposalId === owned.proposal);
    return inverse?.direction === direction ? { schemaVersion: 1, protocolVersion: 1, jobId: owned.job,
      proposalId: owned.proposal, transferId: inverse.transferId } : null;
  }
  async reviewedAuthority(batch?: AgentEditBatch): Promise<WriterAdvanceV1> {
    if (!this.writable || this.mode !== "normal") throw new Error("WRITER_RECOVERY_REQUIRED");
    await this.flushTouches();
    if (batch?.mutation.kind === "undo" || batch?.mutation.kind === "redo") {
      if (this.editor.history.actionFor(batch.mutation.kind) !== batch.mutation.actionId) throw new Error("DEPENDENCY_CHANGED");
      const target = this.historyTarget(batch.mutation.kind);
      if (target) {
        const request = { ...this.header(), jobId: target.jobId, proposalId: target.proposalId, transferId: target.transferId };
        await this.connection.api.begin(request);
        await this.connection.api.acknowledge(request);
      }
    }
    return this.header();
  }
  async adoptReviewed(revision: number): Promise<void> {
    const view = await this.connection.api.read(this.proof);
    if (view.response.workspace.projectRevision !== revision) throw new Error("OUTCOME_UNKNOWN");
    this.acknowledge(view);
    this.last = structuredClone(this.editor.snapshot());
    await this.clearCleanDraft();
  }
  // Kept in this file: NB-G03 mutation evidence removes exactly this guard from the V1 writer source.
  protected override current(ticket: number): void { if (ticket !== this.operation || this.mode !== "protected") throw new Error("WRITER_STALE_CALLBACK"); }
  protected notify(mode: WriterMode, error: string | null): void { this.editor.changed(mode, error); }
  protected lockInput(locked: boolean): void { this.editor.lock(locked); }
  protected compositionDone(): Promise<void> { return this.editor.compositionEnd(); }
  private acknowledge(view: WriterViewV1): void {
    const proof = this.proof;
    if (view.writer.lineage !== proof.lineage || view.writer.epoch !== proof.epoch || view.writer.incarnation !== proof.incarnation
      || view.response.workspace.projectId !== this.connection.api.project || !view.canonicalReady) throw new Error("WRITER_UNKNOWN");
    if (view.response.workspace.projectRevision < this.view.response.workspace.projectRevision) return;
    if (view.response.workspace.projectRevision === this.view.response.workspace.projectRevision
      && (view.writer.acknowledgedCursor < this.view.writer.acknowledgedCursor || view.writer.touchGeneration < this.view.writer.touchGeneration
        || view.writer.barrierGeneration < this.view.writer.barrierGeneration)) return;
    this.connection.view = view;
    this.touches = this.touches.filter(touch => touch.cursor > view.writer.acknowledgedCursor);
    if (this.capacityLocked && this.mode === "normal" && this.touches.length < 100) {
      this.capacityLocked = false; this.editor.lock(false);
    }
    retainResume(this.connection.api.project, proof, view, this.cursor, this.retainsDraft ? this.sequence : 0);
  }
  private observeSnapshot(view: WriterViewV1, basis: WriterViewV1): boolean {
    if (this.view !== basis && view.workspaceSha256 !== this.view.workspaceSha256
      || view.response.workspace.projectRevision < this.view.response.workspace.projectRevision) return false;
    if (!view.canonicalReady) throw new Error("OUTCOME_UNKNOWN");
    if (view.workspaceSha256 !== this.view.workspaceSha256) {
      const before = this.view.response.workspace.project, after = view.response.workspace.project;
      if (!before || !after || !sameValue(before.document, after.document) || !sameValue(before.facts, after.facts))
        throw new Error("WRITER_RECOVERY_REQUIRED");
      this.editor.queue.refreshMetadata(view.response);
    }
    this.acknowledge(view); return true;
  }
  input(kind: RichMutation["kind"]): void {
    if (!this.writable) throw new Error("WRITER_INPUT_BLOCKED");
    const next = this.editor.snapshot(), steps = [...documentSteps(this.last.document, next.document), ...factSteps(this.last.facts, next.facts)];
    this.cursor++;
    const [first, ...rest] = steps;
    const mutation: RichMutation | null = first ? { schemaVersion: 1, projectId: this.connection.api.project,
      clientMutationId: crypto.randomUUID(), actionId: `${this.proof.sessionId}:${this.cursor}`, kind,
      capture: { sessionId: this.proof.sessionId, actionId: `${this.proof.sessionId}:${this.cursor}`, actionToken: 0, dependencies: [] }, steps: [first, ...rest] } : null;
    this.touches.push({ cursor: this.cursor, mutation }); this.last = next;
    this.retain().catch(error => this.editor.changed(this.mode, error instanceof Error ? error.message : "DRAFT_STORAGE_FAILED"));
    if (this.touches.length >= 100) {
      this.capacityLocked = true; this.editor.lock(true);
      this.editor.changed(this.mode, this.mode === "recovering" ? "Черновик заполнен. Восстановите его, чтобы продолжить ввод."
        : "Дождитесь сохранения, чтобы продолжить ввод. Уже введённый текст остаётся в редакторе.");
    }
    if (this.mode === "normal" && this.touches.length >= 80 && !this.flushingInput) {
      this.flushingInput = true;
      queueMicrotask(() => {
        void (async () => {
          if (this.mode !== "normal") return;
          await this.editor.flushLocal();
          if (this.mode === "normal") await this.flushTouches();
        })().catch(error => this.enterRecovery(error)).finally(() => { this.flushingInput = false; });
      });
    }
  }
  private payload(snapshot: EditorSnapshot): DraftPayloadV1 {
    const ids = new Set<string>();
    const collect = (value: unknown): void => {
      if (Array.isArray(value)) value.forEach(collect);
      else if (typeof value === "object" && value !== null) {
        if ("assetId" in value && typeof value.assetId === "string") ids.add(value.assetId);
        Object.values(value).forEach(collect);
      }
    };
    collect([snapshot.document, this.outbox, this.touches]);
    return { schemaVersion: 1, document: snapshot.document, facts: snapshot.facts, assetPins: [...ids],
      outbox: structuredClone(this.outbox), historyOutbox: structuredClone(this.historyOutbox), touches: structuredClone(this.touches) };
  }
  private retain(): Promise<void> {
    const snapshot = structuredClone(this.editor.snapshot()), payload = this.payload(snapshot), payloadWire = JSON.stringify(payload);
    const sequence = ++this.sequence, cursor = this.cursor, proof = this.proof;
    const fields = { schemaVersion: 1 as const, project: this.connection.api.project, lineage: proof.lineage, epoch: proof.epoch, incarnation: proof.incarnation,
      id: this.local?.id ?? `draft_${proof.epoch}_${proof.sessionId}`, sequence, cursor, baseRevision: this.view.response.workspace.projectRevision,
      baseSha256: this.view.workspaceSha256, payloadWire, assets: snapshot.assets.filter(asset => payload.assetPins.includes(asset.id)) };
    try { retainResume(fields.project, proof, this.view, cursor, sequence); }
    catch (error) { return Promise.reject(error); }
    const work = (async () => {
      const result = await this.connection.repository.write({ ...fields, payloadSha256: await sha256(payloadWire) });
      if (this.connection.proof !== proof) return;
      if (!this.local || result.sequence >= this.local.sequence) this.local = result;
      this.durableCursor = Math.max(this.durableCursor, result.cursor);
    })();
    this.writes.add(work); void work.finally(() => this.writes.delete(work)).catch(() => {});
    return work;
  }
  private async clearCleanDraft(): Promise<void> {
    if (this.cursor !== this.view.writer.acknowledgedCursor || this.outbox.length || this.historyOutbox.length || this.touches.length) return;
    const snapshot = this.editor.snapshot(), project = this.view.response.workspace.project;
    if (!project || documentSteps(project.document, snapshot.document).length || factSteps(project.facts, snapshot.facts).length) return;
    const ticket = this.cursor;
    await Promise.all([...this.writes]);
    if (ticket !== this.cursor || this.outbox.length || this.historyOutbox.length || !this.local) return;
    const record = this.local;
    await this.connection.repository.remove(record);
    if (this.local?.sequence === record.sequence) this.local = null;
    this.durableCursor = Math.max(this.durableCursor, ticket);
    retainResume(this.connection.api.project, this.proof, this.view, this.cursor, this.local?.sequence ?? 0);
  }
  async save(mutation: RichMutation): Promise<RichProjectResponse> {
    if (!["normal", "protected"].includes(this.mode)) throw new Error("WRITER_RECOVERY_REQUIRED");
    const proof = this.proof;
    if (!this.outbox.some(item => item.clientMutationId === mutation.clientMutationId)) this.outbox.push(structuredClone(mutation));
    try {
      await this.retain();
      if (this.connection.proof !== proof) throw new Error("WRITER_STALE_CALLBACK");
      // Metadata may advance the snapshot before the writer acknowledges it.
      const view = await this.connection.api.save({ ...this.header(), canonicalRevision: this.view.writer.acknowledgedRevision,
        canonicalSha256: this.view.writer.acknowledgedSha256 ?? this.view.workspaceSha256, mutation });
      if (!view.mutationWire || !containsSubmitted(mutation, JSON.parse(view.mutationWire))) throw new Error("INVALID_RESULT");
      if (this.connection.proof !== proof || !["normal", "protected"].includes(this.mode)) throw new Error("WRITER_STALE_CALLBACK");
      this.acknowledge(view); this.outbox = this.outbox.filter(item => item.clientMutationId !== mutation.clientMutationId);
      await this.clearCleanDraft(); return view.response;
    } catch (error) { if (this.connection.proof === proof) this.enterRecovery(error); throw error; }
  }
  async flushTouches(): Promise<void> {
    const proof = this.proof;
    let result: WriterViewV1;
    try { result = await this.connection.api.flush(this.header()); }
    catch (error) {
      if (!(error instanceof RichApiFailure) || error.code !== "WRITER_UNKNOWN") throw error;
      const basis = this.view, observed = await this.connection.api.read(proof);
      if (this.connection.proof !== proof || !["normal", "protected"].includes(this.mode)) return;
      if (observed.workspaceSha256 === basis.workspaceSha256) throw error;
      this.observeSnapshot(observed, basis);
      result = await this.connection.api.flush(this.header());
    }
    if (this.connection.proof !== proof) return;
    if (!["normal", "protected"].includes(this.mode)) return;
    this.acknowledge(result); await this.observe("touch_watermark_durable"); await this.clearCleanDraft();
  }
  protected enterRecovery(error: unknown): void {
    if (["closed", "detached", "read_only"].includes(this.mode)) return;
    ++this.operation; this.editor.queue.fencePrepared();
    for (const reservation of this.reservations) this.editor.history.discard(reservation);
    this.reservations.clear(); this.editor.lock(false);
    this.setMode("recovering", error instanceof Error ? error.message : "WRITER_RECOVERY_REQUIRED");
    void this.retain().catch(() => {});
  }
  checkpoint(): Promise<void> {
    const proof = this.connection.proof;
    const task = this.checkpoints.catch(() => {}).then(async () => {
      if (!proof || this.connection.proof !== proof) throw new Error("WRITER_STALE_CALLBACK");
      await this.retain();
      const local = this.local;
      if (!local) throw new Error("DRAFT_STORAGE_FAILED");
      if (this.connection.proof !== proof || local.epoch !== proof.epoch || local.incarnation !== proof.incarnation) throw new Error("WRITER_STALE_CALLBACK");
      const payload: unknown = JSON.parse(local.payloadWire);
      if (!isDraftPayload(payload)) throw new Error("DRAFT_CORRUPT");
      await this.connection.api.checkpoint({ schemaVersion: 1, proof, id: local.id, sequence: local.sequence,
        actionCursor: local.cursor, baseRevision: local.baseRevision, baseSha256: local.baseSha256, payload });
      await this.observe("draft_checkpointed");
    });
    this.checkpoints = task; return task;
  }
  async heartbeat(): Promise<void> {
    if (["closed", "detached", "read_only", "protected"].includes(this.mode)) return;
    const proof = this.proof, basis = this.view;
    if (this.heartbeatProof === proof) return;
    this.heartbeatProof = proof;
    try {
      const view = await this.connection.api.heartbeat(proof);
      if (this.connection.proof !== proof) return;
      if (["closed", "detached", "protected"].includes(this.mode)) return;
      if (!view.canonicalReady) throw new Error("OUTCOME_UNKNOWN");
      if (this.mode !== "normal" || this.outbox.length || this.historyOutbox.length) return;
      this.observeSnapshot(view, basis);
    } catch (error) {
      if (this.connection.proof !== proof) return;
      if (error instanceof RichApiFailure && error.code === "WRITER_UNKNOWN" && this.mode === "normal" && !this.retainsDraft) {
        try { await this.reconnectClean(proof); }
        catch (resumeError) { if (this.mode === "normal" || this.mode === "protected") this.enterRecovery(resumeError); }
      } else this.enterRecovery(error);
    } finally { if (this.heartbeatProof === proof) this.heartbeatProof = null; }
  }
  private reconnectClean(proof: WriterProofV1): Promise<void> {
    return this.bounded(async ticket => {
      this.current(ticket);
      if (this.connection.proof !== proof || this.retainsDraft) throw new Error("WRITER_RECOVERY_REQUIRED");
      const current = await this.connection.api.bootstrap(); this.current(ticket);
      if (!current.canonicalReady || current.writer.lineage !== proof.lineage) throw new Error("OUTCOME_UNKNOWN");
      const next = await this.connection.api.open({ schemaVersion: 1, sessionId: proof.sessionId, incarnation: crypto.randomUUID(),
        credential: proof.credential, previousEpoch: proof.epoch, previousIncarnation: proof.incarnation,
        canonicalRevision: current.response.workspace.projectRevision, canonicalSha256: current.workspaceSha256,
        actionCursor: this.cursor, draftSequence: 0 });
      this.current(ticket);
      if (!next.canonicalReady || next.writer.lineage !== proof.lineage) throw new Error("OUTCOME_UNKNOWN");
      this.connection.proof = { ...proof, epoch: next.writer.epoch, incarnation: next.writer.incarnation };
      this.connection.view = next;
      if (next.writer.status !== "attached") throw new Error("WRITER_RECOVERY_REQUIRED");
      this.cursor = next.writer.acknowledgedCursor; this.durableCursor = this.cursor;
      this.sequence = next.writer.draftSequenceFloor ?? 0; this.touches = [];
      const key = `resume:${next.writer.incarnation}`;
      this.editor.queue.beginPrepared(key);
      const changes = cellChanges(this.editor.cells(this.editor.queue.baseline), this.editor.cells(next.response));
      this.editor.queue.adoptPrepared(key, next.response);
      if (!this.editor.history.reconcile(changes)) throw new Error("WRITER_RECOVERY_REQUIRED");
      this.editor.queue.endPrepared(key); this.last = this.editor.snapshot();
      retainResume(this.connection.api.project, this.proof, next, this.cursor, 0);
      await this.observe("writer_resumed"); this.current(ticket);
    });
  }
  private historyRequest(job: JobSnapshotV1, owner: UndoOwnershipV1): WriterHistoryRequestV1 {
    if (!job.proposalId) throw new Error("INVALID_RESULT");
    return { ...this.header(), jobId: job.id, proposalId: job.proposalId, transferId: owner.transferId };
  }
  private async adopt(job: JobSnapshotV1, ticket: number, key: string, recovered = false): Promise<void> {
    this.current(ticket);
    const owner = this.view.inverses?.find(item => item.jobId === job.id && item.proposalId === job.proposalId && item.direction === "undo");
    if (this.completed.has(job.id)) return;
    if (!owner) throw new Error(job.undoExpired ? "REQUEST_EXPIRED" : "OUTCOME_UNKNOWN");
    const offer = await this.connection.api.offer(this.historyRequest(job, owner)); this.current(ticket);
    if (offer.job.id !== job.id || offer.job.proposalId !== job.proposalId || !job.receipt || !sameValue(offer.job.receipt, job.receipt)
      || offer.view.response.workspace.projectRevision < this.editor.queue.baseline.workspace.projectRevision) throw new Error("INVALID_RESULT");
    const response = offer.view.response, cells = this.editor.cells(response), inverse = cellChanges(cells, this.editor.cells(offer.preview));
    const changes = inverse.map(change => ({ key: change.key, before: change.after, after: change.before }));
    const mounted = cellChanges(this.editor.cells(this.editor.queue.baseline), cells);
    if (mounted.length && !sameValue(mounted, changes)) throw new Error("WRITER_RECOVERY_REQUIRED");
    const reservation = this.editor.history.reserve(`background:${job.id}:${job.proposalId}`);
    if (!reservation) return;
    this.reservations.add(reservation);
    try {
      await this.observe("adoption_started"); this.current(ticket);
      const request = { ...this.historyRequest(job, owner), canonicalRevision: response.workspace.projectRevision, canonicalSha256: offer.view.workspaceSha256 };
      await this.connection.api.begin(request); this.current(ticket);
      const ownership = await this.connection.api.acknowledge(request); this.current(ticket);
      if (ownership.owner !== "session" || ownership.transferId !== owner.transferId || ownership.writerEpoch !== this.proof.epoch
        || ownership.incarnation !== this.proof.incarnation) throw new Error("WRITER_UNKNOWN");
      this.acknowledge(await this.connection.api.read(this.proof)); this.current(ticket);
      if (recovered) this.editor.queue.recoverPrepared(key);
      this.editor.queue.adoptPrepared(key, response);
      const applied = mounted.length ? this.editor.history.publish(reservation, mounted) : this.editor.history.adoptExisting(reservation, changes);
      if (!applied) throw new Error("WRITER_RECOVERY_REQUIRED");
      this.actions.set(reservation.actionId, { job: job.id, proposal: job.proposalId ?? "", transfer: owner.transferId });
      this.completed.add(job.id); this.last = this.editor.snapshot(); this.editor.saved(job);
    } finally { this.editor.history.discard(reservation); this.reservations.delete(reservation); }
  }
  async publish(job: JobSnapshotV1, proposal: ProposalBindingV1, approve = false): Promise<void> {
    if (this.active) await this.active.catch(() => {});
    if (this.completed.has(job.id) || this.mode !== "normal") return;
    if (job.submission.identity.projectId !== this.connection.api.project || job.submission.identity.lineage !== this.proof.lineage
      || job.id !== proposal.jobId || job.proposalId !== proposal.id) throw new Error("INVALID_RESULT");
    const key = `publication:${job.id}`;
    let declined = false;
    let command: { schemaVersion: 1; proof: WriterProofV1; generation: number; token: string } | null = null;
    try {
      await this.bounded(async ticket => {
        await this.observe("local_barrier_acquired"); this.current(ticket);
        await this.observe("final_flush_started"); this.current(ticket);
        await this.editor.flushLocal(); this.current(ticket);
        await this.flushTouches(); this.current(ticket);
        this.editor.queue.beginPrepared(key);
        command = { schemaVersion: 1, proof: this.proof, generation: this.view.writer.barrierGeneration + 1, token: crypto.randomUUID() + crypto.randomUUID() };
        this.recoveryJob = { job, proposal, cursor: this.cursor };
        const barrier = await this.connection.api.barrier({ ...this.header(), ...command, touchGeneration: this.view.writer.touchGeneration }); this.current(ticket);
        await this.observe("barrier_acked"); this.current(ticket);
        if (barrier.generation !== command.generation || barrier.token !== command.token || barrier.actionCursor !== this.cursor) throw new Error("INVALID_RESULT");
        const result = await this.connection.api.publish({ ...command, jobId: job.id, proposalSha256: proposal.payloadSha256, ...(approve ? { approve: true } : {}) }); this.current(ticket);
        if (result.job.id !== job.id || result.job.proposalId !== proposal.id
          || result.job.receipt && result.job.receipt.proposalSha256 !== proposal.payloadSha256) throw new Error("INVALID_RESULT");
        this.acknowledge(result.view);
        if (result.job.receipt) await this.adopt(result.job, ticket, key);
        else await this.connection.api.revoke(command);
        this.current(ticket); this.editor.queue.endPrepared(key); this.recoveryJob = null;
        declined = approve && !result.job.receipt && result.job.publication !== "no_change";
      });
    } catch (error) {
      if (command) void this.connection.api.revoke(command).catch(() => {});
      void this.checkpoint().catch(() => {});
      throw error;
    }
    if (declined) throw new Error("Результат устарел. Запросите правку заново.");
  }
  async adoptHeadless(job: JobSnapshotV1): Promise<void> {
    if (this.active) await this.active.catch(() => {});
    if (this.completed.has(job.id) || this.mode !== "normal" || !job.receipt) return;
    if (job.submission.identity.projectId !== this.connection.api.project || job.submission.identity.lineage !== this.proof.lineage) throw new Error("INVALID_RESULT");
    const key = `headless:${job.id}`;
    await this.bounded(async ticket => {
      await this.editor.flushLocal(); this.current(ticket); await this.flushTouches(); this.current(ticket);
      this.editor.queue.beginPrepared(key);
      try { await this.adopt(job, ticket, key); }
      catch (error) {
        if (!(error instanceof RichApiFailure) || !["DEPENDENCY_CHANGED", "REQUEST_EXPIRED"].includes(error.code)) throw error;
        this.current(ticket); this.completed.add(job.id);
        this.editor.changed(this.mode, "Эта правка сохранена, но её история больше не подходит к текущему документу.");
      }
      this.current(ticket); this.editor.queue.endPrepared(key);
    });
  }
  async recoverPublication(job: JobSnapshotV1): Promise<void> {
    const pending = this.recoveryJob;
    if (this.mode !== "recovering" || !pending || pending.job.id !== job.id || this.cursor !== pending.cursor
      || !job.receipt || job.receipt.proposalSha256 !== pending.proposal.payloadSha256 || this.outbox.length || this.historyOutbox.length) return;
    await Promise.all([...this.writes]);
    await this.checkpoints.catch(() => {});
    const view = await this.connection.api.bootstrap();
    if (this.mode !== "recovering" || this.cursor !== pending.cursor || !view.canonicalReady) return;
    this.acknowledge(view);
    const owner = view.inverses?.find(item => item.jobId === job.id && item.proposalId === job.proposalId);
    if (!owner) return;
    const offer = await this.connection.api.offer(this.historyRequest(job, owner));
    if (this.mode !== "recovering" || this.cursor !== pending.cursor || !sameValue(offer.job.receipt, job.receipt)) return;
    const record = view.drafts.find(item => item.id === view.writer.draftId);
    const next = record ? await this.connection.api.discard({ schemaVersion: 1, proof: this.proof, id: record.id,
      sequence: record.sequence, payloadSha256: record.payloadSha256, canonicalRevision: view.response.workspace.projectRevision,
      canonicalSha256: view.workspaceSha256 }) : await this.connection.api.reconcile(this.header());
    if (this.cursor !== pending.cursor) return;
    this.acknowledge(next); this.setMode("normal");
    const key = `recovered:${job.id}`;
    await this.bounded(async ticket => {
      await this.adopt(job, ticket, key, true); this.current(ticket); this.editor.queue.endPrepared(key);
      this.recoveryJob = null; await this.clearCleanDraft();
    });
  }
  async navigate(): Promise<void> {
    if (this.active) await this.active.catch(() => {});
    if (this.mode === "read_only" || this.mode === "detached") return;
    if (this.mode === "recovering") { await this.retainForNavigation(); return; }
    try {
      await this.bounded(async ticket => {
        await this.editor.flushLocal(); this.current(ticket); await this.flushTouches(); this.current(ticket);
        const view = await this.connection.api.detach(this.header()); this.current(ticket);
        this.acknowledge(view); this.setMode("detached"); this.editor.lock(true); this.durableCursor = this.cursor;
        await this.observe("clean_detach_acked");
      });
    } catch { await this.retainForNavigation(); }
  }
  private async retainForNavigation(): Promise<void> {
    await this.retain();
    void this.checkpoint().catch(error => {
      if (this.mode !== "closed") this.editor.changed(this.mode, error instanceof Error ? error.message : "DRAFT_CHECKPOINT_UNCONFIRMED");
    });
  }
  async resume(): Promise<void> {
    if (this.mode !== "detached") return;
    const current = await this.connection.api.bootstrap(), old = this.proof;
    const next = await this.connection.api.open({ schemaVersion: 1, sessionId: old.sessionId, incarnation: crypto.randomUUID(),
      credential: old.credential, previousEpoch: old.epoch, previousIncarnation: old.incarnation,
      canonicalRevision: current.response.workspace.projectRevision, canonicalSha256: current.workspaceSha256, actionCursor: 0, draftSequence: 0 });
    this.connection.proof = { ...old, epoch: next.writer.epoch, incarnation: next.writer.incarnation };
    this.connection.view = next; this.cursor = next.writer.acknowledgedCursor;
    this.durableCursor = this.cursor;
    this.sequence = next.writer.draftSequenceFloor ?? 0; this.touches = [];
    this.setMode("protected");
    const key = `resume:${next.writer.epoch}`;
    try {
      this.editor.queue.beginPrepared(key);
      const changes = cellChanges(this.editor.cells(this.editor.queue.baseline), this.editor.cells(next.response));
      this.editor.queue.adoptPrepared(key, next.response);
      if (!this.editor.history.reconcile(changes)) throw new Error("WRITER_RECOVERY_REQUIRED");
      this.editor.queue.endPrepared(key); this.last = this.editor.snapshot();
      retainResume(this.connection.api.project, this.proof, next, this.cursor, 0);
      await this.observe("writer_resumed");
      this.setMode("normal"); this.editor.lock(false);
    } catch (error) { this.enterRecovery(error); throw error; }
  }
  async history(direction: "undo" | "redo"): Promise<boolean> {
    const action = this.editor.history.actionFor(direction), owned = action ? this.actions.get(action) : null;
    if (!owned) return false;
    if (this.expiredHistory.has(owned.job)) {
      this.editor.changed(this.mode, "Срок отмены этой правки истёк. Сохранённый текст остаётся в резюме.");
      return true;
    }
    await this.bounded(async ticket => {
      await this.editor.flushLocal(); this.current(ticket);
      const owner = this.view.inverses?.find(item => item.jobId === owned.job && item.proposalId === owned.proposal);
      if (!owner || owner.direction !== direction) throw new Error("DEPENDENCY_CHANGED");
      if (owner.owner !== "session" || owner.writerEpoch !== this.proof.epoch || owner.incarnation !== this.proof.incarnation) {
        const request = { ...this.header(), jobId: owned.job, proposalId: owned.proposal, transferId: owner.transferId };
        await this.connection.api.begin(request); this.current(ticket);
        await this.connection.api.acknowledge(request); this.current(ticket);
        owned.transfer = owner.transferId;
      }
      this.cursor++;
      const pending = { jobId: owned.job, proposalId: owned.proposal, transferId: owned.transfer,
        commandId: crypto.randomUUID(), direction, actionCursor: this.cursor };
      this.touches.push({ cursor: this.cursor, mutation: null }); this.historyOutbox.push(pending);
      await this.retain(); this.current(ticket);
      const key = `history:${pending.commandId}`; this.editor.queue.beginPrepared(key);
      const result = await this.connection.api.history({ ...this.header(), ...pending }); this.current(ticket);
      if (result.receipt.commandId !== pending.commandId || result.receipt.jobId !== owned.job) throw new Error("INVALID_RESULT");
      this.acknowledge(result.view); this.editor.queue.adoptPrepared(key, result.view.response);
      const moved = this.editor.applyHistory(direction);
      if (!moved) throw new Error("WRITER_RECOVERY_REQUIRED");
      this.historyOutbox = this.historyOutbox.filter(item => item.commandId !== pending.commandId);
      this.editor.queue.endPrepared(key); this.last = this.editor.snapshot(); await this.clearCleanDraft();
    });
    return true;
  }
  observeJob(job: JobSnapshotV1): void {
    if (job.submission.identity.projectId !== this.connection.api.project || job.submission.identity.lineage !== this.view.writer.lineage) return;
    if (job.undoExpired) this.expiredHistory.add(job.id);
  }
  async resolveDraft(choice: "saved" | "draft"): Promise<RichProjectResponse> {
    if (!["recovering", "read_only"].includes(this.mode)) throw new Error("WRITER_RECOVERY_REQUIRED");
    this.setMode("protected"); this.editor.lock(true);
    try {
      try { return await this.resolveChosenDraft(choice); }
      catch (error) {
        if (!(error instanceof RichApiFailure) || error.code !== "WRITER_UNKNOWN" || !this.connection.proof
          || choice === "draft" && !this.local) throw error;
        this.connection.proof = null;
        return await this.resolveChosenDraft(choice);
      }
    }
    catch (error) {
      this.setMode(this.connection.proof ? "recovering" : "read_only", error instanceof Error ? error.message : "DRAFT_RECOVERY_FAILED");
      this.editor.lock(!this.connection.proof); throw error;
    }
  }
  private async resolveChosenDraft(choice: "saved" | "draft"): Promise<RichProjectResponse> {
    let resolveCurrent = this.connection.proof !== null;
    let superseded: WriterViewV1["drafts"] = [];
    if (!this.connection.proof || this.local && (this.local.epoch !== this.connection.proof.epoch || this.local.incarnation !== this.connection.proof.incarnation)) {
      if (choice === "draft" && !this.local) throw new Error("DRAFT_CORRUPT");
      const view = await this.connection.api.bootstrap(), credential = crypto.randomUUID() + crypto.randomUUID();
      const next = await this.connection.api.abandon({ schemaVersion: 1, sessionId: crypto.randomUUID(), incarnation: crypto.randomUUID(),
        credential, canonicalRevision: view.response.workspace.projectRevision, canonicalSha256: view.workspaceSha256,
        discardDrafts: choice === "saved" ? view.drafts.map(item => item.id) : [] });
      this.connection.proof = { schemaVersion: 1, lineage: next.writer.lineage, epoch: next.writer.epoch,
        sessionId: next.writer.sessionId, incarnation: next.writer.incarnation, credential };
      this.connection.view = next;
      resolveCurrent = choice === "draft";
      if (choice === "saved") { await this.connection.repository.discardProject(this.connection.api.project); this.local = null; }
      else {
        const previous = this.local; if (!previous) throw new Error("DRAFT_CORRUPT");
        this.cursor = 0; this.touches = []; this.outbox = []; this.historyOutbox = [];
        const snapshot = this.editor.snapshot(), payload = this.payload(snapshot), wire = JSON.stringify(payload);
        const replacement: LocalDraft = { ...previous, lineage: this.proof.lineage, epoch: this.proof.epoch, incarnation: this.proof.incarnation,
          id: `draft_${this.proof.epoch}_${this.proof.sessionId}`, sequence: 1, cursor: 0,
          baseRevision: next.response.workspace.projectRevision, baseSha256: next.workspaceSha256,
          payloadWire: wire, payloadSha256: await sha256(wire), assets: snapshot.assets.filter(asset => payload.assetPins.includes(asset.id)) };
        await this.connection.repository.replaceOwner(previous, replacement);
        this.local = replacement; this.sequence = 1; superseded = view.drafts;
      }
    }
    if (resolveCurrent) {
      await this.checkpoint();
      const view = await this.connection.api.bootstrap(); this.acknowledge(view);
      const record = view.drafts.find(item => item.id === view.writer.draftId);
      if (!record) throw new Error("DRAFT_CORRUPT");
      const command = { schemaVersion: 1 as const, proof: this.proof, id: record.id, sequence: record.sequence,
        payloadSha256: record.payloadSha256, canonicalRevision: view.response.workspace.projectRevision, canonicalSha256: view.workspaceSha256 };
      let next: WriterViewV1;
      if (choice === "saved") next = await this.connection.api.discard(command);
      else {
        const project = view.response.workspace.project, snapshot = this.editor.snapshot();
        if (!project) throw new Error("DRAFT_CORRUPT");
        const [first, ...rest] = [...documentSteps(project.document, snapshot.document, true), ...factSteps(project.facts, snapshot.facts)];
        if (!first) next = await this.connection.api.discard(command);
        else next = await this.connection.api.useDraft({ ...command, mutation: { schemaVersion: 1, projectId: this.connection.api.project,
          clientMutationId: crypto.randomUUID(), actionId: crypto.randomUUID(), kind: "structure",
          capture: { sessionId: this.proof.sessionId, actionId: crypto.randomUUID(), actionToken: 0, dependencies: [] }, steps: [first, ...rest] } });
      }
      this.acknowledge(next);
    }
    for (const record of superseded) {
      this.acknowledge(await this.connection.api.discard({ schemaVersion: 1, proof: this.proof, id: record.id,
        sequence: record.sequence, payloadSha256: record.payloadSha256, canonicalRevision: this.view.response.workspace.projectRevision,
        canonicalSha256: this.view.workspaceSha256 }));
    }
    await Promise.all([...this.writes]);
    if (this.local) await this.connection.repository.remove(this.local);
    this.local = null; this.outbox = []; this.historyOutbox = []; this.touches = [];
    this.recoveryJob = null;
    this.cursor = this.view.writer.acknowledgedCursor;
    retainResume(this.connection.api.project, this.proof, this.view, this.cursor, 0);
    await this.connection.api.suspend(this.proof);
    this.setMode("detached"); return this.view.response;
  }
  close(): void {
    ++this.operation; this.setMode("closed");
    for (const reservation of this.reservations) this.editor.history.discard(reservation);
    this.reservations.clear();
  }
}

function isDraftPayload(value: unknown): value is DraftPayloadV1 { return validateBackgroundShape("background_draft_payload_v1", value); }
