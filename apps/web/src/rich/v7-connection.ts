import type { TemplateClipboardCaptureV1 } from "../contracts/generated/template_clipboard_capture_v1";
import type { TemplateEditPreparationV1 } from "../contracts/generated/template_edit_preparation_v1";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { TemplateRewritePreviewV1 } from "../contracts/generated/template_rewrite_preview_v1";
import type { V7Operation } from "./v7-translation";
import type { EditResultV1 } from "../contracts/generated/edit_result_v1";
import type { ProjectOpenResultV1 } from "../contracts/generated/project_open_result_v1";
import type { HistoryStateV1 } from "../contracts/generated/history_state_v1";

/** One open V7 project on the /v2 routes: the editor token, the last verified response and the server's undo state (D109).
 * Replies are parsed with JSON.parse and typed; the server validated them before sending. */
export type HistoryState = HistoryStateV1;
export type EditResult = EditResultV1;
export type OpenResult = ProjectOpenResultV1;
type Snapshot = TemplateEditPreparationV1["snapshot"];
type Selection = TemplateClipboardCaptureV1["selection"];
type Range = TemplateRewritePreviewV1["range"];
export type Fetcher = (input: string, init: RequestInit) => Promise<Response>;

export class ProjectApiFailure extends Error {
  constructor(readonly code: string, readonly status = 0, readonly body: Record<string, unknown> = {}) { super(code); }
}

export async function v2Request<T>(path: string, method = "GET", body?: unknown, fetcher: Fetcher = (input, init) => fetch(input, init)): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store" };
  if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const response = await fetcher(path, init);
  const text = await response.text();
  let value: unknown = null;
  try { value = text ? JSON.parse(text) : null; } catch { throw new ProjectApiFailure("INVALID_RESULT", response.status); }
  if (!response.ok) {
    const record = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
    const error = record["error"], code = typeof error === "object" && error !== null && typeof Reflect.get(error, "code") === "string"
      ? String(Reflect.get(error, "code")) : "REQUEST_FAILED";
    throw new ProjectApiFailure(code, response.status, record);
  }
  return value as T;
}

export class ProjectEditorConnection {
  private replacedToken = false;

  constructor(readonly project: string, private token: string, public response: TemplateProjectResponseV1, public history: HistoryState,
    private readonly fetcher: Fetcher = (input, init) => fetch(input, init)) {}

  static async open(project: string, fetcher?: Fetcher): Promise<ProjectEditorConnection> {
    const opened = await v2Request<OpenResult>(`/v2/projects/${encodeURIComponent(project)}/open`, "POST", {}, fetcher);
    return new ProjectEditorConnection(project, opened.editorToken, opened.response, opened.history, fetcher);
  }

  /** Another page took this project: this page shows a notice and sends nothing more. */
  get replaced(): boolean { return this.replacedToken; }

  private path(tail: string): string { return `/v2/projects/${encodeURIComponent(this.project)}${tail}`; }

  /** Every editing request: a replaced token blocks the page; an unknown one (service restart) re-opens once and retries. */
  private async editing<T>(send: (token: string) => Promise<T>, mutation = false): Promise<T> {
    if (this.replacedToken) throw new ProjectApiFailure("EDITOR_REPLACED", 409);
    try { return await send(this.token); }
    catch (error) {
      if (!(error instanceof ProjectApiFailure)) throw error;
      if (error.code === "EDITOR_REPLACED") { this.replacedToken = true; throw error; }
      if (error.code !== "EDITOR_TOKEN_UNKNOWN") throw error;
      await this.reopen();
      if (mutation) throw error;
      return await send(this.token);
    }
  }

  async reopen(): Promise<void> {
    const opened = await v2Request<OpenResult>(this.path("/open"), "POST", {}, this.fetcher);
    this.token = opened.editorToken;
    this.response = opened.response;
    this.history = opened.history;
  }

  async read(): Promise<TemplateProjectResponseV1> {
    this.response = await v2Request<TemplateProjectResponseV1>(this.path(""), "GET", undefined, this.fetcher);
    return this.response;
  }

  private adopt(result: EditResult): EditResult {
    this.response = result.response;
    this.history = result.history;
    return result;
  }

