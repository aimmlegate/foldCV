import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { TaskStatusV1 } from "../contracts/generated/task_status_v1";
import { ProjectApiFailure, v2Request, type Fetcher } from "../rich/v7-connection";

export type ProjectTask = TaskStatusV1;

export type ImportDiscoveries = {
  name: string; title: string; facts: number; jobs: { id: string; employer: string; role: string }[];
  jobCount: number; technologies: string[]; technologyCount: number;
};

function projectPath(projectId: string, tail = ""): string {
  return `/v2/projects/${encodeURIComponent(projectId)}${tail}`;
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

export function deleteTemplateProject(projectId: string, fetcher?: Fetcher): Promise<{ cleanupStatus: string }> {
  return v2Request(projectPath(projectId), "DELETE", { confirmed: true }, fetcher);
}

/** A V7 .foldcv. Anything the server does not accept as a V7 archive is left for the V6 route. */
export async function openFoldcv(file: File, fetcher: Fetcher = (input, init) => fetch(input, init)): Promise<TemplateProjectResponseV1> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetcher("/v2/projects/archive", { method: "POST", body, credentials: "same-origin", cache: "no-store" });
  const text = await response.text();
  let value: unknown = null;
  try { value = text ? JSON.parse(text) : null; } catch { throw new ProjectApiFailure("INVALID_RESULT", response.status); }
  if (!response.ok) {
    const record = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
    const error = record["error"];
    const code = typeof error === "object" && error !== null && typeof Reflect.get(error, "code") === "string"
      ? String(Reflect.get(error, "code")) : "REQUEST_FAILED";
    throw new ProjectApiFailure(code, response.status, record);
  }
  return value as TemplateProjectResponseV1;
}
