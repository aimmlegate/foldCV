import type { RegistryEntry } from "../contracts/generated/registry";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { TaskStatusV1 } from "../contracts/generated/task_status_v1";
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

/** A pasted text or file becomes a V7 project with the store's active template, ready for import. */
export function createProject(body: FormData, fetcher: Fetcher = browserFetch): Promise<TemplateProjectResponseV1> {
  return upload("/v1/rich/projects/template-input", body, fetcher);
}

/** Opens a .foldcv as a new V7 project. */
export function openFoldcv(file: File, fetcher: Fetcher = browserFetch): Promise<TemplateProjectResponseV1> {
  const body = new FormData();
  body.append("file", file);
  return upload("/v2/projects/archive", body, fetcher);
}

export function startImport(projectId: string, body: { clientRequestId: string; allowTextRewrite: boolean }, fetcher?: Fetcher): Promise<ProjectTask> {
  return v2Request<ProjectTask>(projectPath(projectId, "/import"), "POST", { kind: "start", ...body }, fetcher);
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

export function catalogFlag(projectId: string, archived: boolean, fetcher?: Fetcher): Promise<unknown> {
  return v2Request(projectPath(projectId, `/catalog/${archived ? "archive" : "restore"}`), "POST", {}, fetcher);
}

export function deleteProject(projectId: string, fetcher?: Fetcher): Promise<{ cleanupStatus: string }> {
  return v2Request(projectPath(projectId), "DELETE", { confirmed: true }, fetcher);
}
