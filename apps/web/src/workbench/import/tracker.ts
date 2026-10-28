import { cancelImport, lastImportOperation, projectTasks, resumeImport, startImport, type ImportOptions,
  type ProjectTask } from "../../projects/api";
import { importView, operationOf, type ImportEntry } from "./progress";

export type ImportApi = {
  tasks: typeof projectTasks; cancel: typeof cancelImport; resume: typeof resumeImport; start: typeof startImport;
  operation: typeof lastImportOperation;
};
const defaultApi: ImportApi = { tasks: projectTasks, cancel: cancelImport, resume: resumeImport, start: startImport,
  operation: lastImportOperation };

/** Consecutive failed status reads before the screen shows the failure instead of waiting. */
export const POLL_FAILURES = 3;

function codeOf(error: unknown): string {
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code
    : error instanceof Error ? error.message : "REQUEST_FAILED";
}

/** Follows the imports of several projects at once. The service runs one import per project and queues the others
 * behind the shared model permit, so each project is read on its own and nothing here blocks the workspace. */
export class ImportTracker {
  private readonly entries = new Map<string, ImportEntry>();
  private readonly options = new Map<string, ImportOptions>();
  private readonly misses = new Map<string, number>();
  private readonly reading = new Set<string>();
  private loop: Promise<void> | null = null;
  private closed = false;
  private readonly api: ImportApi;
  private readonly now: () => number;
  private readonly wait: (milliseconds: number) => Promise<void>;
  private readonly interval: number;

  constructor(private readonly changed: (entries: ReadonlyMap<string, ImportEntry>) => void,
              private readonly finished: (entry: ImportEntry) => void = () => {},
              { api = defaultApi, now = Date.now, wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)),
                interval = 1000 }: { api?: ImportApi; now?: () => number; wait?: (milliseconds: number) => Promise<void>;
                interval?: number } = {}) {
    this.api = api; this.now = now; this.wait = wait; this.interval = interval;
  }

  get(projectId: string): ImportEntry | undefined { return this.entries.get(projectId); }

  /** Follow this task of the project; a newer task replaces the one followed before. */
  track(projectId: string, task: ProjectTask, title: string, options?: ImportOptions): void {
    if (this.closed) return;
    if (options) this.options.set(projectId, options);
    const previous = this.entries.get(projectId);
    this.misses.delete(projectId);
    this.put({ projectId, title: previous?.title ?? title, task, polledAt: this.now(), failure: null, stopping: false, retrying: false });
    const entry = this.entries.get(projectId);
    if (entry && task.state !== "running") this.finished(entry);
    this.start();
  }

  async stop(projectId: string): Promise<void> {
    const entry = this.entries.get(projectId);
    if (!entry || entry.task.state !== "running" || entry.stopping) return;
    this.put({ ...entry, stopping: true });
    try {
      const task = await this.api.cancel(projectId, entry.task.id);
      this.settle(projectId, entry.task.id, current => ({ ...current, task, stopping: false, polledAt: this.now() }));
    } catch (error) {
      this.settle(projectId, entry.task.id, current => ({ ...current, stopping: false, failure: codeOf(error) }));
    }
  }

  /** Stop a stalled run if it still runs, then continue the project's import from its operation, or start it again. */
  async retry(projectId: string): Promise<void> {
    const entry = this.entries.get(projectId);
    const view = entry ? importView(entry, this.now()) : null;
    // A healthy run keeps its task; Retry is offered only for stalled, failed and stopped imports.
    if (!entry || !view || entry.retrying || view.kind === "running" || view.kind === "succeeded") return;
    this.put({ ...entry, retrying: true });
    try {
      if (entry.task.state === "running" && entry.failure) {
        // Only the status reads failed: read again instead of touching the task.
        this.misses.delete(projectId);
        this.settle(projectId, entry.task.id, current => ({ ...current, failure: null, retrying: false, polledAt: this.now() }));
        this.start();
        return;
      }
      if (entry.task.state === "running" && view.kind === "stalled")
        await this.api.cancel(projectId, entry.task.id).catch(() => null);
      const operation = operationOf(entry.task) ?? await this.api.operation(projectId);
      const options = this.options.get(projectId) ?? { allowTextRewrite: true, effort: null };
      const task = operation ? await this.api.resume(projectId, operation)
        : await this.api.start(projectId, { clientRequestId: crypto.randomUUID(), ...options });
      if (this.closed || this.entries.get(projectId)?.task.id !== entry.task.id) return;
      this.track(projectId, task, entry.title);
    } catch (error) {
      this.settle(projectId, entry.task.id, current => ({ ...current, retrying: false, failure: codeOf(error) }));
    }
  }

  /** Close the entry; a run that still holds its task is stopped first. */
  dismiss(projectId: string): void {
    const entry = this.entries.get(projectId);
    if (!entry) return;
    if (entry.task.state === "running") void this.api.cancel(projectId, entry.task.id).catch(() => null);
    this.entries.delete(projectId); this.options.delete(projectId); this.misses.delete(projectId);
    this.changed(new Map(this.entries));
  }

  close(): void { this.closed = true; this.entries.clear(); }

  private put(entry: ImportEntry): void {
    if (this.closed) return;
    this.entries.set(entry.projectId, entry);
    this.changed(new Map(this.entries));
  }

  /** Apply a result only to the task it was read for; a retry or a newer start may have replaced it meanwhile. */
  private settle(projectId: string, taskId: string, next: (entry: ImportEntry) => ImportEntry): ImportEntry | null {
    const current = this.entries.get(projectId);
    if (!current || current.task.id !== taskId) return null;
    const updated = next(current);
    this.put(updated);
    return updated;
  }

  private start(): void {
    if (this.loop || this.closed) return;
    this.loop = this.run().finally(() => { this.loop = null; if (this.following().length) this.start(); });
  }

  private following(): ImportEntry[] {
    return [...this.entries.values()].filter(entry => entry.task.state === "running" && !entry.failure);
  }

  private async run(): Promise<void> {
    while (!this.closed && this.following().length) {
      await this.wait(this.interval);
      if (this.closed) return;
      // Each project is read on its own: a reply that never comes holds only its own project.
      for (const entry of this.following()) {
        if (this.reading.has(entry.projectId)) continue;
        this.reading.add(entry.projectId);
        void this.poll(entry).finally(() => this.reading.delete(entry.projectId));
      }
    }
  }

  private async poll(entry: ImportEntry): Promise<void> {
    const { projectId } = entry, taskId = entry.task.id;
    try {
      const tasks = await this.api.tasks(projectId);
      let task = tasks.find(item => item.id === taskId);
      if (!task) {
        // The service restarted and lost its in-memory task: continue the saved operation once.
        const operation = operationOf(entry.task);
        if (!operation) throw new Error("PROCESS_FAILED");
        task = await this.api.resume(projectId, operation);
        if (this.entries.get(projectId)?.task.id === taskId) this.track(projectId, task, entry.title);
        return;
      }
      this.misses.delete(projectId);
      const updated = this.settle(projectId, taskId, current => ({ ...current, task: task ?? current.task, polledAt: this.now(), failure: null }));
      if (updated && updated.task.state !== "running") this.finished(updated);
    } catch (error) {
      const misses = (this.misses.get(projectId) ?? 0) + 1;
      this.misses.set(projectId, misses);
      if (misses >= POLL_FAILURES) this.settle(projectId, taskId, current => ({ ...current, failure: codeOf(error) }));
    }
  }
}
