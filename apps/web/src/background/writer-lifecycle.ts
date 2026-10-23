export type WriterMode = "normal" | "protected" | "recovering" | "read_only" | "detached" | "closed";
export type WriterTimers = { alarm: (callback: () => void, ms: number) => () => void };
export type WriterObserver = (name: "composition_end" | "local_barrier_acquired" | "final_flush_started" | "touch_watermark_durable"
  | "barrier_acked" | "adoption_started" | "draft_checkpointed" | "clean_detach_acked" | "writer_resumed") => Promise<void>;
export const timers: WriterTimers = { alarm: (callback, ms) => { const timer = setTimeout(callback, ms); return () => clearTimeout(timer); } };

/** One writer lifecycle for both V1 and V7 families: mode, stale-callback tickets and bounded barriers. */
export abstract class WriterLifecycle {
  mode: WriterMode = "closed";
  protected operation = 0;
  protected active: Promise<void> | null = null;
  constructor(protected readonly time: WriterTimers, protected readonly observe: WriterObserver) {}
  protected abstract notify(mode: WriterMode, error: string | null): void;
  protected abstract lockInput(locked: boolean): void;
  protected abstract compositionDone(): Promise<void>;
  protected abstract enterRecovery(error: unknown): void;
  protected current(ticket: number): void { if (ticket !== this.operation || this.mode !== "protected") throw new Error("WRITER_STALE_CALLBACK"); }
  protected setMode(mode: WriterMode, error: string | null = null): void { this.mode = mode; this.notify(mode, error); }
  protected bounded(work: (ticket: number) => Promise<void>, limit = 750): Promise<void> {
    if (this.active) return this.active;
    const task = (async () => {
      await this.compositionDone();
      await this.observe("composition_end");
      if (this.mode !== "normal") return;
      this.setMode("protected"); this.lockInput(true);
      const ticket = ++this.operation;
      let cancel = () => {};
      const expiry = new Promise<never>((_resolve, reject) => { cancel = this.time.alarm(() => reject(new Error("WRITER_BARRIER_TIMEOUT")), limit); });
      try { await Promise.race([work(ticket), expiry]); }
      catch (error) { this.enterRecovery(error); throw error; }
      finally {
        cancel();
        if (["protected"].includes(this.mode) && ticket === this.operation) { this.setMode("normal"); this.lockInput(false); }
      }
    })();
    this.active = task;
    void task.finally(() => { if (this.active === task) this.active = null; }).catch(() => {});
    return task;
  }
}
