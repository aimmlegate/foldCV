export type CellValue = string | null;
export type CellChange = { key: string; before: CellValue; after: CellValue };
export type HistoryKind = "typing" | "composition" | "structure" | "panel" | "rewrite" | "cascade";
type Action = { id: string; token: number; kind: HistoryKind; group: string | null; changes: CellChange[]; lastNavigationToken: number };
export type DependencyCapture = {
  session: string;
  actionId: string;
  actionToken: number;
  dependencies: ReadonlyMap<string, number>;
};
export type HistoryEffect = (changes: readonly CellChange[]) => void;
export type HistoryEffectContext = { mode: "ordinary" | "prepared" | "assistant_history"; actionId: string | null;
  actionToken?: number; kind: HistoryKind | "undo" | "redo" | "reconciliation" };
export type HistoryReservation = { id: string; actionId: string; clock: number; position: number };

/** Stable cells let an inverse preserve edits to unrelated blocks and facts. */
export class SessionHistory {
  private readonly cells = new Map<string, CellValue>();
  private readonly epochs = new Map<string, number>();
  private readonly actions: Action[] = [];
  private cursor = 0;
  private sequence = 0;
  private clock = 0;
  private closed = false;
  private reservation: HistoryReservation | null = null;
  private reservedNavigation: { reservation: HistoryReservation; direction: "undo" | "redo"; actionId: string } | null = null;
  private readonly assistantActions = new Set<string>();

  constructor(readonly session: string, initial: ReadonlyMap<string, CellValue>,
    private readonly effect: (changes: readonly CellChange[], context: HistoryEffectContext) => void = () => {},
    private readonly allowed: (context: HistoryEffectContext) => boolean = () => true,
    private readonly actionPrefix: string = session,
    private readonly retention: "local" | "server" = "local") {
    for (const [key, value] of initial) this.cells.set(key, value);
  }

  read(key: string): CellValue { return this.cells.get(key) ?? null; }
  revision(key: string): number { return this.epochs.get(key) ?? 0; }
  get revisionClock(): number { return this.clock; }
  get position(): number { return this.cursor; }
  get length(): number { return this.actions.length; }
  get currentActionId(): string | null { return this.actions[this.cursor - 1]?.id ?? null; }
  actionFor(direction: "undo" | "redo"): string | null { return this.actions[direction === "undo" ? this.cursor - 1 : this.cursor]?.id ?? null; }
  retainedValues(): CellValue[] {
    return [...this.cells.values(), ...this.actions.flatMap(action => action.changes.flatMap(change => [change.before, change.after]))];
  }

  discardPending(actionId: string): boolean {
    if (this.retention === "server") return false;
    const index = this.actions.findIndex(action => action.id === actionId), action = this.actions[index];
    if (!action || action.changes.some(change => !change.key.startsWith("request:") || change.before !== null)) return false;
    const changes = action.changes.map(change => ({ key: change.key, before: this.read(change.key), after: null }));
    if (!this.apply(changes)) return false;
    this.actions.splice(index, 1); if (index < this.cursor) this.cursor--;
    return true;
  }

  private valid(changes: readonly CellChange[]): boolean {
    return !this.closed && new Set(changes.map(change => change.key)).size === changes.length
      && changes.every(change => this.read(change.key) === change.before);
  }

  private apply(changes: readonly CellChange[], context: HistoryEffectContext = { mode: "ordinary", actionId: null, kind: "typing" },
    reservation: HistoryReservation | null = null): boolean {
    if (this.reservation !== reservation || !this.valid(changes) || !this.allowed(context)) return false;
    // The adapter validates and applies the whole transaction before publishing cells.
    this.effect(changes, context);
    for (const change of changes) {
      this.cells.set(change.key, change.after);
      this.epochs.set(change.key, ++this.clock);
    }
    return true;
  }

  commit(kind: HistoryKind, changes: readonly CellChange[], group: string | null = null): string | null {
    const effective = changes.filter(change => change.before !== change.after);
    if (!effective.length && this.retention === "local") return null;
    const previous = this.actions[this.cursor - 1];
    const coalesces = group !== null && previous?.group === group && previous.kind === kind
      && (this.retention === "local" || previous.lastNavigationToken < 0);
    const id = coalesces ? previous.id : `${this.actionPrefix}:${this.sequence + 1}`;
    if (!this.apply(effective, { mode: "ordinary", actionId: id, actionToken: coalesces ? previous.token + 1 : 0, kind })) return null;
    this.actions.splice(this.cursor);
    if (coalesces) {
      for (const change of effective) {
        const old = previous.changes.find(item => item.key === change.key);
        if (old) old.after = change.after;
        else previous.changes.push({ ...change });
      }
      previous.token++;
      previous.changes = previous.changes.filter(change => change.before !== change.after);
      if (!previous.changes.length && this.retention === "local") {
        this.actions.splice(--this.cursor, 1);
        return null;
      }
      return previous.id;
    }
    this.sequence++;
    this.actions.push({ id, token: 0, kind, group, changes: effective.map(change => ({ ...change })), lastNavigationToken: -1 });
    this.cursor++;
    return id;
  }

  undo(): boolean {
    if (this.retention === "server") return false;
    const action = this.actions[this.cursor - 1];
    if (!action || !this.apply(action.changes.map(change => ({ key: change.key, before: change.after, after: change.before })),
      { mode: this.assistantActions.has(action.id) ? "assistant_history" : "ordinary", actionId: action.id, kind: "undo" })) return false;
    action.token++;
    action.lastNavigationToken = action.token;
    this.cursor--;
    return true;
  }

