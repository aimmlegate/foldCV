import type { JobIndexV1 } from "../contracts/generated/background_index_v1";
import type { JobSummaryV1 } from "../contracts/generated/background_summary_v1";
import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";
import { GlobalJobsApi } from "./api";
import { projectJobs } from "./jobs";
import { RichApiFailure } from "../rich/api";
import { active, jobKey, summary } from "./status";
import { sameValue } from "./wire";

export type JobNotice = { key: string; job: JobSummaryV1; kind: "saved" | "completed" | "review" | "cancelled" | "failed" };
export type GlobalJobsView = { enabled: boolean | null; jobs: JobSummaryV1[]; notices: JobNotice[]; error: string | null };
export type GlobalJobsTransport = { index: () => Promise<JobIndexV1>;
  stop: (project: string, id: string) => Promise<JobSnapshotV1>;
  discard: (project: string, id: string) => Promise<JobSnapshotV1> };
export type GlobalScheduler = { later: (callback: () => void, delay: number) => () => void };
const scheduler: GlobalScheduler = { later: (callback, delay) => { const timer = setTimeout(callback, delay); return () => clearTimeout(timer); } };
const api = new GlobalJobsApi();
const transport: GlobalJobsTransport = { index: () => api.index(), stop: (project, id) => projectJobs(project).stop(id),
  discard: (project, id) => projectJobs(project).discard(id) };
function noticeKind(job: JobSummaryV1): JobNotice["kind"] | null {
  return job.execution === "cancelled" ? "cancelled" : ["failed", "interrupted"].includes(job.execution) ? "failed"
    : job.publication === "needs_review" ? "review" : job.saved && job.kind !== "reconciliation" ? "saved"
    : job.kind !== "reconciliation" && job.execution === "completed" && ["none", "no_change"].includes(job.publication) ? "completed" : null;
}

export class GlobalJobs {
  view: GlobalJobsView = { enabled: null, jobs: [], notices: [], error: null };
  private readonly listeners = new Set<(view: GlobalJobsView) => void>();
  private readonly seen = new Map<string, { generation: number; phases: Set<JobNotice["kind"]> }>();
  private readonly commands = new Map<string, Promise<void>>();
  private work: Promise<void> | null = null;
  private cancelTimer: (() => void) | null = null;
  private epoch = 0;
  private closed = false;
  constructor(private readonly api: GlobalJobsTransport = transport, private readonly schedule: GlobalScheduler = scheduler) {}
  subscribe(listener: (view: GlobalJobsView) => void): () => void {
    this.listeners.add(listener); listener(this.view); void this.refresh().catch(() => {});
    return () => { this.listeners.delete(listener); this.plan(); };
  }
  private publish(view: GlobalJobsView): void {
    if (this.closed || sameValue(view, this.view)) return;
    this.view = view; for (const listener of this.listeners) listener(view);
  }
  private plan(): void {
    this.cancelTimer?.(); this.cancelTimer = null;
    if (this.closed || !this.listeners.size || this.view.enabled === false) return;
    this.cancelTimer = this.schedule.later(() => { this.cancelTimer = null; void this.refresh().catch(() => {}); },
      this.view.jobs.some(active) ? 700 : 3000);
  }
  refresh(): Promise<void> {
    if (this.closed) return Promise.resolve();
    if (this.work) return this.work;
    const work = this.load(this.epoch); this.work = work;
    void work.finally(() => { if (this.work === work) this.work = null; this.plan(); }).catch(() => {});
    return work;
  }
  private changes(rows: JobSummaryV1[], notify: boolean): void {
    const old = new Map(this.view.jobs.map(job => [jobKey(job), job])), keys = new Set(rows.map(jobKey));
    const jobs = rows.map(incoming => {
      const previous = old.get(jobKey(incoming));
      return previous && (previous.executionGeneration > incoming.executionGeneration
        || previous.executionGeneration === incoming.executionGeneration && previous.eventCursor > incoming.eventCursor) ? previous : incoming;
    });
    const current = new Map(jobs.map(job => [jobKey(job), job]));
    const notices = this.view.notices.flatMap(notice => {
      const job = current.get(jobKey(notice.job));
      return job && job.executionGeneration === notice.job.executionGeneration && noticeKind(job) === notice.kind ? [{ ...notice, job }] : [];
    });
    for (const job of jobs) {
      const key = jobKey(job), previous = old.get(key);
      let seen = this.seen.get(key);
      if (!seen || seen.generation !== job.executionGeneration) { seen = { generation: job.executionGeneration, phases: new Set() }; this.seen.set(key, seen); }
      const kind = noticeKind(job);
      if (kind && !seen.phases.has(kind)) {
        seen.phases.add(kind);
        if (notify && (!previous || previous.executionGeneration !== job.executionGeneration || !sameValue(previous, job)))
          notices.push({ key: `${key}:${String(job.executionGeneration)}:${kind}`, job, kind });
      }
    }
    for (const key of this.seen.keys()) if (!keys.has(key)) this.seen.delete(key);
    this.publish({ enabled: true, jobs, notices: notices.slice(-3), error: null });
  }
  private async load(epoch: number): Promise<void> {
    try {
      const index = await this.api.index();
      if (this.closed || epoch !== this.epoch) return;
      this.changes(index.jobs, this.view.enabled === true);
    } catch (error) {
      if (this.closed || epoch !== this.epoch) return;
      if (error instanceof RichApiFailure && error.code === "JOB_DISABLED") this.publish({ enabled: false, jobs: [], notices: [], error: null });
      else this.publish({ ...this.view, error: error instanceof Error ? error.message : "JOB_REQUEST_FAILED" });
      throw error;
    }
  }
  dismiss(key: string): void { this.publish({ ...this.view, notices: this.view.notices.filter(notice => notice.key !== key) }); }
  command(job: JobSummaryV1, action: "stop" | "discard"): Promise<void> {
    const key = jobKey(job), existing = this.commands.get(key);
    if (existing) return existing;
    this.epoch++;
    const work = Promise.resolve().then(async () => {
      try {
        const result = await this.api[action](job.projectId, job.jobId);
        if (result.id !== job.jobId || result.submission.identity.projectId !== job.projectId
          || result.submission.identity.lineage !== job.lineage) throw new RichApiFailure("INVALID_RESULT");
        if (this.closed) return;
        this.epoch++;
        if (this.view.jobs.some(row => jobKey(row) === key)) this.changes(this.view.jobs.map(row => jobKey(row) === key ? summary(result, row.projectTitle) : row), true);
      } catch (error) { if (!this.closed) this.publish({ ...this.view, error: error instanceof Error ? error.message : "JOB_REQUEST_FAILED" }); throw error; }
      finally { this.commands.delete(key); this.plan(); }
    });
    this.commands.set(key, work); return work;
  }
  close(): void { this.closed = true; this.epoch++; this.cancelTimer?.(); this.cancelTimer = null; this.listeners.clear(); }
}

const registry = new GlobalJobs();
export function globalJobs(): GlobalJobs { return registry; }
