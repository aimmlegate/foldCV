import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";

export function reviewId(response: RichProjectResponse | null): string | null {
  return response?.workspace.project && response.generation && ["completed", "failed"].includes(response.generation.status)
    ? `${response.workspace.projectId}:${response.generation.id}` : null;
}

export function importView(response: RichProjectResponse | null, reviewed: string | null, sourceOpen: boolean) {
  if (response?.generation && ["queued", "running"].includes(response.generation.status)) return "progress";
  if (sourceOpen || !response?.workspace.project) return "source";
  const id = reviewId(response);
  return id && id !== reviewed ? "assessment" : "editor";
}
