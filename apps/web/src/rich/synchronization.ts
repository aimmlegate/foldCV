import type { RichCompletionRequest } from "../contracts/generated/rich_completion_request";
import type { RichSelection } from "../contracts/generated/rich_selection";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichPanelRequest } from "../contracts/generated/rich_panel_request";
import { projectRequest, RichApiFailure } from "./api";
import type { CellValue, DependencyCapture, SessionHistory } from "./history";
import type { RichBlock, RichSaveQueue } from "./save-queue";

type Sync = RichProjectResponse["workspace"]["syncRecords"][number];
type Capture = DependencyCapture & { epochs: ReadonlyMap<string, number> };
export async function selectionChecksum(document: RichDocumentV1, selection: RichSelection): Promise<string> {
  const blocks = new Map<string, RichBlock>();
  function visit(items: RichBlock[]) { for (const block of items) { blocks.set(block.id, block); visit(block.children); } }
  document.regions.forEach(region => visit(region.blocks));
  const text = (content: RichBlock["content"]): string => typeof content === "string" ? content : Array.isArray(content)
    ? content.map(span => span.type === "link" ? span.content.map(part => part.text).join("") : span.text).join("") : "";
  let result = "";
  for (const id of selection.blockIds) {
    const block = blocks.get(id); if (!block) throw new Error("STALE_SELECTION");
    if (block.type === "table") {
      const cells = block.content.rows.flatMap(row => row.cells), first = id === selection.anchor.blockId ? cells.findIndex(cell => cell.id === selection.anchor.cellId) : 0;
      const last = id === selection.head.blockId ? cells.findIndex(cell => cell.id === selection.head.cellId) : cells.length - 1;
      for (const cell of cells.slice(first, last + 1)) {
        const value = text(cell.content); result += value.slice(id === selection.anchor.blockId && cell.id === selection.anchor.cellId ? selection.anchor.offset : 0,
          id === selection.head.blockId && cell.id === selection.head.cellId ? selection.head.offset : value.length);
      }
    } else {
      const value = text(block.type === "image" ? block.props.caption : block.content);
      result += selection.kind === "blocks" ? value : value.slice(id === selection.anchor.blockId ? selection.anchor.offset : 0,
        id === selection.head.blockId ? selection.head.offset : value.length);
    }
  }
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(result));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
export type SyncAdapter = {
  history: SessionHistory; queue: RichSaveQueue;
  current: () => ReadonlyMap<string, CellValue>;
  cells: (response: RichProjectResponse) => Map<string, CellValue>;
  changed: () => void; report: (response: RichProjectResponse) => void;
  failed?: (error: unknown) => void;
};
export type PanelCommand = Omit<RichPanelRequest, "capture" | "factsRevision" | "documentRevision">;
export class RichSynchronization {
  private closed = false;
  private readonly active = new Map<string, Capture>();
  constructor(private readonly adapter: SyncAdapter, private readonly projectId: string) {}
  close(): void { this.closed = true; this.invalidate(); }
  invalidate(): void {
    for (const [id, capture] of this.active) if (this.closed || !this.adapter.history.current(capture)) {
      this.active.delete(id);
      void projectRequest(`/${this.projectId}/cancel-action`, "POST", this.wireCapture(capture)).catch(() => {});
    }
  }
  private async admitted(path: string, body: unknown, capture: Capture): Promise<RichProjectResponse> {
    this.active.set(capture.actionId, capture);
    try { return await projectRequest(path, "POST", body); }
    finally { this.active.delete(capture.actionId); }
  }
  private capture(action: string, blockIds: string[]): Capture | null {
    const values = this.adapter.current(), records = new Set<string>(), keys = new Set<string>();
    for (const [key, value] of values) {
      if (key.startsWith("region:")) keys.add(key);
      if (!key.startsWith("block:") || !value) continue;
      const stored: unknown = JSON.parse(value);
      if (typeof stored !== "object" || stored === null || !("block" in stored)) continue;
      if (blockIds.includes(key.slice(6))) {
        keys.add(key);
        // IDs, rather than matching prose, select related working records.
        const collect = (item: unknown) => {
          if (Array.isArray(item)) item.forEach(collect);
          else if (typeof item === "object" && item !== null) {
            if ("recordId" in item && typeof item.recordId === "string") records.add(item.recordId);
            Object.values(item).forEach(collect);
          }
        };
        collect(stored);
      } else if ("children" in stored && Array.isArray(stored.children) && stored.children.some((id: unknown) => typeof id === "string" && blockIds.includes(id))) keys.add(key);
    }
    for (const key of values.keys()) if ([...records].some(id => key === `fact:${id}` || key.startsWith("fact-field:") && key.includes(JSON.stringify(id)))) keys.add(key);
    const capture = this.adapter.history.capture(action, [...keys]);
    return capture ? { ...capture, epochs: new Map([...values.keys()].map(key => [key, this.adapter.history.revision(key)])) } : null;
  }
  private wireCapture(capture: DependencyCapture): RichMutation["capture"] {
    return { sessionId: capture.session, actionId: capture.actionId, actionToken: capture.actionToken, dependencies: [] };
  }
  async complete(action: string, blockIds: string[], movedIds: string[], removedFields: RichCompletionRequest["removedFields"], interpret = true, removedRecordIds: string[] = []): Promise<void> {
    const capture = this.capture(action, blockIds);
    if (!capture || this.closed) return;
    await this.adapter.queue.flush();
    if (!this.adapter.history.current(capture) || this.closed) return;
    const response = await this.admitted(`/${this.projectId}/completion`, {
      capture: this.wireCapture(capture), blockIds, movedIds, removedFields, removedRecordIds, interpret } satisfies RichCompletionRequest, capture);
    const sync = response.workspace.syncRecords.at(-1);
    if (sync) await this.apply(sync, capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async rewrite(selection: RichSelection, instruction: string): Promise<void> {
    const marker = `request:${crypto.randomUUID()}`, history = this.adapter.history;
    const action = history.commit("rewrite", [{ key: marker, before: null, after: "pending" }]);
    if (!action) return;
    const capture = this.capture(action, selection.blockIds);
    if (!capture) return;
    await this.adapter.queue.flush();
    if (!history.current(capture) || this.closed) return;
    const project = this.adapter.queue.baseline.workspace.project;
    if (!project) return;
    selection.textSha256 = await selectionChecksum(project.document, selection);
    const blocks = new Map<string, number>();
    function visit(items: RichBlock[]) { for (const block of items) { blocks.set(block.id, block.revision); visit(block.children); } }
    project.document.regions.forEach(region => visit(region.blocks));
    selection.capture = { ...this.wireCapture(capture), dependencies: selection.blockIds.map(id => ({ kind: "block", id, revision: blocks.get(id) ?? 1, fingerprint: null })) };
    const response = await this.admitted(`/${this.projectId}/rewrite`, { selection, instruction }, capture);
    const sync = response.workspace.syncRecords.at(-1);
    if (sync) await this.apply(sync, capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async resolve(id: string): Promise<void> {
    const history = this.adapter.history, marker = `request:${crypto.randomUUID()}`;
    const action = history.commit("panel", [{ key: marker, before: null, after: "resolve" }]);
    if (!action || this.closed) return;
    await this.adapter.queue.flush();
    const response = await projectRequest(`/${this.projectId}/sync/${id}/resolve`, "POST", {
      sessionId: history.session, actionId: action, actionToken: 0, dependencies: [] });
    const sync = response.workspace.syncRecords.at(-1), capture = sync ? this.capture(action, sync.blockIds) : null;
    if (sync && capture) await this.apply(sync, capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async panel(command: PanelCommand): Promise<void> {
    const adapter = this.adapter, history = adapter.history;
    await adapter.queue.flush();
    if (this.closed) return;
    const before = adapter.cells(adapter.queue.baseline), project = adapter.queue.baseline.workspace.project;
    if (!project) return;
    const marker = `request:${crypto.randomUUID()}`, action = history.commit("panel", [{ key: marker, before: null, after: "panel" }]);
    const initial = action ? history.capture(action, []) : null;
    const epochs = new Map([...adapter.current().keys()].map(key => [key, history.revision(key)]));
    if (!initial) return;
    const response = await projectRequest(`/${this.projectId}/panel/preview`, "POST", { ...command,
      factsRevision: project.facts.revision, documentRevision: project.document.revision, capture: this.wireCapture(initial) } satisfies RichPanelRequest);
    const after = adapter.cells(response);
    const changes = [...new Set([...before.keys(), ...after.keys()])].map(key => ({ key, before: before.get(key) ?? null, after: after.get(key) ?? null }))
      .filter(change => change.before !== change.after);
    const dependencies = new Map(changes.map(change => [change.key, epochs.get(change.key) ?? 0]));
    if (this.closed || history.attach({ ...initial, dependencies }, changes) !== "applied") throw new Error("Изменения уже обновились. Повторите правку.");
    adapter.changed(); await adapter.queue.flush();
    const records = new Set<string>();
    for (const change of changes) {
      if (change.key.startsWith("fact:")) records.add(change.key.slice(5));
      if (change.key.startsWith("fact-field:")) {
        const pair: unknown = JSON.parse(change.key.slice(11));
        if (Array.isArray(pair) && typeof pair[0] === "string") records.add(pair[0]);
      }
    }
    const ids = [...adapter.current()].filter(([key, value]) => key.startsWith("block:") && value && [...records].some(id => value.includes(JSON.stringify(id))))
      .map(([key]) => key.slice(6));
    const capture = this.capture(initial.actionId, ids);
    if (capture && records.size) void this.panelSync(capture, [...records]).catch(error => adapter.failed?.(error));
  }
  private async panelSync(capture: Capture, records: string[]): Promise<void> {
    const response = await this.admitted(`/${this.projectId}/panel/sync`, { capture: this.wireCapture(capture), recordIds: records }, capture);
    const sync = response.workspace.syncRecords.at(-1);
    if (sync) await this.apply(sync, capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  async retry(id: string, blockIds: string[]): Promise<void> {
    const history = this.adapter.history, marker = `request:${crypto.randomUUID()}`;
    const action = history.commit("rewrite", [{ key: marker, before: null, after: "retry" }]);
    const capture = action ? this.capture(action, blockIds) : null;
    if (!capture || this.closed) return;
    await this.adapter.queue.flush();
    const response = await this.admitted(`/${this.projectId}/sync/${id}/retry`, this.wireCapture(capture), capture);
    const sync = response.workspace.syncRecords.at(-1);
    if (sync) await this.apply(sync, capture);
    if (!this.closed) this.adapter.report(await projectRequest(`/${this.projectId}`));
  }
  private async apply(sync: Sync, original: Capture): Promise<void> {
    const adapter = this.adapter;
    const [first, ...rest] = sync.proposedSteps ?? [];
    if (!sync.ready || !first) return;
    const mutation: RichMutation = { schemaVersion: 1, projectId: this.projectId, clientMutationId: crypto.randomUUID(),
      actionId: original.actionId, kind: sync.kind === "rewrite" ? "rewrite" : "reconciliation",
      capture: { ...this.wireCapture(original), dependencies: sync.dependencies }, steps: [first, ...rest] };
    let disposition: "applied" | "stale" | "conflict" = "stale";
    let errorCode: string | null = "STALE_SYNC";
    if (!this.closed && adapter.history.current(original)) {
      try {
        await adapter.queue.flush();
        const before = adapter.cells(adapter.queue.baseline);
        const preview = await projectRequest(`/${this.projectId}/preview`, "POST", mutation);
        const after = adapter.cells(preview);
        const changes = [...new Set([...before.keys(), ...after.keys()])].filter(key => !key.startsWith("request:"))
          .map(key => ({ key, before: before.get(key) ?? null, after: after.get(key) ?? null })).filter(change => change.before !== change.after);
        const deps = new Map(original.dependencies);
        for (const change of changes) if (!deps.has(change.key)) deps.set(change.key, original.epochs.get(change.key) ?? 0);
        disposition = this.closed ? "stale" : adapter.history.attach({ ...original, dependencies: deps }, changes);
        errorCode = disposition === "applied" ? null : disposition === "conflict" ? "SYNC_HISTORY_CONFLICT" : "STALE_SYNC";
        if (disposition === "applied") { adapter.changed(); await adapter.queue.flush(); }
      } catch (error) { disposition = "conflict"; errorCode = error instanceof RichApiFailure ? error.code : "SYNC_PREVIEW_FAILED"; }
    }
    if (!this.closed) {
      const response = await projectRequest(`/${this.projectId}/sync/${sync.id}`, "POST", { status: disposition, errorCode });
      adapter.report(response);
    }
  }
}
