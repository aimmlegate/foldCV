export class AppliedIntentFailure extends Error {
  constructor(readonly recover: () => Promise<void>, cause: unknown) {
    super("Правка применена. Повторите сохранение перед следующей правкой.", { cause });
  }
}
type Entry<T> = { intent: T; resolve: () => void; reject: (error: unknown) => void };
export type IntentState<T> = { pending: readonly T[]; paused: boolean };

export class IntentQueue<T> {
  private readonly entries: Entry<T>[] = [];
  private working: Promise<void> | null = null;
  private recovery: Promise<void> | null = null;
  private paused: AppliedIntentFailure | null = null;
  private failure: unknown = null;
  private closed = false;
  constructor(private readonly execute: (intent: T) => Promise<void>, private readonly changed: (state: IntentState<T>) => void) {}
  get busy(): boolean { return this.entries.length > 0; }
  get awaitingSave(): boolean { return this.paused !== null; }
  enqueue(intent: T): Promise<void> {
    if (this.closed) return Promise.reject(new Error("Редактор закрыт."));
    if (this.paused) return Promise.reject(this.paused);
    this.failure = null;
    const result = new Promise<void>((resolve, reject) => this.entries.push({ intent, resolve, reject }));
    this.notify(); this.start(); return result;
  }
  async drain(): Promise<void> {
    if (this.paused) await this.recover();
    while (!this.closed && this.entries.length) {
      this.start(); await this.working;
      if (this.paused) throw this.paused;
    }
    if (this.closed) throw new Error("Редактор закрыт.");
    if (this.failure) { const failure = this.failure; this.failure = null; throw failure; }
  }
  close(): Promise<void> {
    this.closed = true;
    for (const entry of this.entries.splice(0)) entry.reject(new Error("Редактор закрыт."));
    return this.working ?? Promise.resolve();
  }
  private notify(): void { if (!this.closed) this.changed({ pending: this.entries.map(entry => entry.intent), paused: this.paused !== null }); }
  private start(): void {
    if (this.working || this.paused || this.closed) return;
    this.working = this.run().finally(() => { this.working = null; if (this.entries.length && !this.paused && !this.closed) this.start(); });
  }
  private async run(): Promise<void> {
    while (!this.closed && this.entries.length) {
      const entry = this.entries[0]; if (!entry) return;
      try {
        await this.execute(entry.intent);
        if (this.closed) return;
        this.entries.shift(); entry.resolve(); this.notify();
      } catch (error) {
        if (this.closed) return;
        entry.reject(error);
        if (error instanceof AppliedIntentFailure) this.paused = error;
        else {
          this.failure = error;
          for (const unsent of this.entries.splice(0)) unsent.reject(error);
        }
        this.notify(); return;
      }
    }
  }
  private recover(): Promise<void> {
    if (this.recovery) return this.recovery;
    const paused = this.paused;
    if (!paused) return Promise.resolve();
    this.recovery = paused.recover().then(() => {
      if (this.closed) return;
      this.entries.shift()?.resolve(); this.paused = null; this.notify();
    }).finally(() => { this.recovery = null; });
    return this.recovery;
  }
}
