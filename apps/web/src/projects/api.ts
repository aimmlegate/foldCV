import type { RegistryEntry } from "../contracts/generated/registry";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { TaskStatusV1 } from "../contracts/generated/task_status_v1";
import type { ReasoningEffort } from "../connection/reasoning";
import { ProjectApiFailure, v2Request, type Fetcher } from "../rich/v7-connection";

export type ProjectTask = TaskStatusV1;

/** One row of GET /v2/projects: the registry entry with catalog flags and the resume identity. */
export type ProjectListEntry = RegistryEntry & { lastOpenedAt?: string | null; archived?: boolean; subtitle?: string | null };
/** The server sends the entries newest added first; the sidebar keeps that order. */
export type ProjectList = { entries: ProjectListEntry[]; errors: { projectId: string; errorCode: string }[] };

export type ImportDiscoveries = {
  name: string; title: string; facts: number; jobs: { id: string; employer: string; role: string }[];
  jobCount: number; technologies: string[]; technologyCount: number;
};

/** `detail.progress` of a running import task (`projects/import_progress.py`): steps, model activity and the stall
 * check the service computed from the operation record. */
export type ImportPhase = "starting" | "queued" | "processing" | "publication";
export type ImportProgress = {
  phase: ImportPhase; done: number; total: number; current: string[]; events: { at: string; text: string }[];
  lastEventAt: string | null; lastModelAt: string | null; quietSeconds: number; quietLimitSeconds: number; stalled: boolean;
};
export type ImportOptions = { allowTextRewrite: boolean; effort: ReasoningEffort | null };
/** A template new resumes can use: `bundled` when the app ships its id, `edited` when its current version is not the
 * shipped one. */
export type TemplateEntry = { id: string; name: string; revision: string; packageHash: string; bundled: boolean; edited: boolean };
export type TemplateCatalog = { defaultId: string; templates: TemplateEntry[] };
export type TemplateImportStatus = TemplateCatalog & { available: boolean };

function projectPath(projectId: string, tail = ""): string {
  return `/v2/projects/${encodeURIComponent(projectId)}${tail}`;
}

const browserFetch: Fetcher = (input, init) => fetch(input, init);

export function listProjects(fetcher?: Fetcher): Promise<ProjectList> {
  return v2Request<ProjectList>("/v2/projects", "GET", undefined, fetcher);
}

async function upload(path: string, body: FormData, fetcher: Fetcher): Promise<TemplateProjectResponseV1> {
  const response = await fetcher(path, { method: "POST", body, credentials: "same-origin", cache: "no-store" });
  const text = await response.text();
  let value: unknown = null;
  try { value = text ? JSON.parse(text) : null; } catch { throw new ProjectApiFailure("INVALID_RESULT", response.status); }
  const record = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
  if (!response.ok) {
    const error = record["error"];
    const code = typeof error === "object" && error !== null && typeof Reflect.get(error, "code") === "string"
      ? String(Reflect.get(error, "code")) : "REQUEST_FAILED";
    throw new ProjectApiFailure(code, response.status, record);
  }
  // Only V7 projects open in this client; any other reply is not a project it can show.
  const workspace = record["workspace"];
  if (typeof workspace !== "object" || workspace === null || Reflect.get(workspace, "schemaVersion") !== 7)
    throw new ProjectApiFailure("INVALID_RESULT", response.status);
  return value as TemplateProjectResponseV1;
}

/** A pasted text or file becomes a V7 project with the chosen template (null: the default one), ready for import. */
export function createProject(body: FormData, templateId: string | null, fetcher: Fetcher = browserFetch): Promise<TemplateProjectResponseV1> {
  const path = "/v1/rich/projects/template-input";
  return upload(templateId === null ? path : `${path}/${encodeURIComponent(templateId)}`, body, fetcher);
}

/** Opens a .foldcv as a new V7 project. */
export function openFoldcv(file: File, fetcher: Fetcher = browserFetch): Promise<TemplateProjectResponseV1> {
  const body = new FormData();
  body.append("file", file);
  return upload("/v2/projects/archive", body, fetcher);
}

