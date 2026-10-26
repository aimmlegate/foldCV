import type { WriterProofV1 } from "../contracts/generated/background_writer_proof_v1";
import type { WriterSessionV1, WriterViewV2 } from "../contracts/generated/background_writer_view_v2";
import type { WriterAdvanceV2 } from "../contracts/generated/background_writer_advance_v2";
import type { WriterTouchV2 } from "../contracts/generated/background_writer_touch_v2";
import { jsonResponseWire } from "../contracts/json-response";
import { jsonWireAt, parseJsonWire, type JsonWireNode } from "../contracts/lossless-json";
import { RichApiFailure } from "../rich/api";
import type { PreparedSaveOpening, TemplateSaveVerification } from "../contracts/template-save";
import type { BoundTemplatePreparation } from "../contracts/template-transport";
import { snapshotIdentity, type RichSaveQueue, type TemplateQueuePorts } from "../rich/save-queue";
import type { TemplateClipboardCaptureV1 } from "../contracts/generated/template_clipboard_capture_v1";
import type { WriterCaptureClipboardV2 } from "../contracts/generated/background_writer_capture_clipboard_v2";
import type { TemplateRewritePreviewV1 } from "../contracts/generated/template_rewrite_preview_v1";
import type { WriterRewritePreviewV2 } from "../contracts/generated/background_writer_rewrite_preview_v2";
import type { DraftPayloadV2 } from "../contracts/generated/background_writer_draft_payload_v2";
import { isTemplateDraftPayload } from "../contracts/template-drafts";
import { retainResume, type AttachedTemplateWriter } from "./connection";
import type { LocalDraft } from "./drafts";
import { sha256 } from "./wire";
import { timers, WriterLifecycle, type WriterMode, type WriterObserver } from "./writer-lifecycle";

export type TemplateWriterPort = {
  compositionEnd: () => Promise<void>;
  lock: (locked: boolean) => void;
  changed: (mode: WriterMode, error: string | null) => void;
};
type Acknowledged = { revision: number; sha256: string; cursor: number; touchGeneration: number };
export type TemplateDraftQueue = NonNullable<DraftPayloadV2["templateQueue"]>;

function field(value: unknown, key: string): unknown { return typeof value === "object" && value !== null ? Reflect.get(value, key) : undefined; }
function images(value: unknown, found = new Set<string>()): Set<string> {
  if (Array.isArray(value)) value.forEach(item => images(item, found));
  else if (typeof value === "object" && value !== null) {
    const id = field(value, "assetId");
    if (typeof id === "string") found.add(id);
    Object.values(value).forEach(item => images(item, found));
  }
  return found;
}

function acknowledgedOf(writer: WriterSessionV1, fallback: string): Acknowledged {
  return { revision: writer.acknowledgedRevision, sha256: writer.acknowledgedSha256 ?? fallback,
    cursor: writer.acknowledgedCursor, touchGeneration: writer.touchGeneration };
}

