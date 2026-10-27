import type { TemplateClipboardCaptureV1 } from "../contracts/generated/template_clipboard_capture_v1";
import type { TemplateEditPreparationV1 } from "../contracts/generated/template_edit_preparation_v1";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { TemplateRewritePreviewV1 } from "../contracts/generated/template_rewrite_preview_v1";
import type { V7Operation } from "./v7-translation";
import type { EditResultV1 } from "../contracts/generated/edit_result_v1";
import type { ProjectOpenResultV1 } from "../contracts/generated/project_open_result_v1";
import type { HistoryStateV1 } from "../contracts/generated/history_state_v1";
import type { AssistantApplyResultV1 } from "../contracts/generated/assistant_apply_result_v1";
import { templateExportArtifact } from "../contracts/template-export";
import archiveSchema from "../../../../contracts/json-schema/archive_manifest_v7.schema.json" with { type: "json" };

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

  /** Apply an assistant proposal with this page's token; an edit result becomes the shown state and undo history. */
  async applyProposal(proposalId: string, clientMutationId: string, allowEdits: boolean): Promise<AssistantApplyResultV1> {
    const result = await this.editing(token => v2Request<AssistantApplyResultV1>(
      this.path(`/assistant/proposals/${encodeURIComponent(proposalId)}/apply`), "POST",
      { editorToken: token, clientMutationId, allowEdits }, this.fetcher), true);
    if (result.edit) this.adopt(result.edit);
    return result;
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

  async rename(title: string): Promise<TemplateProjectResponseV1> {
    const response = await this.editing(token => v2Request<TemplateProjectResponseV1>(this.path("/rename"), "POST",
      { editorToken: token, baseRevision: this.response.workspace.projectRevision, title }, this.fetcher));
    this.response = response;
    return response;
  }

  async exportDocx(): Promise<{ blob: Blob; attemptId: string }> {
    const snapshot = this.response.snapshot;
    if (!snapshot) throw new ProjectApiFailure("INVALID_RESULT");
    const captured = structuredClone(snapshot);
    return this.editing(async token => {
      const response = await this.fetcher(this.path("/export"), { method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schemaVersion: 1, editorToken: token, snapshot: captured }) });
      if (!response.ok) throw await rejected(response);
      try {
        const artifact = await templateExportArtifact(response, captured);
        return { blob: artifact.blob, attemptId: artifact.attemptId };
      } catch (error) {
        throw new ProjectApiFailure(error instanceof Error && error.message === "ARTIFACT_BYTES_MISMATCH" ? error.message : "INVALID_RESULT", response.status);
      }
    });
  }

  saveFoldcv(): Promise<Blob> {
    const workspace = this.response.workspace;
    return this.editing(async token => fileBody(await this.fetcher(this.path("/archive"), {
      method: "POST", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ editorToken: token, projectRevision: workspace.projectRevision, documentRevision: workspace.documentRevision }),
    }), "application/vnd.foldcv.project+zip", archiveSchema["x-maxArchiveBytes"]));
  }
}

async function rejected(response: Response): Promise<ProjectApiFailure> {
  const text = await response.text();
  let value: unknown = null;
  try { value = text ? JSON.parse(text) : null; } catch { return new ProjectApiFailure("INVALID_RESULT", response.status); }
  const record = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
  const error = record["error"];
  const code = typeof error === "object" && error !== null && typeof Reflect.get(error, "code") === "string"
    ? String(Reflect.get(error, "code")) : "REQUEST_FAILED";
  return new ProjectApiFailure(code, response.status, record);
}

async function fileBody(response: Response, mime: string, maximum: number): Promise<Blob> {
  if (!response.ok) throw await rejected(response);
  const blob = await response.blob();
  if (!blob.size || blob.size > maximum || blob.type !== mime) throw new ProjectApiFailure("INVALID_RESULT", response.status);
  return blob;
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