/** A null effort keeps the import model's catalog default; the service checks a chosen one against the catalog. */
export function startImport(projectId: string, body: { clientRequestId: string } & ImportOptions, fetcher?: Fetcher): Promise<ProjectTask> {
  const { effort, ...rest } = body;
  return v2Request<ProjectTask>(projectPath(projectId, "/import"), "POST", { kind: "start", ...rest, ...(effort ? { effort } : {}) }, fetcher);
}

export function resumeImport(projectId: string, operationId: string, fetcher?: Fetcher): Promise<ProjectTask> {
  return v2Request<ProjectTask>(projectPath(projectId, "/import"), "POST",
    { kind: "resume", operationId, clientRequestId: `resume-${operationId}` }, fetcher);
}

export function cancelImport(projectId: string, taskId: string, fetcher?: Fetcher): Promise<ProjectTask> {
  return v2Request<ProjectTask>(projectPath(projectId, "/import"), "POST", { kind: "cancel", taskId }, fetcher);
}

export async function projectTasks(projectId: string, fetcher?: Fetcher): Promise<ProjectTask[]> {
  const value = await v2Request<{ tasks: ProjectTask[] }>(projectPath(projectId, "/tasks"), "GET", undefined, fetcher);
  return value.tasks;
}

/** The newest import operation of a pre-draft, read without an editor token; null before the first start. */
export async function lastImportOperation(projectId: string, fetcher?: Fetcher): Promise<string | null> {
  const value = await v2Request<TemplateProjectResponseV1>(projectPath(projectId), "GET", undefined, fetcher);
  const owner = value.workspace.project ?? value.workspace.preDraft;
  return owner?.templateOperations?.at(-1)?.id ?? null;
}

function invalid(): never {
  throw new ProjectApiFailure("INVALID_RESULT");
}
function templateEntry(value: unknown): TemplateEntry {
  if (typeof value !== "object" || value === null) invalid();
  const { id, name, revision, packageHash, bundled, edited } = value as Record<string, unknown>;
  if (typeof id !== "string" || typeof name !== "string" || typeof revision !== "string" || typeof packageHash !== "string"
    || typeof bundled !== "boolean" || typeof edited !== "boolean") invalid();
  return { id, name, revision, packageHash, bundled, edited };
}
/** The templates and the default one, from the import status or the Settings list. */
export function parseTemplateCatalog(value: unknown): TemplateCatalog {
  const record = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
  const { schemaVersion, defaultId, templates } = record;
  if (schemaVersion !== 1 || typeof defaultId !== "string" || !Array.isArray(templates)) invalid();
  const entries = templates.map(templateEntry);
  if (!entries.some(entry => entry.id === defaultId)) invalid();
  return { defaultId, templates: entries };
}

/** The template the import form shows after it reads the list: the user's own pick while it still exists, else the
 * default one. */
export function shownTemplate(catalog: TemplateCatalog, current: string | null, picked: boolean): string {
  const kept = picked ? catalog.templates.find(entry => entry.id === current) : undefined;
  return kept?.id ?? catalog.defaultId;
}

/** Whether imports run, and the templates a new resume can use. */
export async function templateImportStatus(fetcher?: Fetcher): Promise<TemplateImportStatus> {
  const value = await v2Request<unknown>("/v1/rich/template-import", "GET", undefined, fetcher);
  const available: unknown = typeof value === "object" && value !== null ? Reflect.get(value, "available") : undefined;
  if (typeof available !== "boolean") invalid();
  return { available, ...parseTemplateCatalog(value) };
}

export function catalogFlag(projectId: string, archived: boolean, fetcher?: Fetcher): Promise<unknown> {
  return v2Request(projectPath(projectId, `/catalog/${archived ? "archive" : "restore"}`), "POST", {}, fetcher);
}

export function deleteProject(projectId: string, fetcher?: Fetcher): Promise<{ cleanupStatus: RegistryEntry["cleanupStatus"] }> {
  return v2Request(projectPath(projectId), "DELETE", { confirmed: true }, fetcher);
}
