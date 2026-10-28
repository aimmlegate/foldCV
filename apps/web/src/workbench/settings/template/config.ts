import { isMap, isScalar, isSeq, parseDocument } from "yaml";
import { parseTemplateCatalog, type TemplateCatalog, type TemplateEntry } from "../../../projects/api";
import { ProjectApiFailure } from "../../../rich/v7-connection";

export type TemplateSummary = { id: string; name: string; revision: string; packageHash: string };
/** One template's YAML; `bundled` and `edited` as in its catalog entry. */
export type TemplateConfigState = { package: TemplateSummary; format: "yaml" | "json"; text: string; bundled: boolean; edited: boolean };
export type TemplateProblem = { path: string; message: string };
export type TemplateCheck = { valid: true; package: TemplateSummary } | { valid: false; error: TemplateProblem };
export type TemplateSave = { saved: true; state: TemplateConfigState } | { saved: false; error: TemplateProblem };

const path = "/v1/rich/template-config";
const one = (templateId: string) => `${path}/${encodeURIComponent(templateId)}`;

function field(value: unknown, key: string): unknown {
  return typeof value === "object" && value !== null ? Reflect.get(value, key) : undefined;
}
function text(value: unknown, key: string): string {
  const item = field(value, key);
  if (typeof item !== "string") throw new ProjectApiFailure("INVALID_RESULT");
  return item;
}
function summary(value: unknown): TemplateSummary {
  return { id: text(value, "id"), name: text(value, "name"), revision: text(value, "revision"), packageHash: text(value, "packageHash") };
}
export function parseConfigState(value: unknown): TemplateConfigState {
  const format = field(value, "format"), bundled = field(value, "bundled"), edited = field(value, "edited");
  if (field(value, "schemaVersion") !== 1 || (format !== "yaml" && format !== "json") || typeof bundled !== "boolean" || typeof edited !== "boolean")
    throw new ProjectApiFailure("INVALID_RESULT");
  return { package: summary(field(value, "package")), format, text: text(value, "text"), bundled, edited };
}
export function parseCheck(value: unknown): TemplateCheck {
  if (field(value, "schemaVersion") !== 1) throw new ProjectApiFailure("INVALID_RESULT");
  const valid = field(value, "valid");
  if (valid === true) return { valid: true, package: summary(field(value, "package")) };
  if (valid !== false) throw new ProjectApiFailure("INVALID_RESULT");
  const error = field(value, "error");
  return { valid: false, error: { path: text(error, "path"), message: text(error, "message") } };
}

/** The catalog after a save or reset of one template: its entry follows the new state, the others stay. */
export function withState(catalog: TemplateCatalog, state: TemplateConfigState): TemplateCatalog {
  const entry: TemplateEntry = { ...state.package, bundled: state.bundled, edited: state.edited };
  return { ...catalog, templates: catalog.templates.map(value => value.id === entry.id ? entry : value) };
}

/** A refused save answers 422 with the same body as a failed check; other failures carry an error code. */
async function call(url: string, method: string, body?: unknown): Promise<{ status: number; value: unknown }> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store" };
  if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const response = await fetch(url, init);
  let value: unknown = null;
  try { value = JSON.parse(await response.text()) as unknown; } catch { value = null; }
  if (response.ok || response.status === 422 && field(value, "valid") === false) return { status: response.status, value };
  const code = field(field(value, "error"), "code");
  throw new ProjectApiFailure(typeof code === "string" ? code : "REQUEST_FAILED", response.status);
}

export async function readTemplateCatalog(): Promise<TemplateCatalog> {
  return parseTemplateCatalog((await call(path, "GET")).value);
}
export async function readTemplateConfig(templateId: string): Promise<TemplateConfigState> {
  return parseConfigState((await call(one(templateId), "GET")).value);
}
export async function checkTemplateConfig(templateId: string, source: string): Promise<TemplateCheck> {
  return parseCheck((await call(`${one(templateId)}/check`, "POST", { text: source })).value);
}
export async function saveTemplateConfig(templateId: string, source: string): Promise<TemplateSave> {
  const { status, value } = await call(one(templateId), "PUT", { text: source });
  if (status === 422) {
    const check = parseCheck(value);
    if (check.valid) throw new ProjectApiFailure("INVALID_RESULT");
    return { saved: false, error: check.error };
  }
  return { saved: true, state: parseConfigState(value) };
}
export async function resetTemplateConfig(templateId: string): Promise<TemplateConfigState> {
  return parseConfigState((await call(`${one(templateId)}/reset`, "POST", {})).value);
}
/** Makes the template the default for new imports; its saved YAML stays as it is. */
export async function setDefaultTemplate(templateId: string): Promise<TemplateCatalog> {
  return parseTemplateCatalog((await call("/v1/rich/template-default", "PUT", { templateId })).value);
}

function tokens(pointer: string): string[] {
  return pointer.split("/").slice(1).filter(part => part !== "").map(part => part.replace(/~1/g, "/").replace(/~0/g, "~"));
}
function lineEnd(source: string, start: number): number {
  const end = source.indexOf("\n", start);
  return end < 0 ? source.length : end;
}

/** Text range for a server JSON pointer: the deepest key, item or value that exists, else the first line. */
export function pointerRange(source: string, pointer: string): { start: number; end: number } {
  const document = parseDocument(source);
  let node: unknown = document.contents, best: { start: number; end: number } | null = null;
  for (const token of tokens(pointer)) {
    if (isMap(node)) {
      const pair = node.items.find(item => isScalar(item.key) && String(item.key.value) === token);
      if (!pair || !isScalar(pair.key) || !pair.key.range) break;
      best = { start: pair.key.range[0], end: pair.key.range[1] };
      node = pair.value;
    } else if (isSeq(node)) {
      const item: unknown = /^\d+$/.test(token) ? node.items[Number(token)] : undefined;
      const range = isMap(item) || isSeq(item) || isScalar(item) ? item.range : undefined;
      if (!range) break;
      best = { start: range[0], end: Math.min(range[1], lineEnd(source, range[0])) };
      node = item;
    } else break;
  }
  if (isScalar(node) && node.range && best) best = { start: best.start, end: Math.max(best.end, node.range[1]) };
  if (best && best.end > best.start) return best;
  const first = source.search(/^[^#\s]/m);
  const start = first < 0 ? 0 : first;
  return { start, end: Math.max(start + 1, lineEnd(source, start)) };
}

// Top-level sections people rarely edit: fonts and files, fact storage, operations, provenance.
const TECHNICAL = new Set(["style", "layout", "source", "content_definitions", "fact_types", "operations", "assets", "provenance"]);

/** 0-based lines of the technical top-level keys, folded in the editor by default. */
export function technicalLines(source: string): number[] {
  return source.split("\n").flatMap((line, index) => {
    const key = /^([a-z_]+):/.exec(line)?.[1];
    return key !== undefined && TECHNICAL.has(key) ? [index] : [];
  });
}
