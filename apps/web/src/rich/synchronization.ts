import type { RichCompletionRequest } from "../contracts/generated/rich_completion_request";
import type { RichSelection } from "../contracts/generated/rich_selection";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichPanelRequest } from "../contracts/generated/rich_panel_request";
import type { DateCascadeProposal } from "../contracts/generated/date_cascade_proposal";
import { projectRequest, previewCascade, RichApiFailure } from "./api";
import type { CellChange, CellValue, DependencyCapture, SessionHistory } from "./history";
import type { RichBlock, RichSaveQueue } from "./save-queue";
import { AppliedIntentFailure } from "./intent-queue";
import { currentPanelIntent } from "./panel-intents";
import { FixedOperations, operationSync, type FixedCommand } from "../background/fixed";
import { pendingJob, projectJobs, type ProjectJobs } from "../background/jobs";
import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";
import { rewriteActive, rewriteCancellable, rewriteStage, type RewriteActivity, type RewritePreview, type RewriteStage } from "./rewrite-progress";
import { singleRewriteRange } from "./selection";
import { failureLabel } from "../background/status";

type Sync = RichProjectResponse["workspace"]["syncRecords"][number];
type Capture = DependencyCapture & { epochs: ReadonlyMap<string, number> };
export async function selectionChecksum(document: RichDocumentV1, selection: RichSelection): Promise<string> {
  const blocks = new Map<string, RichBlock>();
  function visit(items: RichBlock[]) { for (const block of items) { blocks.set(block.id, block); visit(block.children); } }
  document.regions.forEach(region => visit(region.blocks));
  const text = (content: RichBlock["content"]): string => typeof content === "string" ? content : Array.isArray(content)
    ? content.map(span => span.type === "link" ? span.content.map(part => part.text).join("") : span.text).join("") : "";
  let result = "";
  for (const id of selection.blockIds) {
    const block = blocks.get(id); if (!block) throw new Error("STALE_SELECTION");
    if (block.type === "table") {
      const cells = block.content.rows.flatMap(row => row.cells), first = id === selection.anchor.blockId ? cells.findIndex(cell => cell.id === selection.anchor.cellId) : 0;
      const last = id === selection.head.blockId ? cells.findIndex(cell => cell.id === selection.head.cellId) : cells.length - 1;
      for (const cell of cells.slice(first, last + 1)) {
        const value = text(cell.content); result += value.slice(id === selection.anchor.blockId && cell.id === selection.anchor.cellId ? selection.anchor.offset : 0,
          id === selection.head.blockId && cell.id === selection.head.cellId ? selection.head.offset : value.length);
      }
    } else {
      const value = text(block.type === "image" ? block.props.caption : block.content);
      result += selection.kind === "blocks" ? value : value.slice(id === selection.anchor.blockId ? selection.anchor.offset : 0,
        id === selection.head.blockId ? selection.head.offset : value.length);
    }
  }
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(result));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
export type SyncAdapter = {
  history: SessionHistory; queue: RichSaveQueue;
  current: () => ReadonlyMap<string, CellValue>;
  cells: (response: RichProjectResponse) => Map<string, CellValue>;
  changed: () => void; report: (response: RichProjectResponse) => void;
  failed?: (error: unknown) => void;
  applied?: (actionId: string, changes: CellChange[]) => void;
  rewriteProgress?: (activity: RewriteActivity) => void;
  rewritePreview?: (preview: RewritePreview) => void;
  approveRewrite?: (job: JobSnapshotV1) => Promise<void>;
  background?: boolean;
};
export type PanelCommand = Omit<RichPanelRequest, "capture" | "factsRevision" | "documentRevision">;
export class RichSynchronization {
  private closed = false;
  private readonly active = new Map<string, Capture>();
  private readonly invalidated = new Set<string>();
  private readonly cascades = new Map<string, DependencyCapture>();
  private readonly fixed: FixedOperations | null;
  private readonly jobs: ProjectJobs | null;
  private readonly submitted = new Map<string, string>();
  private readonly previews = new Map<string, { value: RewritePreview; sync: Sync; capture: Capture | null; job: JobSnapshotV1 | null }>();
  private readonly loadingPreviews = new Set<string>();
  private readonly applyingPreviews = new Set<string>();
  private readonly unsubscribe: (() => void) | null;
  private readonly rewrites = new Map<string, { activity: RewriteActivity; capture: Capture | null; jobId: string | null;
    stamp: { generation: number; cursor: number } | null; cancelled: boolean }>();
  constructor(private readonly adapter: SyncAdapter, private readonly projectId: string) {
    this.fixed = adapter.background ? new FixedOperations(projectId) : null;
    this.jobs = this.fixed ? projectJobs(projectId) : null;
    this.unsubscribe = this.jobs?.subscribe(view => this.finished(view.project?.jobs ?? [])) ?? null;
  }
  close(): void {
    this.invalidate();
    this.closed = true; this.unsubscribe?.(); this.cascades.clear(); this.invalidate(); this.submitted.clear(); this.rewrites.clear();
  }
  private finished(jobs: JobSnapshotV1[]): void {
    if (this.closed) return;
    for (const job of jobs) {
      if (job.submission.kind === "rewrite" && job.submission.scope.kind === "selection") {
        const id = job.submission.scope.selection.capture.actionId;
        if (!this.rewrites.has(id) && pendingJob(job)) {
          const started = Date.parse(job.submission.submittedAt);
          const activity: RewriteActivity = { actionId: id, stage: "queued", startedAt: Number.isFinite(started) ? started : Date.now(), finishedAt: null, detail: null };
          this.rewrites.set(id, { activity, capture: null, jobId: job.id, stamp: null, cancelled: false });
          this.adapter.rewriteProgress?.(activity);
        }
        const entry = this.rewrites.get(id);
        if (entry && (!entry.jobId || entry.jobId === job.id) && (!entry.stamp || job.executionGeneration > entry.stamp.generation
            || job.executionGeneration === entry.stamp.generation && job.eventCursor >= entry.stamp.cursor)) {
          entry.jobId = job.id;
          entry.stamp = { generation: job.executionGeneration, cursor: job.eventCursor };
          if (!this.applyingPreviews.has(id) || rewriteStage(job) !== "preview")
            this.progress(id, rewriteStage(job), failureLabel(job.publicationError?.code ?? job.error?.code));
          if (rewriteStage(job) === "preview" && !this.previews.has(id) && !this.loadingPreviews.has(id)) void this.loadPreview(job, id);
        }
      }
      const action = this.submitted.get(job.id);
      if (!action || !job.proposalId && !["completed", "failed", "cancelled", "interrupted"].includes(job.execution)) continue;
      this.submitted.delete(job.id); this.active.delete(action); this.adapter.history.discardPending(action);
    }
  }
  private retainPreview(sync: Sync, capture: Capture | null, job: JobSnapshotV1 | null): void {
    if (!sync.selection || typeof sync.rewriteSource !== "string" || typeof sync.rewriteResult !== "string" || !sync.rewriteResult.trim())
      throw new RichApiFailure("INVALID_RESULT");
    const value: RewritePreview = { actionId: sync.actionId, source: sync.rewriteSource, text: sync.rewriteResult, instruction: sync.instruction ?? "", selection: sync.selection };
    this.previews.set(sync.actionId, { value, sync, capture, job });
    this.adapter.rewritePreview?.(value);
    this.progress(sync.actionId, "preview");
  }
  private async loadPreview(job: JobSnapshotV1, id: string): Promise<void> {
    this.loadingPreviews.add(id);
    try {
      const response = await projectRequest(`/${this.projectId}`);
      if (this.closed || this.rewrites.get(id)?.cancelled) return;
      const sync = response.workspace.syncRecords.find(record => record.id === job.submission.input.id && record.actionId === id);
      if (response.workspace.projectId !== this.projectId || !sync || sync.kind !== "rewrite") throw new RichApiFailure("INVALID_RESULT");
      this.retainPreview(sync, this.rewrites.get(id)?.capture ?? null, job);
    } catch { this.progress(id, "review", "Не удалось открыть результат. Откройте резюме заново."); }
    finally { this.loadingPreviews.delete(id); }
  }
  previewRewrite(id: string): RewritePreview | null { return this.previews.get(id)?.value ?? null; }
  async applyRewrite(id: string): Promise<void> {
    const preview = this.previews.get(id);
    if (!preview || this.closed || this.rewrites.get(id)?.cancelled || this.applyingPreviews.has(id)) throw new RichApiFailure("STALE_SELECTION");
    this.applyingPreviews.add(id);
    this.progress(id, "applying");
    try {
      if (preview.job && this.jobs && this.adapter.approveRewrite) {
        await this.jobs.refresh();
        const job = this.jobs.view.project?.jobs.find(item => item.id === preview.job?.id);
        if (!job || rewriteStage(job) !== "preview") throw new RichApiFailure("STALE_SELECTION");
        await this.adapter.approveRewrite(job);
        await this.jobs.refresh();
        const saved = this.jobs.view.project?.jobs.find(item => item.id === job.id);
        if (!saved?.receipt && saved?.publication !== "no_change") throw new RichApiFailure("STALE_SELECTION");
        this.progress(id, saved.receipt ? "saved" : "no_change");
      } else {
        const origin = preview.capture, history = this.adapter.history;
        if (!origin || [...origin.dependencies].some(([key, revision]) => history.revision(key) !== revision)) throw new RichApiFailure("STALE_SELECTION");
        const marker = `request:${crypto.randomUUID()}`, action = history.commit("rewrite", [{ key: marker, before: null, after: "apply" }]);
        const capture = action ? this.capture(action, preview.sync.blockIds) : null;
        if (!capture) throw new RichApiFailure("STALE_SELECTION");
        try {
          const disposition = await this.apply(preview.sync, { ...capture, dependencies: origin.dependencies, epochs: origin.epochs });
          if (disposition && disposition !== "applied") throw new RichApiFailure("STALE_SELECTION");
          this.progress(id, disposition === "applied" ? "saved" : "no_change");
        } finally { history.discardPending(action ?? ""); }
      }
      this.previews.delete(id);
    } catch (error) { this.progress(id, "review", "Результат не применён. Проверьте фрагмент или запросите правку заново."); throw error; }
    finally { this.applyingPreviews.delete(id); }
  }
  private progress(id: string, stage: RewriteStage, detail: string | null = null): void {
    const entry = this.rewrites.get(id);
    if (!entry || this.closed || entry.activity.stage === stage && entry.activity.detail === detail) return;
    if (entry.cancelled && ["saving", "queued", "starting", "running"].includes(stage)) return;
    entry.activity = { ...entry.activity, stage, detail,
      startedAt: stage === "applying" && entry.activity.stage === "preview" ? Date.now() : entry.activity.startedAt,
      finishedAt: rewriteActive(stage) ? null : Date.now() };
    this.adapter.rewriteProgress?.(entry.activity);
  }
  async cancelRewrite(id: string): Promise<void> {
    const entry = this.rewrites.get(id);
    if (!entry || !rewriteCancellable(entry.activity.stage) && !this.previews.has(id)) return;
    const preview = this.previews.get(id);
    entry.cancelled = true; this.invalidated.add(id);
    this.progress(id, "cancelling");
    this.active.delete(id);
    this.adapter.history.discardPending(id);
    try {
      if (preview?.job && this.jobs) { this.finished([await this.jobs.discard(preview.job.id)]); this.previews.delete(id); }
      else if (entry.jobId && this.jobs) this.finished([await this.jobs.stop(entry.jobId)]);
      else if (entry.capture) {
        await projectRequest(`/${this.projectId}/cancel-action`, "POST", this.wireCapture(entry.capture));
        this.progress(id, "cancelled");
      }
      this.previews.delete(id);
    } catch {
      this.progress(id, "failed", "Не удалось подтвердить отмену. Проверьте состояние задачи перед повторным запросом.");
    }
  }
  private async background(command: FixedCommand, capture: Capture): Promise<boolean> {
    if (!this.fixed || !this.jobs) return false;
    this.active.set(capture.actionId, capture);
    try {
      const reply = await this.fixed.submit(command,
        () => !this.invalidated.has(capture.actionId) && (this.closed || this.adapter.history.current(capture)));
      if (this.invalidated.has(capture.actionId) || !this.closed && !this.adapter.history.current(capture)) {
        await projectRequest(`/${this.projectId}/cancel-action`, "POST", this.wireCapture(capture));
        this.adapter.history.discardPending(capture.actionId);
      }
      if (this.closed) return true;
      this.submitted.set(reply.job.id, capture.actionId);
      this.finished([reply.job, ...(this.jobs.view.project?.jobs ?? [])]);
      void this.jobs.refresh().catch(() => {});
      return true;
    } catch (error) { this.active.delete(capture.actionId); throw error; }
  }
  invalidate(): void {
    for (const [id, capture] of this.active) if (this.closed || !this.adapter.history.current(capture)) {
      this.active.delete(id);
      if (this.closed && this.fixed) continue;
      this.invalidated.add(id);
      const rewrite = this.rewrites.get(id);
      if (rewrite) { rewrite.cancelled = true; this.progress(id, "cancelling", "Выделенный фрагмент изменился. Останавливаем этот запрос."); }
      void projectRequest(`/${this.projectId}/cancel-action`, "POST", this.wireCapture(capture))
        .then(() => { if (rewrite && !rewrite.jobId) this.progress(id, "cancelled", "Выделенный фрагмент изменился."); })
        .catch(() => { if (rewrite) this.progress(id, "failed", "Не удалось подтвердить отмену. Проверьте состояние задачи."); });
      if (this.fixed) this.adapter.history.discardPending(id);
    }
  }
  private async admitted(path: string, body: unknown, capture: Capture): Promise<RichProjectResponse> {
    if (this.closed || !this.adapter.history.current(capture)) throw new RichApiFailure("STALE_SELECTION");
    this.active.set(capture.actionId, capture);
    try { return await projectRequest(path, "POST", body); }
    finally { this.active.delete(capture.actionId); }
  }
  private capture(action: string, blockIds: string[]): Capture | null {
    const values = this.adapter.current(), records = new Set<string>(), keys = new Set<string>();
    for (const [key, value] of values) {
      if (key.startsWith("region:")) keys.add(key);
      if (!key.startsWith("block:") || !value) continue;
      const stored: unknown = JSON.parse(value);
      if (typeof stored !== "object" || stored === null || !("block" in stored)) continue;
      if (blockIds.includes(key.slice(6))) {
        keys.add(key);
        // IDs, rather than matching prose, select related working records.
        const collect = (item: unknown) => {
          if (Array.isArray(item)) item.forEach(collect);
          else if (typeof item === "object" && item !== null) {
            if ("recordId" in item && typeof item.recordId === "string") records.add(item.recordId);
            Object.values(item).forEach(collect);
          }
        };
        collect(stored);
      } else if ("children" in stored && Array.isArray(stored.children) && stored.children.some((id: unknown) => typeof id === "string" && blockIds.includes(id))) keys.add(key);
    }
    for (const key of values.keys()) if ([...records].some(id => key === `fact:${id}` || key.startsWith("fact-field:") && key.includes(JSON.stringify(id)))) keys.add(key);
    const capture = this.adapter.history.capture(action, [...keys]);
    return capture ? { ...capture, epochs: new Map([...values.keys()].map(key => [key, this.adapter.history.revision(key)])) } : null;
  }
  private wireCapture(capture: DependencyCapture): RichMutation["capture"] {
    return { sessionId: capture.session, actionId: capture.actionId, actionToken: capture.actionToken, dependencies: [] };
  }
  async complete(action: string, blockIds: string[], movedIds: string[], removedFields: RichCompletionRequest["removedFields"], interpret = true, removedRecordIds: string[] = []): Promise<void> {
    const capture = this.capture(action, blockIds);
    if (!capture || this.closed) return;
    await this.adapter.queue.flush();
    if (!this.adapter.history.current(capture) || this.closed) return;
    const request = { capture: this.wireCapture(capture), blockIds, movedIds, removedFields, removedRecordIds, interpret } satisfies RichCompletionRequest;
    if (await this.background({ kind: "completion", request }, capture)) return;
    const response = await this.admitted(`/${this.projectId}/completion`, request, capture);
    await this.apply(operationSync(response, this.projectId, capture.actionId), capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async rewrite(selection: RichSelection, instruction: string, previewOnly = false): Promise<void> {
    if (previewOnly && !singleRewriteRange(selection)) throw new Error("Выделите текст внутри одного блока или ячейки.");
    const marker = `request:${crypto.randomUUID()}`, history = this.adapter.history;
    const action = history.commit("rewrite", [{ key: marker, before: null, after: "pending" }]);
    if (!action) return;
    let queued = false;
    try {
    const capture = this.capture(action, selection.blockIds);
    if (!capture) return;
    const activity: RewriteActivity = { actionId: action, stage: "saving", startedAt: Date.now(), finishedAt: null, detail: null };
    this.rewrites.set(action, { activity, capture, jobId: null, stamp: null, cancelled: false });
    this.adapter.rewriteProgress?.(activity);
    await this.adapter.queue.flush();
    if (this.invalidated.has(action) || this.closed) return;
    if (!history.current(capture)) throw new RichApiFailure("STALE_SELECTION");
    const project = this.adapter.queue.baseline.workspace.project;
    if (!project) return;
    selection.textSha256 = await selectionChecksum(project.document, selection);
    if (this.invalidated.has(action) || this.closed) return;
    if (!history.current(capture)) throw new RichApiFailure("STALE_SELECTION");
    const blocks = new Map<string, number>();
    function visit(items: RichBlock[]) { for (const block of items) { blocks.set(block.id, block.revision); visit(block.children); } }
    project.document.regions.forEach(region => visit(region.blocks));
    selection.capture = { ...this.wireCapture(capture), dependencies: selection.blockIds.map(id => ({ kind: "block", id, revision: blocks.get(id) ?? 1, fingerprint: null })) };
    this.progress(action, this.fixed ? "queued" : "running");
    const request = { selection, instruction, ...(previewOnly ? { previewOnly: true } : {}) };
    if (await this.background({ kind: "rewrite", request }, capture)) { queued = true; this.finished(this.jobs?.view.project?.jobs ?? []); return; }
    const response = await this.admitted(`/${this.projectId}/rewrite`, request, capture);
    if (this.invalidated.has(action) || this.closed) return;
    const sync = operationSync(response, this.projectId, capture.actionId);
    if (sync.status === "failed" || sync.status === "stale") {
      this.adapter.report(response); throw new RichApiFailure(sync.errorCode ?? "REWRITE_FAILED");
    }
    if (previewOnly) { this.retainPreview(sync, capture, null); return; }
    this.progress(action, "applying");
    const disposition = await this.apply(sync, capture);
    if (disposition && disposition !== "applied") throw new Error("Правка устарела. Запросите её заново.");
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
    this.progress(action, disposition === "applied" ? "saved" : "no_change");
    } catch (error) {
      if (!this.rewrites.get(action)?.cancelled) {
        this.progress(action, "failed", "Правка не завершена. Проверьте текст и состояние сохранения перед повторным запросом.");
        throw error;
      }
    } finally { if (!queued) history.discardPending(action); }
  }
  async resolve(id: string): Promise<void> {
    const history = this.adapter.history, marker = `request:${crypto.randomUUID()}`;
    const action = history.commit("panel", [{ key: marker, before: null, after: "resolve" }]);
    if (!action || this.closed) return;
    await this.adapter.queue.flush();
    const origin = this.capture(action, this.adapter.queue.baseline.workspace.syncRecords.find(sync => sync.id === id)?.blockIds ?? []);
    if (!origin) return;
    if (await this.background({ kind: "resolve", syncId: id, capture: this.wireCapture(origin) }, origin)) return;
    const response = await projectRequest(`/${this.projectId}/sync/${id}/resolve`, "POST", this.wireCapture(origin));
    const sync = operationSync(response, this.projectId, action), capture = this.capture(action, sync.blockIds);
    if (sync && capture) await this.apply(sync, capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async panel(command: PanelCommand): Promise<void> {
    const adapter = this.adapter, history = adapter.history;
    await adapter.queue.flush();
    if (this.closed) throw new Error("Редактор закрыт.");
    const before = adapter.cells(adapter.queue.baseline), project = adapter.queue.baseline.workspace.project;
    if (!project) throw new Error("Документ закрыт.");
    const intent = currentPanelIntent(command, project.facts);
    if (!intent) return;
    const marker = `request:${crypto.randomUUID()}`, action = history.commit("panel", [{ key: marker, before: null, after: "panel" }]);
    const initial = action ? history.capture(action, []) : null;
    const epochs = new Map([...adapter.current().keys()].map(key => [key, history.revision(key)]));
    if (!initial) return;
    try {
    const response = await projectRequest(`/${this.projectId}/panel/preview`, "POST", { ...intent,
      factsRevision: project.facts.revision, documentRevision: project.document.revision, capture: this.wireCapture(initial) } satisfies RichPanelRequest);
    const after = adapter.cells(response);
    const changes = [...new Set([...before.keys(), ...after.keys()])].map(key => ({ key, before: before.get(key) ?? null, after: after.get(key) ?? null }))
      .filter(change => change.before !== change.after);
    if (!changes.length) return;
    const dependencies = new Map(changes.map(change => [change.key, epochs.get(change.key) ?? 0]));
    const disposition = this.closed ? "stale" : history.attach({ ...initial, dependencies }, changes);
    if (disposition !== "applied") throw new Error("Изменения уже обновились. Повторите правку.");
    adapter.changed();
    const saved = () => { if (!this.closed) { adapter.applied?.(initial.actionId, changes); this.synchronizePanelAction(initial.actionId, changes); } };
    try { await adapter.queue.flush(); }
    catch (error) { throw new AppliedIntentFailure(async () => { await adapter.queue.flush(); saved(); }, error); }
    saved();
    } finally { history.discardPending(initial.actionId); }
  }
  private synchronizePanelAction(actionId: string, changes: CellChange[]): void {
    const adapter = this.adapter;
    const records = new Set<string>();
    for (const change of changes) {
      if (change.key.startsWith("fact:")) records.add(change.key.slice(5));
      if (change.key.startsWith("fact-field:")) {
        const pair: unknown = JSON.parse(change.key.slice(11));
        if (Array.isArray(pair) && typeof pair[0] === "string") records.add(pair[0]);
      }
    }
    const ids = [...adapter.current()].filter(([key, value]) => key.startsWith("block:") && value && [...records].some(id => value.includes(JSON.stringify(id))))
      .map(([key]) => key.slice(6));
    const capture = this.capture(actionId, ids);
    if (capture && records.size) void this.panelSync(capture, [...records]).catch(error => adapter.failed?.(error));
  }
  private async panelSync(capture: Capture, records: string[]): Promise<void> {
    const [first, ...rest] = records;
    if (!first) return;
    const request = { capture: this.wireCapture(capture), recordIds: [first, ...rest] } satisfies Extract<FixedCommand, { kind: "panel" }>["request"];
    if (await this.background({ kind: "panel", request }, capture)) return;
    const response = await this.admitted(`/${this.projectId}/panel/sync`, request, capture);
    await this.apply(operationSync(response, this.projectId, capture.actionId), capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async cascadePreview(jobId: string, periodId: string, actionId: string): Promise<DateCascadeProposal> {
    await this.adapter.queue.flush();
    const history = this.adapter.history;
    const keys = [...this.adapter.current().keys()].filter(key => key.startsWith("fact-field:") && key.includes('"period:'));
    const capture = history.capture(actionId, keys);
    if (!capture || this.closed) throw new Error("Предпросмотр устарел. Измените период заново.");
    const proposal = await previewCascade(this.projectId, { anchorJobId: jobId, anchorPeriodId: periodId, capture: this.wireCapture(capture) });
    if (!history.current(capture) || this.closed) throw new Error("Предпросмотр устарел. Обновите его.");
    this.cascades.clear(); this.cascades.set(proposal.id, capture);
    return proposal;
  }
  async cascadeApply(proposal: DateCascadeProposal): Promise<void> {
    const adapter = this.adapter, history = adapter.history, origin = this.cascades.get(proposal.id);
    if (!origin || !history.current(origin) || this.closed) throw new Error("Предпросмотр устарел. Обновите его.");
    await adapter.queue.flush();
    const before = adapter.cells(adapter.queue.baseline), marker = `request:${crypto.randomUUID()}`;
    const action = history.commit("cascade", [{ key: marker, before: null, after: "cascade" }]);
    const capture = action ? history.capture(action, []) : null;
    if (!capture) return;
    const epochs = new Map([...adapter.current().keys()].map(key => [key, history.revision(key)]));
    try {
    const response = await projectRequest(`/${this.projectId}/cascade/preview`, "POST", { proposal, capture: this.wireCapture(capture) });
    if (!history.current(origin) || this.closed) throw new Error("Предпросмотр устарел. Обновите его.");
    const after = adapter.cells(response);
    const changes = [...new Set([...before.keys(), ...after.keys()])].map(key => ({ key, before: before.get(key) ?? null, after: after.get(key) ?? null }))
      .filter(change => change.before !== change.after);
    const dependencies = new Map(changes.map(change => [change.key, epochs.get(change.key) ?? 0]));
    if (history.attach({ ...capture, dependencies }, changes) !== "applied") throw new Error("Предпросмотр устарел. Обновите его.");
    adapter.changed();
    const saved = () => { this.cascades.delete(proposal.id); if (!this.closed) this.synchronizePanelAction(capture.actionId, changes); };
    try { await adapter.queue.flush(); }
    catch (error) { throw new AppliedIntentFailure(async () => { await adapter.queue.flush(); saved(); }, error); }
    saved();
    } finally { history.discardPending(capture.actionId); }
  }
  async retry(id: string, blockIds: string[]): Promise<void> {
    const history = this.adapter.history, marker = `request:${crypto.randomUUID()}`;
    const action = history.commit("rewrite", [{ key: marker, before: null, after: "retry" }]);
    const capture = action ? this.capture(action, blockIds) : null;
    if (!capture || this.closed) return;
    await this.adapter.queue.flush();
    if (await this.background({ kind: "retry", syncId: id, capture: this.wireCapture(capture) }, capture)) return;
    const response = await this.admitted(`/${this.projectId}/sync/${id}/retry`, this.wireCapture(capture), capture);
    await this.apply(operationSync(response, this.projectId, capture.actionId), capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  private async apply(sync: Sync, original: Capture): Promise<"applied" | "stale" | "conflict" | null> {
    const adapter = this.adapter;
    const [first, ...rest] = sync.proposedSteps ?? [];
    if (!sync.ready || !first) return null;
    const mutation: RichMutation = { schemaVersion: 1, projectId: this.projectId, clientMutationId: crypto.randomUUID(),
      actionId: original.actionId, kind: sync.kind === "rewrite" ? "rewrite" : "reconciliation",
      capture: { ...this.wireCapture(original), dependencies: sync.dependencies }, steps: [first, ...rest] };
    let disposition: "applied" | "stale" | "conflict" = "stale";
    let errorCode: string | null = "STALE_SYNC";
    if (!this.closed && adapter.history.current(original)) {
      try {
        await adapter.queue.flush();
        const before = adapter.cells(adapter.queue.baseline);
        const preview = await projectRequest(`/${this.projectId}/preview`, "POST", mutation);
        const after = adapter.cells(preview);
        const changes = [...new Set([...before.keys(), ...after.keys()])].filter(key => !key.startsWith("request:"))
          .map(key => ({ key, before: before.get(key) ?? null, after: after.get(key) ?? null })).filter(change => change.before !== change.after);
        const deps = new Map(original.dependencies);
        for (const change of changes) if (!deps.has(change.key)) deps.set(change.key, original.epochs.get(change.key) ?? 0);
        disposition = this.closed ? "stale" : adapter.history.attach({ ...original, dependencies: deps }, changes);
        errorCode = disposition === "applied" ? null : disposition === "conflict" ? "SYNC_HISTORY_CONFLICT" : "STALE_SYNC";
        if (disposition === "applied") { adapter.changed(); await adapter.queue.flush(); adapter.applied?.(original.actionId, changes); }
      } catch (error) { disposition = "conflict"; errorCode = error instanceof RichApiFailure ? error.code : "SYNC_PREVIEW_FAILED"; }
    }
    if (!this.closed) {
      const response = await projectRequest(`/${this.projectId}/sync/${sync.id}`, "POST", { status: disposition, errorCode });
      adapter.report(response);
    }
    return disposition;
  }
}