/** The V7 family of the existing writer lifecycle: V2 headers, null input touches, compact saves and local history. */
export class TemplateBackgroundWriter extends WriterLifecycle {
  cursor: number;
  private touches: WriterTouchV2[] = [];
  private acknowledged: Acknowledged;
  // Saves name the writer's acknowledged state; flush and detach name the latest canonical state, which may be newer.
  private latest: { revision: number; sha256: string };
  private capacityLocked = false;
  private queue: RichSaveQueue | null = null;
  // The private local draft: verified durable content plus pending V7 input; it never proves a save.
  private local: LocalDraft | null;
  private sequence: number;
  private readonly writes = new Set<Promise<void>>();
  private draftSource: () => TemplateDraftQueue | null = () => null;
  private saves = new WeakMap<BoundTemplatePreparation, { header: JsonWireNode; opening: PreparedSaveOpening; proof: WriterProofV1 }>();
  private beating: object | null = null;
  constructor(readonly connection: AttachedTemplateWriter, private readonly port: TemplateWriterPort, time = timers,
    observe: WriterObserver = () => Promise.resolve()) {
    super(time, observe);
    const view = connection.view, local = connection.local;
    this.local = local?.record ?? null;
    this.cursor = Math.max(view.writer.acknowledgedCursor, local?.record.cursor ?? 0);
    this.sequence = Math.max(local?.record.sequence ?? 0, view.writer.draftSequenceFloor ?? 0);
    if (local) this.touches = (local.payload.touches ?? []).filter(touch => touch.cursor > view.writer.acknowledgedCursor);
    this.acknowledged = acknowledgedOf(view.writer, view.workspaceSha256);
    this.latest = { revision: view.response.workspace.projectRevision, sha256: view.workspaceSha256 };
    this.mode = !connection.proof ? "read_only" : view.writer.status === "attached" && !local ? "normal" : "recovering";
    this.port.changed(this.mode, connection.error);
  }
  get proof(): WriterProofV1 { const proof = this.connection.proof; if (!proof) throw new Error("WRITER_READ_ONLY"); return proof; }
  /** The verified canonical response the V7 queue starts from. */
  get durable(): JsonWireNode { return jsonWireAt(this.connection.viewWire, ["response"]); }
  get writable(): boolean { return this.mode === "normal" && this.touches.length < 100; }
  get retainsDraft(): boolean { return this.local !== null || this.writes.size > 0; }
  get needsUnloadGuard(): boolean {
    return !["detached", "closed", "read_only"].includes(this.mode) && (this.touches.length > 0 || (this.queue?.template.pending.length ?? 0) > 0);
  }
  /** The editor session supplies the queue record; the writer owns draft storage. */
  useDraftSource(source: () => TemplateDraftQueue | null): void { this.draftSource = source; }
  private payload(): DraftPayloadV2 {
    const project = jsonWireAt(this.requireQueue().template.durable, ["workspace", "project"]).value, queue = this.draftSource();
    const document = field(project, "document");
    const value = { schemaVersion: 2, document, facts: field(project, "facts"), outbox: [], assetPins: [...images(document)],
      touches: structuredClone(this.touches), historyOutbox: [], importIssues: field(project, "importIssues"),
      importCoverage: field(project, "importCoverage"), ...(queue ? { templateQueue: queue } : {}) };
    if (!isTemplateDraftPayload(value)) throw new Error("DRAFT_CORRUPT");
    return value;
  }
  /** Retain the verified durable state and pending input locally; later writes win by sequence. */
  retain(): Promise<void> {
    const proof = this.connection.proof;
    if (!proof || !this.queue) return Promise.resolve();
    let payload: DraftPayloadV2;
    try { payload = this.payload(); } catch (error) { return Promise.reject(error); }
    const payloadWire = JSON.stringify(payload), sequence = ++this.sequence, cursor = this.cursor, view = this.connection.view;
    const assets = (view.response.workspace.project?.assets ?? []).filter(asset => payload.assetPins.includes(asset.id))
      .map(asset => ({ id: asset.id, sha256: asset.sha256 }));
    const fields = { schemaVersion: 1 as const, project: this.connection.api.project, lineage: proof.lineage, epoch: proof.epoch,
      incarnation: proof.incarnation, id: this.local?.id ?? `draft_${proof.epoch}_${proof.sessionId}`, sequence, cursor,
      baseRevision: view.response.workspace.projectRevision, baseSha256: view.workspaceSha256, payloadWire, assets };
    retainResume(fields.project, proof, view, cursor, sequence);
    const work = (async () => {
      const result = await this.connection.repository.write({ ...fields, payloadSha256: await sha256(payloadWire) });
      if (this.connection.proof !== proof) return;
      if (!this.local || result.sequence >= this.local.sequence) this.local = result;
    })();
    this.writes.add(work);
    void work.finally(() => this.writes.delete(work)).catch(() => {});
    return work;
  }
  /** Remove the local draft once everything it held is saved; the caller has no unqueued editor input. */
  async clearCleanDraft(): Promise<void> {
    const template = this.queue?.template;
    if (!this.local || !template || template.pending.length || template.state.kind !== "ready" || this.touches.length
      || !["normal", "protected"].includes(this.mode)) return;
    const ticket = this.cursor;
    await Promise.all([...this.writes]);
    if (ticket !== this.cursor || template.pending.length || this.touches.length || !this.local) return;
    const record = this.local;
    await this.connection.repository.remove(record);
    if (this.local?.sequence === record.sequence) this.local = null;
    retainResume(this.connection.api.project, this.proof, this.connection.view, this.cursor, this.local?.sequence ?? 0);
  }
  /** A server copy of the local draft when leaving fails; the writer stays recovering on the server. */
  async checkpoint(): Promise<void> {
    const proof = this.proof;
    await this.retain();
    const local = this.local;
    if (!local) throw new Error("DRAFT_STORAGE_FAILED");
    if (this.connection.proof !== proof || local.epoch !== proof.epoch || local.incarnation !== proof.incarnation) throw new Error("WRITER_STALE_CALLBACK");
    const payload: unknown = JSON.parse(local.payloadWire);
    if (!isTemplateDraftPayload(payload)) throw new Error("DRAFT_CORRUPT");
    await this.connection.api.templateCheckpoint({ schemaVersion: 2, proof, id: local.id, sequence: local.sequence,
      actionCursor: local.cursor, baseRevision: local.baseRevision, baseSha256: local.baseSha256, payload });
    await this.observe("draft_checkpointed");
  }
  /** Leave recovery: a server draft ends with pending_input, otherwise the writer reconciles; the queue starts from the read state. */
  async reattach(): Promise<void> {
    if (this.mode !== "recovering") return;
    try { await this.reattachOnce(); }
    catch (error) {
      // An expired lease or a service restart leaves this proof unable to reconcile; the same session opens again once.
      if (!(error instanceof RichApiFailure) || error.code !== "WRITER_UNKNOWN") throw error;
      try { await this.reopen(); }
      catch (reopenError) {
        // Another session took this resume over: this one only reads until the user takes it back.
        if (reopenError instanceof RichApiFailure && reopenError.code === "WRITER_UNKNOWN") {
          ++this.operation; this.connection.proof = null; this.connection.error = "WRITER_READ_ONLY";
          this.port.lock(true); this.setMode("read_only");
        }
        throw reopenError;
      }
      await this.reattachOnce();
    }
  }
  private async reopen(): Promise<void> {
    const old = this.proof, ticket = this.operation;
    const view = await this.connection.api.templateOpen({ schemaVersion: 1, sessionId: old.sessionId, incarnation: crypto.randomUUID(),
      credential: old.credential, previousEpoch: old.epoch, previousIncarnation: old.incarnation,
      canonicalRevision: this.latest.revision, canonicalSha256: this.latest.sha256,
      actionCursor: this.cursor, draftSequence: this.local?.sequence ?? 0 });
    if (this.connection.proof !== old || this.operation !== ticket) throw new Error("WRITER_STALE_CALLBACK");
    const proof: WriterProofV1 = { schemaVersion: 1, lineage: view.writer.lineage, epoch: view.writer.epoch,
      sessionId: view.writer.sessionId, incarnation: view.writer.incarnation, credential: old.credential };
    if (this.local) {
      const replacement = { ...this.local, incarnation: proof.incarnation };
      await this.connection.repository.replaceOwner(this.local, replacement);
      this.local = replacement;
    }
    this.connection.proof = proof;
    // Retained save headers name the old incarnation; the fenced head was resolved before recovery reached here.
    this.saves = new WeakMap();
    retainResume(this.connection.api.project, proof, view, this.cursor, this.local?.sequence ?? 0);
  }
  private async reattachOnce(): Promise<void> {
    const proof = this.proof, ticket = this.operation, read = await this.connection.api.templateRead(proof);
    if (this.connection.proof !== proof || this.operation !== ticket || !this.adoptView(read)) throw new Error("WRITER_STALE_CALLBACK");
    this.touches = this.touches.filter(touch => touch.cursor > read.writer.acknowledgedCursor);
    const record = read.drafts.find(item => item.id === read.writer.draftId);
    let view = read;
    if (record) view = await this.connection.api.templatePendingInput({ schemaVersion: 1, proof, id: record.id, sequence: record.sequence,
      payloadSha256: record.payloadSha256, canonicalRevision: read.response.workspace.projectRevision, canonicalSha256: read.workspaceSha256 });
    else if (read.writer.status !== "attached") {
      try { view = await this.connection.api.templateReconcile(this.headerValue(this.latest)); }
      catch (error) {
        // Null touches carry no content; when they no longer chain to the server cursor they are dropped.
        if (!(error instanceof RichApiFailure) || error.code !== "JOB_SCOPE_INVALID") throw error;
        this.touches = []; this.cursor = read.writer.acknowledgedCursor;
        view = await this.connection.api.templateReconcile(this.headerValue(this.latest));
      }
    }
    // An attached writer may still have lost its lease; confirm it before input resumes.
    else view = await this.connection.api.templateHeartbeat(proof);
    if (this.connection.proof !== proof || this.operation !== ticket || !this.adoptView(view)) throw new Error("WRITER_STALE_CALLBACK");
    this.cursor = Math.max(this.cursor, view.writer.acknowledgedCursor);
    const template = this.requireQueue().template;
    if (!template.pending.length) template.adoptDurable(jsonWireAt(this.connection.viewWire, ["response"]));
    this.setMode("normal"); this.port.lock(false);
  }
  /** Give up the retained input and continue from the saved state. */
  async discardDraft(): Promise<void> {
    await this.reattach();
    await Promise.all([...this.writes]);
    if (this.local) { await this.connection.repository.remove(this.local); this.local = null; }
  }
  /** The queue is attached after construction so its ports can call back into this writer. */
  attach(queue: RichSaveQueue): void { if (this.queue) throw new Error("WRITER_QUEUE_ATTACHED"); void queue.template; this.queue = queue; }
  protected notify(mode: WriterMode, error: string | null): void { this.port.changed(mode, error); }
  protected lockInput(locked: boolean): void { this.port.lock(locked); }
  protected compositionDone(): Promise<void> { return this.port.compositionEnd(); }
  protected enterRecovery(error: unknown): void {
    if (["closed", "detached", "read_only"].includes(this.mode)) return;
    ++this.operation; this.port.lock(false);
    this.setMode("recovering", error instanceof Error ? error.message : "WRITER_RECOVERY_REQUIRED");
  }
  /** Accepted input advances the cursor; a null touch records order only and never implies saved content. */
  input(): void {
    if (!this.writable) throw new Error("WRITER_INPUT_BLOCKED");
    this.cursor++;
    this.touches.push({ cursor: this.cursor, mutation: null });
    if (this.touches.length >= 100) {
      this.capacityLocked = true; this.port.lock(true);
      this.port.changed(this.mode, "Дождитесь сохранения, чтобы продолжить ввод. Уже введённый текст остаётся в редакторе.");
    }
  }
  private headerValue(canonical: { revision: number; sha256: string } = this.acknowledged): WriterAdvanceV2 {
    return { schemaVersion: 2, proof: structuredClone(this.proof), canonicalRevision: canonical.revision,
      canonicalSha256: canonical.sha256, actionCursor: this.cursor, touches: structuredClone(this.touches) };
  }
  private header(): JsonWireNode { return parseJsonWire(JSON.stringify(this.headerValue())); }
  private acknowledge(writer: WriterSessionV1, fallback: string): void {
    const proof = this.proof;
    if (writer.lineage !== proof.lineage || writer.epoch !== proof.epoch || writer.incarnation !== proof.incarnation
      || writer.sessionId !== proof.sessionId || writer.projectId !== this.connection.api.project) throw new Error("WRITER_UNKNOWN");
    const next = acknowledgedOf(writer, fallback);
    if (next.cursor < this.acknowledged.cursor || next.touchGeneration < this.acknowledged.touchGeneration) return;
    this.acknowledged = next;
    if (next.revision > this.latest.revision) this.latest = { revision: next.revision, sha256: next.sha256 };
    this.touches = this.touches.filter(touch => touch.cursor > next.cursor);
    if (this.capacityLocked && this.mode === "normal" && this.touches.length < 100) { this.capacityLocked = false; this.port.lock(false); }
    retainResume(this.connection.api.project, proof, { response: { workspace: { projectRevision: next.revision } }, workspaceSha256: next.sha256 },
      this.cursor, 0);
  }
  private adoptView(view: WriterViewV2): boolean {
    const revision = view.response.workspace.projectRevision;
    if (revision < this.latest.revision || view.writer.acknowledgedCursor < this.acknowledged.cursor
      || view.writer.touchGeneration < this.acknowledged.touchGeneration || view.writer.acknowledgedRevision < this.acknowledged.revision) return false;
    if (revision === this.latest.revision && view.workspaceSha256 !== this.latest.sha256) throw new Error("INVALID_RESULT");
    const wire = jsonResponseWire(view);
    this.acknowledge(view.writer, view.workspaceSha256);
    this.connection.view = view; this.connection.viewWire = wire;
    this.latest = { revision, sha256: view.workspaceSha256 };
    return true;
  }
  /** Adopt a canonical advance made outside this writer (export records): flush names it, so the writer acknowledges it;
   * the queue takes it as base only while idle. */
  async refresh(): Promise<boolean> {
    if (!["normal", "protected"].includes(this.mode)) return false;
    const proof = this.proof, ticket = this.operation, view = await this.connection.api.templateRead(proof);
    if (this.connection.proof !== proof || this.operation !== ticket || !this.adoptView(view)) return false;
    if (this.latest.revision !== this.acknowledged.revision || this.latest.sha256 !== this.acknowledged.sha256) {
      const flushed = await this.connection.api.templateFlush(this.headerValue(this.latest));
      if (this.connection.proof !== proof || this.operation !== ticket || !this.adoptView(flushed)) return false;
    }
    const template = this.requireQueue().template;
    if (template.pending.length || template.state.kind !== "ready") return false;
    template.adoptDurable(jsonWireAt(this.connection.viewWire, ["response"]));
    return true;
  }
  /** A stale header after an outside metadata advance is re-read once while this writer still owns the session. */
  private async canonicalRetry<T>(work: () => Promise<T>): Promise<T> {
    try { return await work(); }
    catch (error) {
      if (!(error instanceof RichApiFailure) || error.code !== "WRITER_UNKNOWN") throw error;
      const before = this.latest.revision;
      await this.refresh();
      if (this.latest.revision === before) throw error;
      return work();
    }
  }
  private opening(): PreparedSaveOpening {
    const proof = this.proof;
    return { projectId: this.connection.api.project, lineage: proof.lineage, epoch: proof.epoch, sessionId: proof.sessionId,
      incarnation: proof.incarnation, actionCursor: this.cursor, minimumTouchGeneration: this.acknowledged.touchGeneration };
  }
  /** Network ports for the queue's V7 strategy; the queue alone schedules them. */
  queuePorts(events: Pick<TemplateQueuePorts, "adopted" | "changed" | "retained" | "released">): TemplateQueuePorts {
    return { ...events, proof: () => this.proof,
      prepare: (base, request) => this.connection.api.templatePrepareDelta(base, request),
      save: preparation => this.save(preparation) };
  }
  private async save(preparation: BoundTemplatePreparation): Promise<TemplateSaveVerification> {
    if (!["normal", "protected"].includes(this.mode)) throw new Error("WRITER_RECOVERY_REQUIRED");
    const retained = this.saves.get(preparation) ?? { header: this.header(), opening: this.opening(), proof: this.proof };
    this.saves.set(preparation, retained);
    const { proof, header, opening } = retained;
    if (this.proof !== proof) throw new Error("WRITER_STALE_CALLBACK");
    const result = await this.connection.api.templateSavePrepared(header, preparation, opening);
    if (this.connection.proof !== proof) throw new Error("WRITER_STALE_CALLBACK");
    this.acknowledge(result.acknowledgment.writer, this.acknowledged.sha256);
    this.saves.delete(preparation);
    return result;
  }
  async flushTouches(): Promise<void> {
    if (!this.touches.length || !["normal", "protected"].includes(this.mode)) return;
    const proof = this.proof, view = await this.canonicalRetry(() => this.connection.api.templateFlush(this.headerValue(this.latest)));
    if (this.connection.proof !== proof) return;
    this.adoptView(view);
    await this.observe("touch_watermark_durable");
  }
  async heartbeat(): Promise<void> {
    // One heartbeat at a time: each holds the server writer lock, so overlapping ones only queue behind a slow save.
    if (this.mode !== "normal" || this.beating) return;
    const beat = {}, proof = this.proof;
    this.beating = beat;
    // A reply that never comes must not stop later heartbeats for good.
    const release = this.time.alarm(() => { if (this.beating === beat) this.beating = null; }, 30_000);
    try { await this.connection.api.templateHeartbeat(proof); }
    catch (error) { if (this.connection.proof === proof) this.enterRecovery(error); }
    finally { release(); if (this.beating === beat) this.beating = null; }
  }
  /** Drain, then one server Undo/Redo for the action at the cursor; its verified state becomes the queue base. */
  history(direction: "undo" | "redo", originActionId: string, actionGeneration: number): Promise<WriterViewV2> {
    let result: WriterViewV2 | null = null;
    return this.bounded(async ticket => {
      const queue = this.requireQueue();
      await queue.flush(); this.current(ticket);
      const durable = queue.template.durable, workspace = jsonWireAt(durable, ["workspace"]);
      const revision = jsonWireAt(workspace, ["projectRevision"]).value;
      if (typeof revision !== "number") throw new Error("INVALID_RESULT");
      this.cursor++; this.touches.push({ cursor: this.cursor, mutation: null });
      // A history command names the current canonical state, not the last acknowledged save header.
      const header = this.headerValue({ revision, sha256: await sha256(workspace.wire) });
      const view = await this.connection.api.templateHistory({ ...header, originActionId, actionGeneration, direction,
        clientMutationId: `${this.proof.sessionId}:history:${crypto.randomUUID()}` });
      this.current(ticket);
      this.adoptView(view);
      queue.template.adoptDurable(jsonWireAt(this.connection.viewWire, ["response"]));
      result = view;
    }, 15_000).then(() => { if (!result) throw new Error("WRITER_RECOVERY_REQUIRED"); return result; });
  }
  /** Capture a copy source against the drained verified snapshot; the capture lives with this writer session. */
  captureClipboard(selection: WriterCaptureClipboardV2["selection"]): Promise<TemplateClipboardCaptureV1> {
    if (this.mode !== "normal") return Promise.reject(new Error("WRITER_INPUT_BLOCKED"));
    const durable = this.requireQueue().template.durable;
    return this.connection.api.templateCaptureClipboard({ schemaVersion: 2, proof: this.proof, clientCaptureId: crypto.randomUUID(),
      snapshot: snapshotIdentity(jsonWireAt(durable, ["snapshot"]).value), selection });
  }
  /** Generate a replacement for a verified range at the drained snapshot; nothing changes until it is applied. */
  rewritePreview(requestId: string, range: WriterRewritePreviewV2["range"], instruction: string): Promise<TemplateRewritePreviewV1> {
    if (this.mode !== "normal") return Promise.reject(new Error("WRITER_INPUT_BLOCKED"));
    const durable = this.requireQueue().template.durable;
    return this.connection.api.templateRewritePreview({ schemaVersion: 2, proof: this.proof, requestId,
      snapshot: snapshotIdentity(jsonWireAt(durable, ["snapshot"]).value), range, instruction });
  }
  async rewriteCancel(requestId: string): Promise<boolean> {
    if (!this.connection.proof) return false;
    return this.connection.api.templateRewriteCancel({ schemaVersion: 2, proof: this.proof, requestId });
  }
  async releaseClipboard(clipboardCaptureId: string): Promise<void> {
    if (!this.connection.proof || ["read_only", "detached", "closed"].includes(this.mode)) return;
    await this.connection.api.templateReleaseClipboard({ schemaVersion: 2, proof: this.proof, clipboardCaptureId });
  }
  /** Resolve a fenced head from the durable replay record before any later input moves. */
  async recover(): Promise<void> {
    const queue = this.requireQueue();
    if (queue.template.state.kind !== "fenced") { await this.reattach(); return; }
    const head = queue.template.headIdentity(), proof = this.proof, ticket = this.operation;
    const view = await this.connection.api.templateRead(proof);
    if (this.connection.proof !== proof || this.operation !== ticket || !this.adoptView(view)) throw new Error("WRITER_STALE_CALLBACK");
    const replay = view.response.workspace.mutationReplay;
    const checksum = head?.mutationWire ? await sha256(head.mutationWire) : null;
    if (this.connection.proof !== proof || this.operation !== ticket) throw new Error("WRITER_STALE_CALLBACK");
    const committed = head !== null && checksum !== null && replay.some(item => item.clientMutationId === head.clientMutationId
      && item.requestSha256 === checksum);
    queue.resolveTemplateOutcome(jsonWireAt(this.connection.viewWire, ["response"]), head !== null && committed);
    await this.reattach();
  }
  /** Leaving the project drains input and detaches cleanly; a failure leaves input retained and the writer recovering. */
  async navigate(): Promise<void> {
    if (this.mode === "read_only" || this.mode === "detached") return;
    if (this.mode === "recovering") { await this.retainForNavigation(); return; }
    try {
      await this.bounded(async ticket => {
        await this.requireQueue().flush(); this.current(ticket);
        await this.flushTouches(); this.current(ticket);
        const view = await this.canonicalRetry(() => this.connection.api.templateDetach(this.headerValue(this.latest))); this.current(ticket);
        this.adoptView(view);
        await this.clearCleanDraft().catch(() => {});
        this.setMode("detached"); this.port.lock(true);
        await this.observe("clean_detach_acked");
      }, 15_000);
    } catch { await this.retainForNavigation(); }
  }
  private async retainForNavigation(): Promise<void> {
    await this.retain();
    void this.checkpoint().catch(error => { if (this.mode !== "closed") this.port.changed(this.mode, error instanceof Error ? error.message : "DRAFT_CHECKPOINT_UNCONFIRMED"); });
  }
  /** Reattach the same session after a clean detach (settings and back); the verified canonical state becomes the queue base. */
  async resume(): Promise<void> {
    if (this.mode !== "detached") return;
    const old = this.proof, current = this.connection.view;
    const view = await this.connection.api.templateOpen({ schemaVersion: 1, sessionId: old.sessionId, incarnation: crypto.randomUUID(),
      credential: old.credential, previousEpoch: old.epoch, previousIncarnation: old.incarnation,
      canonicalRevision: current.response.workspace.projectRevision, canonicalSha256: current.workspaceSha256,
      actionCursor: this.cursor, draftSequence: 0 });
    if (view.writer.status !== "attached") { this.setMode("recovering", "DRAFT_RECOVERY_REQUIRED"); throw new Error("DRAFT_RECOVERY_REQUIRED"); }
    this.connection.proof = { schemaVersion: 1, lineage: view.writer.lineage, epoch: view.writer.epoch, sessionId: view.writer.sessionId,
      incarnation: view.writer.incarnation, credential: old.credential };
    this.touches = []; this.cursor = view.writer.acknowledgedCursor;
    this.acknowledged = acknowledgedOf(view.writer, view.workspaceSha256);
    this.adoptView(view);
    this.requireQueue().template.adoptDurable(jsonWireAt(this.connection.viewWire, ["response"]));
    this.setMode("normal"); this.port.lock(false);
  }
  close(): void { ++this.operation; this.setMode("closed"); }
  private requireQueue(): RichSaveQueue { if (!this.queue) throw new Error("WRITER_QUEUE_REQUIRED"); return this.queue; }
}
