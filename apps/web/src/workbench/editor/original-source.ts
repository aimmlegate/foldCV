export type OriginalKind = "pdf" | "docx" | "text" | "markdown" | "unsupported";

export function originalKind(name: string): OriginalKind {
  const extension = name.toLowerCase().split(".").at(-1);
  if (extension === "pdf" || extension === "docx") return extension;
  if (extension === "md" || extension === "markdown") return "markdown";
  return extension === "txt" ? "text" : "unsupported";
}

export function originalUrl(projectId: string, sourceId: string, version: "v1" | "v2" = "v1"): string {
  const root = version === "v2" ? "/v2/projects" : "/v1/rich/projects";
  return `${root}/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(sourceId)}/original`;
}

export async function loadOriginal(url: string, hash: string, signal: AbortSignal): Promise<Blob> {
  const response = await fetch(url, { credentials: "same-origin", cache: "no-store", signal });
  if (!response.ok) throw new Error("Не удалось загрузить оригинал. Попробуйте ещё раз.");
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actual = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  if (actual !== hash) throw new Error("Сохранённый оригинал повреждён.");
  signal.throwIfAborted();
  return new Blob([bytes], { type: response.headers.get("Content-Type") ?? "application/octet-stream" });
}
