export function projectFilename(title: string, extension: "docx" | "foldcv"): string {
  const text = Array.from(title).map(char => (char.codePointAt(0) ?? 0) < 32 || char === "\u007f" ? " " : char).join("");
  const safe = text.replace(/[<>:"/\\|?*]/gu, " ").replace(/\s+/gu, " ").replace(/^[. ]+|[. ]+$/gu, "");
  const name = Array.from(safe).slice(0, 60).join("").replace(/[. ]+$/u, "");
  return `${name || "resume"}.${extension}`;
}
