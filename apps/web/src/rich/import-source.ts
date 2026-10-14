export type ResumeInput = { kind: "text"; text: string } | { kind: "file"; file: File };

export function hasInput(input: ResumeInput): boolean {
  return input.kind === "file" || input.text.trim().length > 0;
}

export function importBody(input: ResumeInput): FormData {
  const body = new FormData();
  if (input.kind === "file") body.append("file", input.file);
  else body.append("paste", new Blob([input.text], { type: "text/plain" }), "pasted.txt");
  return body;
}
