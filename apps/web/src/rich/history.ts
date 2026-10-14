export type CellValue = string | null;
export type CellChange = { key: string; before: CellValue; after: CellValue };
export type HistoryKind = "typing" | "composition" | "structure" | "panel" | "rewrite" | "cascade";
type Action = { id: string; token: number; kind: HistoryKind; group: string | null; changes: CellChange[] };
export type DependencyCapture = {
  session: string;
  actionId: string;
  actionToken: number;
  dependencies: ReadonlyMap<string, number>;
};
export type HistoryEffect = (changes: readonly CellChange[]) => void;

/** Stable cells let an inverse preserve edits to unrelated blocks and facts. */
export class SessionHistory {
  private readonly cells = new Map<string, CellValue>();
  private readonly epochs = new Map<string, number>();
  private readonly actions: Action[] = [];
  private cursor = 0;
  private sequence = 0;
  private clock = 0;
  private closed = false;

  constructor(readonly session: string, initial: ReadonlyMap<string, CellValue>, private readonly effect: HistoryEffect = () => {}) {
    for (const [key, value] of initial) this.cells.set(key, value);
  }

  read(key: string): CellValue { return this.cells.get(key) ?? null; }
  revision(key: string): number { return this.epochs.get(key) ?? 0; }
  get revisionClock(): number { return this.clock; }
  get position(): number { return this.cursor; }
  get length(): number { return this.actions.length; }
  get currentActionId(): string | null { return this.actions[this.cursor - 1]?.id ?? null; }
  retainedValues(): CellValue[] {
    return [...this.cells.values(), ...this.actions.flatMap(action => action.changes.flatMap(change => [change.before, change.after]))];
  }

  private valid(changes: readonly CellChange[]): boolean {
    return !this.closed && new Set(changes.map(change => change.key)).size === changes.length
      && changes.every(change => this.read(change.key) === change.before);
  }

  private apply(changes: readonly CellChange[]): boolean {
    if (!this.valid(changes)) return false;
    // The adapter validates and applies the whole transaction before publishing cells.
    this.effect(changes);
    for (const change of changes) {
      this.cells.set(change.key, change.after);
      this.epochs.set(change.key, ++this.clock);
    }
    return true;
  }

  commit(kind: HistoryKind, changes: readonly CellChange[], group: string | null = null): string | null {
    const effective = changes.filter(change => change.before !== change.after);
    if (!effective.length || !this.apply(effective)) return null;
    this.actions.splice(this.cursor);
    const previous = this.actions[this.cursor - 1];
    if (group !== null && previous?.group === group && previous.kind === kind) {
      for (const change of effective) {
        const old = previous.changes.find(item => item.key === change.key);
        if (old) old.after = change.after;
        else previous.changes.push({ ...change });
      }
      previous.token++;
      return previous.id;
    }
    const id = `${this.session}:${++this.sequence}`;
    this.actions.push({ id, token: 0, kind, group, changes: effective.map(change => ({ ...change })) });
    this.cursor++;
    return id;
  }

  undo(): boolean {
    const action = this.actions[this.cursor - 1];
    if (!action || !this.apply(action.changes.map(change => ({ key: change.key, before: change.after, after: change.before })))) return false;
    action.token++;
    this.cursor--;
    return true;
  }

  redo(): boolean {
    const action = this.actions[this.cursor];
    if (!action || !this.apply(action.changes)) return false;
    action.token++;
    this.cursor++;
    return true;
  }

  capture(actionId: string, keys: readonly string[]): DependencyCapture | null {
    const index = this.actions.findIndex(item => item.id === actionId);
    const action = this.actions[index];
    if (!action || this.closed) return null;
    const dependencies = new Set(keys);
    if (index >= this.cursor || this.actions.slice(index + 1, this.cursor).some(later =>
      later.changes.some(change => dependencies.has(change.key)))) return null;
    return { session: this.session, actionId, actionToken: action.token,
      dependencies: new Map(keys.map(key => [key, this.revision(key)])) };
  }

  attach(capture: DependencyCapture, changes: readonly CellChange[]): "applied" | "stale" | "conflict" {
    const index = this.actions.findIndex(action => action.id === capture.actionId);
    const action = this.actions[index];
    if (this.closed || capture.session !== this.session || index < 0 || index >= this.cursor
      || !action || action.token !== capture.actionToken
      || [...capture.dependencies].some(([key, revision]) => this.revision(key) !== revision)) return "stale";
    const writeKeys = new Set(changes.map(change => change.key));
    if (changes.some(change => !capture.dependencies.has(change.key))
      || this.actions.slice(index + 1, this.cursor).some(later => later.changes.some(change => writeKeys.has(change.key)))
      || !this.valid(changes)) return "conflict";
    if (!this.apply(changes)) return "conflict";
    for (const change of changes) {
      const old = action.changes.find(item => item.key === change.key);
      if (old) old.after = change.after;
      else action.changes.push({ ...change });
    }
    action.token++;
    // A redo branch may depend on the old result and cannot be safely replayed.
    this.actions.splice(this.cursor);
    return "applied";
  }

  current(capture: DependencyCapture): boolean {
    const index = this.actions.findIndex(action => action.id === capture.actionId), action = this.actions[index];
    return !this.closed && capture.session === this.session && index >= 0 && index < this.cursor && !!action
      && action.token === capture.actionToken && [...capture.dependencies].every(([key, revision]) => this.revision(key) === revision);
  }

  close(): void { this.closed = true; }
}
