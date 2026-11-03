/** The title as a file name without its extension: no control or reserved characters, at most 60 characters. */
export function projectStem(title: string): string {
  const text = Array.from(title).map(char => (char.codePointAt(0) ?? 0) < 32 || char === "\u007f" ? " " : char).join("");
  const safe = text.replace(/[<>:"/\\|?*]/gu, " ").replace(/\s+/gu, " ").replace(/^[. ]+|[. ]+$/gu, "");
  return Array.from(safe).slice(0, 60).join("").replace(/[. ]+$/u, "") || "resume";
}

export function projectFilename(title: string, extension: "docx" | "foldcv"): string {
  return `${projectStem(title)}.${extension}`;
}
