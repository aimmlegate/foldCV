export type RewriteStage = "saving" | "queued" | "starting" | "running" | "applying" | "cancelling"
  | "preview" | "saved" | "no_change" | "cancelled" | "failed" | "review";
export type RewriteActivity = { actionId: string; stage: RewriteStage; startedAt: number; finishedAt: number | null; detail: string | null };

export function rewriteCancellable(stage: RewriteStage): boolean {
  return ["saving", "queued", "starting", "running"].includes(stage);
}
export const rewriteLabels: Record<RewriteStage, string> = {
  saving: "Сохраняем правки", queued: "В очереди", starting: "Начинаем",
  running: "Готовим новый текст", applying: "Применяем", cancelling: "Останавливаем",
  saved: "Текст изменён", no_change: "Без изменений", cancelled: "Отменено",
  failed: "Не удалось изменить текст", review: "Проверьте результат",
  preview: "Новый текст готов",
};

/** A server task stage as a panel stage; one this client does not know leaves the shown stage. */
export function serverRewriteStage(stage: string | null): RewriteStage | null {
  return stage === "queued" ? "queued" : stage === "generating" ? "running" : null;
}

type RewritePorts<Preview> = {
  preview: (requestId: string, stage: (stage: RewriteStage) => void) => Promise<Preview>;
  cancel: (requestId: string) => Promise<boolean>;
  activity: (activity: RewriteActivity | null) => void;
  done: (preview: Preview) => void;
  failed: (code: string) => void;
  cancelFailed: (error: unknown) => void;
};

/** One rewrite request at a time. Its reply counts only while it is the current one, so a panel reopened on another
 * selection never receives an earlier preview. */
export class RewriteRequests<Preview> {
  private current: RewriteActivity | null = null;
  constructor(private readonly ports: RewritePorts<Preview>) {}

  get running(): boolean { return this.current !== null; }
  private show(activity: RewriteActivity | null): void { this.current = activity; this.ports.activity(activity); }
  private moved(requestId: string, stage: RewriteStage): void {
    if (this.current?.actionId === requestId) this.show({ ...this.current, stage });
  }

  async submit(): Promise<void> {
    const requestId = crypto.randomUUID(), live = () => this.current?.actionId === requestId;
    this.show({ actionId: requestId, stage: "saving", startedAt: Date.now(), finishedAt: null, detail: null });
    try {
      const preview = await this.ports.preview(requestId, stage => { if (this.current?.stage !== "cancelling") this.moved(requestId, stage); });
      if (live()) this.ports.done(preview);
    } catch (error) { if (live()) this.ports.failed(error instanceof Error ? error.message : "INVALID_RESULT"); }
    finally { if (live()) this.show(null); }
  }

  /** The cancel button: a cancel that fails puts the stage back and says so, as the request is still running. */
  async cancel(requestId: string): Promise<void> {
    const stage = this.current?.stage;
    if (this.current?.actionId !== requestId || !stage) return;
    this.moved(requestId, "cancelling");
    try { if (await this.ports.cancel(requestId)) return; this.ports.cancelFailed("REQUEST_FAILED"); }
    catch (error) { this.ports.cancelFailed(error); }
    this.moved(requestId, stage);
  }

  /** The panel opens on a new selection: a running request stops and its reply no longer counts. */
  supersede(): void {
    const requestId = this.current?.actionId;
    if (requestId === undefined) return;
    this.show(null);
    this.ports.cancel(requestId).catch(() => {});
  }
}
