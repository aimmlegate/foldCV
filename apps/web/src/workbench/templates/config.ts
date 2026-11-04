import { isMap, isScalar, isSeq, parseDocument } from "yaml";
import { field, optionalText, text } from "../../api/fields";
import { parseTemplateCatalog, type TemplateCatalog, type TemplateEntry } from "../../projects/api";
import { ProjectApiFailure } from "../../rich/v7-connection";

export type TemplateSummary = { id: string; name: string; revision: string; packageHash: string };
/** One template's YAML; `bundled` and `edited` as in its catalog entry. */
export type TemplateConfigState = { package: TemplateSummary; format: "yaml" | "json"; text: string; bundled: boolean; edited: boolean };
/** `nextRevision`: the free revision the server offers when the text's revision is saved already with other bytes. */
export type TemplateProblem = { path: string; message: string; nextRevision?: string };
export type TemplateCheck = { valid: true; package: TemplateSummary } | { valid: false; error: TemplateProblem };
export type TemplateSave = { saved: true; state: TemplateConfigState } | { saved: false; error: TemplateProblem };

const path = "/v1/rich/template-config";
const one = (templateId: string) => `${path}/${encodeURIComponent(templateId)}`;

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
  const error = field(value, "error"), next = field(error, "nextRevision");
  const problem: TemplateProblem = { path: text(error, "path"), message: text(error, "message") };
  return { valid: false, error: typeof next === "string" && next ? { ...problem, nextRevision: next } : problem };
}

/** The catalog after a save, reset or create of one template: its entry follows the new state, the others stay. A
 * new id joins the list where the server lists it: after the shipped templates, own ones by id. */
export function withState(catalog: TemplateCatalog, state: TemplateConfigState): TemplateCatalog {
  const entry: TemplateEntry = { ...state.package, bundled: state.bundled, edited: state.edited };
  if (catalog.templates.some(value => value.id === entry.id)) return { ...catalog, templates: catalog.templates.map(value => value.id === entry.id ? entry : value) };
  const shipped = catalog.templates.filter(value => value.bundled), own = [...catalog.templates.filter(value => !value.bundled), entry];
  return { ...catalog, templates: [...shipped, ...own.sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0)] };
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
/** A save or create reply: the new state, or on 422 the compile error in the check shape. */
export function parseSave(status: number, value: unknown): TemplateSave {
  if (status === 422) {
    const check = parseCheck(value);
    if (check.valid) throw new ProjectApiFailure("INVALID_RESULT");
    return { saved: false, error: check.error };
  }
  return { saved: true, state: parseConfigState(value) };
}
/** `revision`: the offered free revision; the server writes it into the text's revision line before it saves. */
export async function saveTemplateConfig(templateId: string, source: string, revision?: string): Promise<TemplateSave> {
  const { status, value } = await call(one(templateId), "PUT", revision ? { text: source, revision } : { text: source });
  return parseSave(status, value);
}
/** A copy of a saved template under a new name, or a new template from unsaved text; the server picks the id. */
export type TemplateCreate = { copyOf: string; name: string } | { text: string; assetsFrom: string | null };
export async function createTemplate(body: TemplateCreate): Promise<TemplateSave> {
  const { status, value } = await call(path, "POST", body);
  return parseSave(status, value);
}
/** Removes an own template from the catalog; resumes made with it keep their captured copy. */
export async function deleteTemplate(templateId: string): Promise<TemplateCatalog> {
  return parseTemplateCatalog((await call(one(templateId), "DELETE")).value);
}
export async function resetTemplateConfig(templateId: string): Promise<TemplateConfigState> {
  return parseConfigState((await call(`${one(templateId)}/reset`, "POST", {})).value);
}
/** Makes the template the default for new imports; its saved YAML stays as it is. */
export async function setDefaultTemplate(templateId: string): Promise<TemplateCatalog> {
  return parseTemplateCatalog((await call("/v1/rich/template-default", "PUT", { templateId })).value);
}

/** D145: whether the template has a logo place, its own logo as a PNG data URL, and the footer email. */
export type TemplateBranding = { logoPlace: boolean; logo: string | null; footer: string };
export type BrandingChange = { logo?: string; removeLogo?: boolean; footer: string };
export type BrandingSave = { saved: true; state: TemplateConfigState; branding: TemplateBranding } | { saved: false; error: TemplateProblem };
export function parseBranding(value: unknown): TemplateBranding {
  const place = field(value, "logoPlace"), logo = optionalText(value, "logo");
  if (typeof place !== "boolean") throw new ProjectApiFailure("INVALID_RESULT");
  return { logoPlace: place, logo: logo?.startsWith("data:image/png;base64,") ? logo : null, footer: text(value, "footer") };
}
export async function readTemplateBranding(templateId: string): Promise<TemplateBranding> {
  const { value } = await call(`${one(templateId)}/branding`, "GET");
  if (field(value, "schemaVersion") !== 1) throw new ProjectApiFailure("INVALID_RESULT");
  return parseBranding(value);
}
/** Saves the logo and email as the template's next version; `logo` is the picture's base64, without a data URL prefix. */
export async function saveTemplateBranding(templateId: string, change: BrandingChange): Promise<BrandingSave> {
  const { status, value } = await call(`${one(templateId)}/branding`, "PUT", change);
  const result = parseSave(status, value);
  return result.saved ? { ...result, branding: parseBranding(field(value, "branding")) } : result;
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

/** The 1-based editor line where `pointerRange` places a server problem. */
export function problemLine(source: string, pointer: string): number {
  const { start } = pointerRange(source, pointer);
  let line = 1;
  for (let index = source.indexOf("\n"); index >= 0 && index < start; index = source.indexOf("\n", index + 1)) line += 1;
  return line;
}

/** The editor's tabs (D147): each shows its top-level YAML keys and folds the others. «Шаблон» also holds the leading
 * comments; keys the list does not name are service ones. */
export type SectionTab = "template" | "model" | "blocks" | "style" | "service";
export const sectionTabs: readonly { id: SectionTab; label: string }[] = [{ id: "template", label: "Шаблон" }, { id: "model", label: "Правила" },
  { id: "blocks", label: "Блоки" }, { id: "style", label: "Стили" }, { id: "service", label: "Служебные" }];
const keyTabs: Readonly<Record<string, SectionTab>> = { schema_version: "template", template: "template", model: "model", blocks: "blocks", style: "style" };
export function sectionTab(key: string): SectionTab { return Object.hasOwn(keyTabs, key) ? keyTabs[key] as SectionTab : "service"; }

/** The top-level keys of a YAML text with their 0-based lines. A JSON text has none, so it shows without tabs. */
export function topLevelSections(source: string): { key: string; line: number }[] {
  return source.split("\n").flatMap((line, index) => {
    const key = /^([A-Za-z_][\w-]*)\s*:/.exec(line)?.[1];
    return key === undefined ? [] : [{ key, line: index }];
  });
}
/** The tab of a server problem: its pointer's first key; a problem of the whole text opens «Шаблон». */
export function problemTab(pointer: string): SectionTab {
  const key = tokens(pointer)[0];
  return key === undefined ? "template" : sectionTab(key);
}