  async edit(preparation: TemplateEditPreparationV1, baseRevision: number): Promise<EditResult> {
    return this.adopt(await this.editing(token => v2Request<EditResult>(this.path("/edits"), "POST",
      { editorToken: token, baseRevision, preparation }, this.fetcher), true));
  }

  async step(direction: "undo" | "redo", clientMutationId: string, expectedActionId: string | null, baseRevision: number): Promise<EditResult> {
    return this.adopt(await this.editing(token => v2Request<EditResult>(this.path("/history"), "POST",
      { editorToken: token, baseRevision, direction, clientMutationId, expectedActionId }, this.fetcher), true));
  }

  async capture(clientCaptureId: string, snapshot: Snapshot, selection: Selection): Promise<{ clipboardCaptureId: string }> {
    return this.editing(token => v2Request<{ clipboardCaptureId: string }>(this.path("/clipboard"), "POST",
      { editorToken: token, clientCaptureId, snapshot, selection }, this.fetcher));
  }

  async rewritePreview(requestId: string, snapshot: Snapshot, range: Range, instruction: string): Promise<TemplateRewritePreviewV1> {
    return this.editing(token => v2Request<TemplateRewritePreviewV1>(this.path("/rewrite/preview"), "POST",
      { editorToken: token, requestId, snapshot, range, instruction }, this.fetcher));
  }

  async rewriteCancel(requestId: string): Promise<boolean> {
    const value = await this.editing(token => v2Request<{ cancelled: boolean }>(this.path("/rewrite/cancel"), "POST",
      { requestId, editorToken: token }, this.fetcher));
    return value.cancelled;
  }
}

/** Unacknowledged intents of one project, kept in IndexedDB until the server confirms them (plan 2.6). */
export type PendingIntent = { localId: string; clientMutationId: string; baseRevision: number; actionId: string; actionToken: number;
  operation: V7Operation; prior: [string, string][]; text: string; issued: TemplateEditPreparationV1 | null };
export type PendingNavigation = { direction: "undo" | "redo"; clientMutationId: string; expectedActionId: string; baseRevision: number };
export type PendingRecord = { schemaVersion: 1; project: string; intents: PendingIntent[]; locals: [string, string][];
  navigation: PendingNavigation | null };
export interface PendingStore {
  load(project: string): Promise<PendingRecord | null>;
  save(record: PendingRecord): Promise<void>;
  clear(project: string): Promise<void>;
}

export class MemoryPendingStore implements PendingStore {
  readonly records = new Map<string, PendingRecord>();
  load(project: string): Promise<PendingRecord | null> { return Promise.resolve(structuredClone(this.records.get(project) ?? null)); }
  save(record: PendingRecord): Promise<void> { this.records.set(record.project, structuredClone(record)); return Promise.resolve(); }
  clear(project: string): Promise<void> { this.records.delete(project); return Promise.resolve(); }
}

export class BrowserPendingStore implements PendingStore {
  private database: Promise<IDBDatabase> | null = null;
  private open(): Promise<IDBDatabase> {
    this.database ??= new Promise((resolve, reject) => {
      const request = indexedDB.open("foldcv-pending-edits", 1);
      request.onupgradeneeded = () => { request.result.createObjectStore("projects"); };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("DRAFT_STORAGE_FAILED"));
    });
    return this.database;
  }
  private async run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    const database = await this.open();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction("projects", mode), request = work(transaction.objectStore("projects"));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error ?? new Error("DRAFT_STORAGE_FAILED"));
      transaction.onabort = () => reject(transaction.error ?? new Error("DRAFT_STORAGE_FAILED"));
    });
  }
  async load(project: string): Promise<PendingRecord | null> {
    const value: unknown = await this.run("readonly", store => store.get(project));
    return typeof value === "object" && value !== null && Reflect.get(value, "schemaVersion") === 1 ? value as PendingRecord : null;
  }
  async save(record: PendingRecord): Promise<void> { await this.run("readwrite", store => store.put(record, record.project)); }
  async clear(project: string): Promise<void> { await this.run("readwrite", store => store.delete(project)); }
}

export function pendingStore(): PendingStore {
  return typeof indexedDB === "undefined" ? new MemoryPendingStore() : new BrowserPendingStore();
}
