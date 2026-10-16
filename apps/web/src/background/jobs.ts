import type { JobProjectV1 } from "../contracts/generated/background_project_v1";
import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";
import type { JobAgentRequestV1 } from "../contracts/generated/background_agent_request_v1";
import { RichApiFailure } from "../rich/api";
import { JobsApi } from "./api";
import { sameValue } from "./wire";

export type JobsTransport = Pick<JobsApi, "project" | "projectJobs" | "read" | "submit" | "cancel" | "replay" | "proposal" | "legacy" | "conversation">
  & Partial<Pick<JobsApi, "discard">>;
export type JobsView = { project: JobProjectV1 | null; error: string | null };
export type JobsScheduler = { later: (callback: () => void) => () => void };
const scheduler: JobsScheduler = { later: callback => { const timer = setTimeout(callback, 700); return () => clearTimeout(timer); } };
export function pendingJob(job: JobSnapshotV1): boolean {
  return !["completed", "failed", "cancelled", "interrupted"].includes(job.execution)
    || ["waiting_for_sync", "ready", "committing", "outcome_unknown"].includes(job.publication);
}

/** These subscriptions belong to a project, so closing a screen cannot end its work. */
export class ProjectJobs {
  view: JobsView = { project: null, error: null };
  private readonly listeners = new Set<(view: JobsView) => void>();
  private refreshWork: Promise<void> | null = null;
  private cancelTimer: (() => void) | null = null;
  private closed = false;
  private epoch = 0;
  constructor(readonly api: JobsTransport, private readonly schedule = scheduler) {}

  subscribe(listener: (view: JobsView) => void): () => void {
    this.listeners.add(listener); listener(this.view); void this.refresh().catch(() => {});
    return () => { this.listeners.delete(listener); this.plan(); };
  }
  private publish(project: JobProjectV1 | null, error: string | null): void {
    if (this.closed || sameValue(this.view, { project, error })) return;
    this.view = { project, error }; for (const listener of this.listeners) listener(this.view);
  }
  private accept(job: JobSnapshotV1): void {
    const current = this.view.project;
    if (!current || job.submission.identity.projectId !== this.api.project || job.submission.identity.lineage !== current.lineage) throw new Error("INVALID_RESULT");
    const old = current.jobs.find(item => item.id === job.id);
    if (old && (job.executionGeneration < old.executionGeneration || job.executionGeneration === old.executionGeneration && job.eventCursor < old.eventCursor)) return;
    this.publish({ ...current, jobs: old ? current.jobs.map(item => item.id === job.id ? job : item) : [...current.jobs, job] }, null);
  }
  private plan(): void {
    this.cancelTimer?.(); this.cancelTimer = null;
    if (this.closed || !this.listeners.size && !this.view.project?.jobs.some(pendingJob)) return;
    this.cancelTimer = this.schedule.later(() => { this.cancelTimer = null; void this.refresh().catch(() => {}); });
  }
  refresh(): Promise<void> {
    if (this.closed) return Promise.resolve();
    if (this.refreshWork) return this.refreshWork;
    const work = this.load(); this.refreshWork = work;
    void work.finally(() => { if (this.refreshWork === work) this.refreshWork = null; this.plan(); }).catch(() => {});
    return work;
  }
  private async load(): Promise<void> {
    const epoch = this.epoch;
    try {
      const project = await this.api.projectJobs();
      if (this.closed || epoch !== this.epoch) return;
      if (project.projectId !== this.api.project || this.view.project && this.view.project.lineage !== project.lineage) throw new Error("INVALID_RESULT");
      const known = this.view.project;
      if (!known) this.publish({ ...project, jobs: [] }, null);
      for (const listed of project.jobs) {
        const previous = this.view.project?.jobs.find(item => item.id === listed.id);
        if (previous && previous.executionGeneration === listed.executionGeneration && previous.eventCursor >= listed.eventCursor) continue;
        let cursor = previous?.executionGeneration === listed.executionGeneration ? previous.eventCursor : 0;
        let resync = false;
        try {
          const replay = await this.api.replay(listed.id, listed.executionGeneration, cursor);
          if (this.closed || epoch !== this.epoch) return;
          for (const event of replay.events) {
            if (event.projectId !== project.projectId || event.lineage !== project.lineage || event.jobId !== listed.id || event.generation !== listed.executionGeneration) throw new Error("JOB_RESYNC_REQUIRED");
            if (event.cursor <= cursor) continue;
            if (event.type !== "cursor.gap" && event.cursor !== cursor + 1) throw new Error("JOB_RESYNC_REQUIRED");
            cursor = event.cursor; this.accept(event.snapshot);
          }
          resync = cursor < listed.eventCursor;
        } catch (error) {
          if (!(error instanceof Error) || !["INVALID_RESULT", "JOB_RESYNC_REQUIRED"].includes(error.message)) throw error;
          resync = true;
        }
        if (resync) {
          const current = await this.api.read(listed.id);
          if (this.closed || epoch !== this.epoch) return;
          this.accept(current);
        } else this.accept(listed);
      }
      const latest = this.view.project;
      if (latest) this.publish({ ...latest, jobs: latest.jobs.filter(job => project.jobs.some(listed => listed.id === job.id)),
        requestEpoch: Math.max(latest.requestEpoch, project.requestEpoch) }, null);
    } catch (error) {
      if (this.closed || epoch !== this.epoch) return;
      if (error instanceof RichApiFailure && error.code === "PROJECT_DELETED") { this.publish(null, error.code); this.close(); }
      else this.publish(this.view.project, error instanceof Error ? error.message : "JOB_REQUEST_FAILED");
      throw error;
    }
  }
  async submit(request: JobAgentRequestV1): Promise<JobSnapshotV1> {
    if (!this.view.project) await this.refresh();
    this.epoch++;
    const job = await this.api.submit(request); this.epoch++; this.accept(job); this.plan(); return job;
  }
  async stop(id: string): Promise<JobSnapshotV1> {
    if (!this.view.project) await this.refresh();
    this.epoch++;
    const job = await this.api.cancel(id); this.epoch++; this.accept(job); this.plan(); return job;
  }
  async discard(id: string): Promise<JobSnapshotV1> {
    if (!this.api.discard) throw new RichApiFailure("JOB_DISABLED");
    if (!this.view.project) await this.refresh();
    this.epoch++;
    const job = await this.api.discard(id); this.epoch++; this.accept(job); this.plan(); return job;
  }
  close(): void { this.closed = true; this.epoch++; this.cancelTimer?.(); this.cancelTimer = null; this.listeners.clear(); }
}

const projects = new Map<string, ProjectJobs>();
export function projectJobs(project: string): ProjectJobs {
  let jobs = projects.get(project);
  if (!jobs) { jobs = new ProjectJobs(new JobsApi(project)); projects.set(project, jobs); }
  return jobs;
}
