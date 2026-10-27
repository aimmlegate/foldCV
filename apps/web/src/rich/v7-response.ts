import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";

/** Read helpers over a verified V7 response parsed with JSON.parse: blocks, their text containers and inline leaves. */
type Json = Record<string, unknown>;
export type ResponseLeaf = { path: [number] | [number, number]; span: Json; owner: Json | null; start: number; end: number };
export type ResponseGroup = { kind: "content" | "caption" | "cell"; key: string; content: Json[]; cellRevision: number | null };
export type ResponseBlock = { block: Json; revision: number; groups: ResponseGroup[] };
export type InsertionTarget = { kind: "literal" } | { kind: "field"; bindingId: string } | { kind: "manual_scope"; fragmentId: string };

function invalid(): never { throw new Error("INVALID_RESULT"); }
function object(value: unknown): Json { return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Json : invalid(); }
function list(value: unknown): Json[] { return Array.isArray(value) ? value.map(object) : invalid(); }
function text(node: Json, key: string): string { const value = node[key]; return typeof value === "string" ? value : invalid(); }
function integer(node: Json, key: string): number {
  const value = node[key];
  return typeof value === "number" && Number.isSafeInteger(value) ? value : invalid();
}

function groups(block: Json): ResponseGroup[] {
  const type = text(block, "type");
  if (type === "table") return list(object(block["content"])["rows"]).flatMap(row => list(row["cells"]).map(cell => ({
    kind: "cell" as const, key: text(cell, "id"), content: list(cell["content"]), cellRevision: integer(cell, "revision") })));
  if (type === "image") return [{ kind: "caption", key: "caption", content: list(object(block["props"])["caption"]), cellRevision: null }];
  return Array.isArray(block["content"]) ? [{ kind: "content", key: "content", content: list(block["content"]), cellRevision: null }] : [];
}

/** Every block of the response by id, in document order, with its text containers. */
export function responseBlocks(response: TemplateProjectResponseV1): Map<string, ResponseBlock> {
  const result = new Map<string, ResponseBlock>();
  const visit = (block: Json): void => {
    const id = text(block, "id");
    if (result.has(id)) invalid();
    result.set(id, { block, revision: integer(block, "revision"), groups: groups(block) });
    list(block["children"]).forEach(visit);
  };
  const project = response.workspace.project ?? invalid();
  for (const region of project.document.regions) list(region.blocks).forEach(visit);
  return result;
}

/** Inline leaves with UTF-16 offsets; link children are leaves of their link. */
export function responseLeaves(content: readonly Json[]): ResponseLeaf[] {
  const result: ResponseLeaf[] = [];
  let cursor = 0;
  content.forEach((span, index) => {
    const type = text(span, "type");
    const children: { path: ResponseLeaf["path"]; node: Json; owner: Json | null }[] = type === "link" || type === "bound_link"
      ? list(span["content"]).map((child, childIndex) => ({ path: [index, childIndex], node: child, owner: span }))
      : [{ path: [index], node: span, owner: null }];
    for (const child of children) {
      const size = text(child.node, "text").length;
      result.push({ path: child.path, span: child.node, owner: child.owner, start: cursor, end: cursor + size });
      cursor += size;
    }
  });
  return result;
}

export function contentText(content: readonly Json[]): string { return responseLeaves(content).map(leaf => text(leaf.span, "text")).join(""); }

/** Where typing at a leaf goes: its complete field, its manual scope, or literal text; a bound link label has none. */
export function leafTarget(leaf: ResponseLeaf): InsertionTarget | null {
  const type = text(leaf.span, "type");
  if (type === "fact_field") return leaf.span["complete"] === true ? { kind: "field", bindingId: text(leaf.span, "bindingId") } : null;
  if (type === "manual_scope") return { kind: "manual_scope", fragmentId: text(leaf.span, "fragmentId") };
  return leaf.owner && text(leaf.owner, "type") === "bound_link" ? null : { kind: "literal" };
}

/** The ids of the last 200 applied client mutations, as the project file keeps them (plan 2.1). */
export function appliedMutations(response: TemplateProjectResponseV1): Set<string> {
  return new Set((response.workspace.mutationReplay ?? []).map(row => row.clientMutationId));
}
