import type { PrepareRequest } from "../contracts/generated/prepare_request";
import { prepare, PrivateOutputError, render } from "./render";
import type { Rendered } from "./render";

export type PreviewState = { status: "empty" | "rendering" | "ready" | "stale" | "error"; artifact: Rendered | null; error: string | null };
type ExportKind = "pdf" | "docx";
type Job = { epoch: number; key: string; input: PrepareRequest; exports: Set<ExportKind>; controller: AbortController };

function cancellable<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(new Error("cancelled"));
  return new Promise((resolve, reject) => {
    const abort = () => { signal.removeEventListener("abort", abort); reject(new Error("cancelled")); };
    signal.addEventListener("abort", abort, { once: true });
    void promise.then((value) => { signal.removeEventListener("abort", abort); resolve(value); },
      (error: unknown) => { signal.removeEventListener("abort", abort); reject(error); });
  });
}

export class PreviewWorkflow {
  private epoch = 0;
  private active = false;
  private activeJob: Job | null = null;
  private queued: Job | null = null;
  private current: Rendered | null = null;
  private currentKey: string | null = null;
  private cached: { key: string; artifact: Rendered } | null = null;
  private displayed: Rendered | null = null;
  private closed = false;
  readonly onChange: (state: PreviewState) => void;
  readonly prepareRequest: typeof prepare;
  readonly renderRequest: typeof render;
  readonly onExport: (artifact: Rendered, kind: ExportKind) => void;

  constructor(onChange: (state: PreviewState) => void, onExport: (artifact: Rendered, kind: ExportKind) => void,
              prepareRequest = prepare, renderRequest = render) {
    this.onChange = onChange;
    this.onExport = onExport;
    this.prepareRequest = prepareRequest;
    this.renderRequest = renderRequest;
  }

  get ready(): Rendered | null { return this.current; }

  matches(input: PrepareRequest, artifact: Rendered): boolean {
    return this.current === artifact && this.currentKey === JSON.stringify(input);
  }

  install(input: PrepareRequest, artifact: Rendered): void {
    this.invalidate();
    const key = JSON.stringify(input);
    this.cached = { key, artifact };
    this.restore(input);
  }

  invalidate(): void {
    if (this.closed) return;
    this.epoch += 1;
    this.activeJob?.controller.abort();
    this.activeJob = null;
    this.active = false;
    this.queued = null;
    this.current = null;
    this.currentKey = null;
    this.onChange({ status: this.displayed ? "stale" : "empty", artifact: this.displayed, error: null });
  }

  resetArchive(): void {
    if (this.closed) return;
    this.epoch += 1;
    this.activeJob?.controller.abort();
    this.active = false;
    this.activeJob = null;
    this.queued = null;
    this.current = null;
    this.currentKey = null;
    this.cached = null;
    this.displayed = null;
    this.onChange({ status: "empty", artifact: null, error: null });
  }

  restore(input: PrepareRequest): void {
    if (this.closed) return;
    const key = JSON.stringify(input);
    if (this.cached?.key !== key) return;
    this.current = this.cached.artifact;
    this.currentKey = key;
    this.displayed = this.cached.artifact;
    this.onChange({ status: "ready", artifact: this.current, error: null });
  }

  request(input: PrepareRequest, exportKind?: ExportKind): void {
    if (this.closed) return;
    const key = JSON.stringify(input);
    if (this.current && this.currentKey === key) {
      this.onChange({ status: "ready", artifact: this.current, error: null });
      if (exportKind) this.onExport(this.current, exportKind);
      return;
    }
    if (this.cached?.key === key) {
      this.restore(input);
      if (exportKind) this.onExport(this.cached.artifact, exportKind);
      return;
    }
    if (this.activeJob?.epoch === this.epoch && this.activeJob.key === key && !this.queued) {
      if (exportKind) this.activeJob.exports.add(exportKind);
      return;
    }
    const job: Job = { epoch: this.epoch, key, input: structuredClone(input),
      exports: new Set(exportKind ? [exportKind] : []), controller: new AbortController() };
    if (this.active) {
      this.activeJob?.controller.abort();
      this.activeJob = null;
      this.active = false;
    }
    void this.run(job);
  }

  close(): void {
    this.closed = true;
    this.epoch += 1;
    this.activeJob?.controller.abort();
    this.queued = null;
    this.current = null;
    this.currentKey = null;
    this.cached = null;
    this.displayed = null;
  }

  private async run(job: Job): Promise<void> {
    this.active = true;
    this.activeJob = job;
    this.onChange({ status: "rendering", artifact: this.displayed, error: null });
    try {
      const request = await cancellable(this.prepareRequest(job.input, job.controller.signal), job.controller.signal);
      if (request.baseRevision !== job.input.project.revision ||
          request.document.candidate.name !== job.input.presentation.name ||
          request.document.candidate.title !== job.input.presentation.title) throw new Error("preparation mismatch");
      if (this.closed || job.epoch !== this.epoch || this.activeJob !== job || this.queued) return;
      const artifact = await cancellable(this.renderRequest(request, job.controller.signal), job.controller.signal);
      if (this.closed || job.epoch !== this.epoch || this.activeJob !== job || this.queued) return;
      this.current = artifact;
      this.currentKey = job.key;
      this.cached = { key: job.key, artifact };
      this.displayed = artifact;
      this.onChange({ status: "ready", artifact, error: null });
      for (const kind of job.exports) this.onExport(artifact, kind);
    } catch (error) {
      if (!this.closed && job.epoch === this.epoch && this.activeJob === job && !this.queued)
        this.onChange({ status: "error", artifact: this.displayed, error: error instanceof PrivateOutputError ? error.message :
          "Не удалось подготовить или проверить документы. Повторите по кнопке." });
    } finally {
      if (this.activeJob === job) {
        this.active = false;
        this.activeJob = null;
        const next = this.queued;
        this.queued = null;
        if (next && !this.closed && next.epoch === this.epoch) void this.run(next);
      }
    }
  }
}