  navigation(direction: "undo" | "redo"): { actionId: string; changes: CellChange[] } | null {
    const action = this.actions[direction === "undo" ? this.cursor - 1 : this.cursor];
    if (this.closed || !action) return null;
    const changes = direction === "undo" ? action.changes.map(change => ({ key: change.key, before: change.after, after: change.before }))
      : action.changes.map(change => ({ ...change }));
    return this.valid(changes) ? { actionId: action.id, changes } : null;
  }

  navigationMatches(direction: "undo" | "redo", changes: readonly CellChange[]): boolean {
    const expected = this.navigation(direction)?.changes.filter(change => !change.key.startsWith("request:"));
    return expected !== undefined && expected.length === changes.length && expected.every(change => changes.some(actual =>
      actual.key === change.key && actual.before === change.before && actual.after === change.after));
  }

  reserveNavigation(direction: "undo" | "redo", requestId: string): HistoryReservation | null {
    if (this.retention !== "server" || !this.navigation(direction)) return null;
    const reservation = this.reserve(requestId);
    const action = this.actions[direction === "undo" ? this.cursor - 1 : this.cursor];
    if (!reservation || !action) return null;
    action.token++;
    action.lastNavigationToken = action.token;
    this.reservedNavigation = { reservation, direction, actionId: action.id };
    return reservation;
  }

  /** Visible equality cannot decide whether an authority or issue edit was a no-op. */
  acknowledgeServerAction(actionId: string, actionToken: number, retained: boolean): "retained" | "removed" | "pending" | "stale" {
    const index = this.actions.findIndex(action => action.id === actionId), action = this.actions[index];
    if (this.retention !== "server" || this.closed || this.reservation || !action || !Number.isSafeInteger(actionToken)
      || actionToken < 0 || actionToken > action.token || actionToken <= action.lastNavigationToken) return "stale";
    if (actionToken < action.token) return "pending";
    if (retained) return "retained";
    if (action.changes.length) return "stale";
    this.actions.splice(index, 1);
    if (index < this.cursor) this.cursor--;
    return "removed";
  }

  publishNavigation(reservation: HistoryReservation, direction: "undo" | "redo", changes: readonly CellChange[]): boolean {
    const value = this.navigation(direction), action = this.actions[direction === "undo" ? this.cursor - 1 : this.cursor];
    if (!value || !action || !this.reserved(reservation) || !this.navigationMatches(direction, changes)
      || this.retention === "server" && (this.reservedNavigation?.reservation !== reservation
        || this.reservedNavigation.direction !== direction || this.reservedNavigation.actionId !== action.id)
      || !this.apply(value.changes, { mode: "prepared", actionId: action.id, actionToken: action.token + 1, kind: direction }, reservation)) return false;
    action.token++;
    action.lastNavigationToken = action.token;
    this.cursor += direction === "undo" ? -1 : 1;
    this.reservation = null;
    this.reservedNavigation = null;
    return true;
  }

  redo(): boolean {
    if (this.retention === "server") return false;
    const action = this.actions[this.cursor];
    if (!action || !this.apply(action.changes,
      { mode: this.assistantActions.has(action.id) ? "assistant_history" : "ordinary", actionId: action.id, kind: "redo" })) return false;
    action.token++;
    action.lastNavigationToken = action.token;
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
    if (!this.apply(changes, { mode: "ordinary", actionId: action.id, actionToken: action.token + 1, kind: "reconciliation" })) return "conflict";
    for (const change of changes) {
      const old = action.changes.find(item => item.key === change.key);
      if (old) old.after = change.after;
      else action.changes.push({ ...change });
    }
    if (this.retention === "server") action.changes = action.changes.filter(change => change.before !== change.after);
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

  reserve(actionId: string): HistoryReservation | null {
    if (this.closed || this.reservation || this.actions.some(action => action.id === actionId)) return null;
    this.reservation = { id: crypto.randomUUID(), actionId, clock: this.clock, position: this.cursor };
    return this.reservation;
  }

  reserved(reservation: HistoryReservation): boolean {
    return !this.closed && this.reservation === reservation && reservation.clock === this.clock && reservation.position === this.cursor;
  }

  publish(reservation: HistoryReservation, changes: readonly CellChange[]): boolean {
    const effective = changes.filter(change => change.before !== change.after);
    if (this.reservedNavigation || (!effective.length && this.retention === "local") || !this.reserved(reservation) || !this.apply(effective,
      { mode: "prepared", actionId: reservation.actionId, kind: "structure" }, reservation)) return false;
    this.actions.splice(this.cursor);
    this.actions.push({ id: reservation.actionId, token: 0, kind: "structure", group: null,
      changes: effective.map(change => ({ ...change })), lastNavigationToken: -1 });
    this.assistantActions.add(reservation.actionId);
    this.cursor++;
    this.reservation = null;
    return true;
  }

  discard(reservation: HistoryReservation): void {
    if (this.reservation === reservation) { this.reservation = null; this.reservedNavigation = null; }
  }

  adoptExisting(reservation: HistoryReservation, changes: readonly CellChange[]): boolean {
    const effective = changes.filter(change => change.before !== change.after);
    if (this.reservedNavigation || (!effective.length && this.retention === "local") || !this.reserved(reservation) || new Set(effective.map(change => change.key)).size !== effective.length
      || effective.some(change => this.read(change.key) !== change.after)) return false;
    this.actions.splice(this.cursor);
    this.actions.push({ id: reservation.actionId, token: 0, kind: "structure", group: null, changes: effective.map(change => ({ ...change })), lastNavigationToken: -1 });
    this.assistantActions.add(reservation.actionId);
    this.cursor++; this.reservation = null;
    return true;
  }

  reconcile(changes: readonly CellChange[]): boolean {
    return this.apply(changes, { mode: "prepared", actionId: null, kind: "structure" });
  }

  close(): void { this.closed = true; this.reservation = null; this.reservedNavigation = null; }
}
