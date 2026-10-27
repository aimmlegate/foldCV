export type ReadCapture = Readonly<{ projectId: string; selectionEpoch: number; requestId: number }>;

export function readCaptureCurrent(captured: ReadCapture, current: ReadCapture): boolean {
  return captured.projectId === current.projectId && captured.selectionEpoch === current.selectionEpoch && captured.requestId === current.requestId;
}

export type WorkspaceReadSlot = "export" | "archive";

/** Pending selection reads are separate from the opening still shown after a failed load. */
export class WorkspaceReads {
  private epoch = 0;
  private sequence = 0;
  private active: ReadCapture | null = null;
  private loading: ReadCapture | null = null;
  private replacing = false;
  private readonly slots = new Map<WorkspaceReadSlot, ReadCapture>();

  get version(): number { return this.epoch; }
  get opening(): ReadCapture | null { return this.active ? { ...this.active } : null; }
  beginSelection(projectId: string): ReadCapture {
    const capture = { projectId, selectionEpoch: ++this.epoch, requestId: ++this.sequence };
    this.loading = capture; this.replacing = false;
    this.slots.clear();
    return { ...capture };
  }
  selectionCurrent(capture: ReadCapture): boolean { return this.loading !== null && readCaptureCurrent(this.loading, capture); }
  adoptSelection(capture: ReadCapture): boolean {
    if (!this.selectionCurrent(capture)) return false;
    this.active = { ...capture }; this.loading = null;
    return true;
  }
  cancelSelection(capture: ReadCapture): void { if (this.selectionCurrent(capture)) this.loading = null; }
  beginReplacement(): number { this.epoch++; this.loading = null; this.replacing = true; this.slots.clear(); return this.epoch; }
  replacementCurrent(version: number): boolean { return this.replacing && version === this.epoch; }
  cancelReplacement(version: number): void { if (this.replacementCurrent(version)) this.replacing = false; }
  matchesOpening(capture: ReadCapture | null): boolean {
    return capture !== null && this.active !== null && capture.projectId === this.active.projectId
      && capture.selectionEpoch === this.active.selectionEpoch;
  }
  begin(slot: WorkspaceReadSlot): ReadCapture | null {
    if (!this.active || this.loading || this.replacing) return null;
    const capture = { ...this.active, requestId: ++this.sequence };
    this.slots.set(slot, capture);
    return { ...capture };
  }
  current(slot: WorkspaceReadSlot, capture: ReadCapture): boolean {
    const expected = this.slots.get(slot);
    return !this.loading && !this.replacing && this.matchesOpening(capture) && expected !== undefined && readCaptureCurrent(expected, capture);
  }
  clear(): void { this.epoch++; this.active = null; this.loading = null; this.replacing = false; this.slots.clear(); }
}
