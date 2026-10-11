import type { Project } from "../contracts/generated/project";
import type { Presentation } from "../contracts/generated/prepare_request";
import type { ExtractResult } from "../contracts/generated/extract_result";
import type { FactSheet, TextFact } from "../contracts/generated/fact_sheet";
import type { EditorState } from "../editor/state";
import { initialEditorState } from "../editor/state";
import type { ImportedSource, ImportState } from "../import/workflow";
import type { FactView } from "../facts/workflow";
import type { ManualInput, WorkingDraft } from "../facts/working";
import { emptyManualInput } from "../facts/working";
import type { Rendered } from "../preview/render";
import { syntheticSourceBytes } from "../editor/example";
import { validateContract, validateDraftResult, validateExtractResult, validateFactSheet,
  validateRenderRequest, validateRewriteResult } from "../contracts/validate";
import { readZip, safeArchivePath, writeZip } from "./zip";
import { migrateSelectedView } from "./legacy";
import pinnedTemplate from "../../../../templates/generic/manifest.json" with { type: "json" };

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });
const maxJson = 16 * 1024 * 1024;
const trustedTemplate = "d081df948bfd55d107c38d40387a9758f563f9c14a9cffc4a847f44cb687b8b9";
const hashPattern = /^[a-f0-9]{64}$/;

type Role = "project" | "workspace" | "source_original" | "template_asset" | "render";
type ManifestEntry = { path: string; role: Role; sha256: string; uncompressedSize: number };
type Manifest = { schemaVersion: 4; appVersion: string; rendererVersion: string | null;
  templatePackageSha256: string | null; templateAssetsIncluded: boolean;
  projectId: string | null; entries: ManifestEntry[] };
type FactSnapshot = { view: FactView; assertions: TextFact[]; corrections: Record<string, string> };
type ImportSnapshot = { state: ImportState; originals: Record<string, Uint8Array> };
type WorkingSourceRecord = { entry: ImportedSource; originalRef: string };
type WorkingRecord = Omit<WorkingDraft, "sources"> & { sources: WorkingSourceRecord[] };
type EditorRecord = Omit<EditorState, "project" | "loadId" | "sourceIntegrity" | "working"> & { working: WorkingRecord | null };
type LegacyRecord = { format: "v2"; archive: Record<string, unknown>; originalRef: string;
  originalName: string; originalSha256: string; view: Record<string, unknown> | null };
export type LegacyV2 = { archive: Record<string, unknown>; originalName: string; originalBytes: Uint8Array;
  view: Record<string, unknown> | null };
type Workspace = { schemaVersion: 4; editor: EditorRecord | null; importState: ImportState;
  importOriginals: Record<string, string>; facts: FactSnapshot; manualForm: ManualInput;
  assertionDraft: string; factEdits: Record<string, string>; rewriteInstruction: string;
  preEditorSourceText: string; renderBinding: string | null; legacy: LegacyRecord | null };
export type ArchiveInput = { editor: EditorState; imports: ImportSnapshot; facts: FactSnapshot;
  projectOriginals: Record<string, Uint8Array>;
  legacy: LegacyV2 | null;
  trustedAssets: Map<string, Uint8Array> | null;
  manualForm: ManualInput; assertionDraft: string; factEdits: Record<string, string>;
  rewriteInstruction: string; render: Rendered | null };
export type OpenedArchive = { editor: EditorState; imports: ImportSnapshot; facts: FactSnapshot;
  projectOriginals: Record<string, Uint8Array>;
  legacy: LegacyV2 | null;
  trustedAssets: Map<string, Uint8Array> | null;
  manualForm: ManualInput; assertionDraft: string; factEdits: Record<string, string>;
  rewriteInstruction: string; render: null; migration: string | null };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function strings(value: unknown): value is Record<string, string> {
  return object(value) && Object.values(value).every((item) => typeof item === "string");
}
function exact(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).every((key) => keys.includes(key)) && keys.every((key) => Object.hasOwn(value, key));
}
function optional(value: Record<string, unknown>, required: readonly string[], allowed: readonly string[]): boolean {
  return required.every((key) => Object.hasOwn(value, key)) && Object.keys(value).every((key) => allowed.includes(key));
}
function finite(value: unknown, seen = new Set<object>()): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || value === null) return value === null || typeof value === "string" || typeof value === "boolean";
  if (seen.has(value)) return false;
  seen.add(value);
  return Object.values(value).every((item) => finite(item, seen));
}
function noCredentialKeys(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(noCredentialKeys);
  if (!object(value)) return true;
  return Object.entries(value).every(([key, part]) =>
    !/^(?:secret|password|token|api[_-]?key|authorization|cookie|credential|session|home|cwd|workspace|config[_-]?path)$/i.test(key) &&
    noCredentialKeys(part));
}
function validLegacyArchive(value: unknown): value is Record<string, unknown> {
  if (!object(value) || !exact(value, ["schema_version", "as_of", "source_snapshot", "source", "units",
      "classifications", "jobs", "global_technologies"]) || value.schema_version !== 2 ||
      typeof value.as_of !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value.as_of) ||
      typeof value.source_snapshot !== "string" || !safeArchivePath(value.source_snapshot) ||
      value.source_snapshot.includes("/") || !object(value.source) ||
      !exact(value.source, ["file", "sha256", "pages", "warnings"]) ||
      typeof value.source.file !== "string" || typeof value.source.sha256 !== "string" ||
      !hashPattern.test(value.source.sha256) || !Array.isArray(value.source.pages) ||
      !value.source.pages.every((page: unknown) => object(page) && exact(page, ["page", "text"]) &&
        Number.isInteger(page.page) && Number(page.page) >= 1 && typeof page.text === "string") ||
      !stringArray(value.source.warnings) || !Array.isArray(value.units) ||
      !value.units.every((unit: unknown) => object(unit) && exact(unit, ["id", "page", "text"]) &&
        typeof unit.id === "string" && Number.isInteger(unit.page) && Number(unit.page) >= 1 &&
        typeof unit.text === "string") || !object(value.classifications) ||
      !Array.isArray(value.jobs) || !Array.isArray(value.global_technologies) ||
      !finite(value) || !noCredentialKeys(value)) return false;
  const units = value.units as { id: string; page: number; text: string }[];
  const ids = new Set(units.map((unit) => unit.id));
  const jobs = value.jobs as unknown[];
  const jobIds = new Set(jobs.filter(object).map((job) => job.id));
  const cited = (item: unknown): boolean => object(item) && exact(item, ["text", "sources"]) &&
    typeof item.text === "string" && stringArray(item.sources) && item.sources.every((id) => ids.has(id));
  const tech = (item: unknown): boolean => object(item) &&
    optional(item, ["name", "sources"], ["name", "sources", "start", "end", "duration_eligible"]) &&
    typeof item.name === "string" && stringArray(item.sources) && item.sources.every((id) => ids.has(id)) &&
    (item.start === undefined || typeof item.start === "string") &&
    (item.end === undefined || item.end === null || typeof item.end === "string") &&
    (item.duration_eligible === undefined || typeof item.duration_eligible === "boolean");
  return ids.size === units.length &&
    Object.entries(value.classifications).every(([id, item]) => ids.has(id) && object(item) &&
      exact(item, ["category", "importance", "job_id"]) &&
      ["identity", "profile", "job_header", "period", "role", "task", "result", "stack", "education",
        "course", "language", "location", "preferences", "contacts", "personal", "meta"].includes(String(item.category)) &&
      ["essential", "supporting", "administrative"].includes(String(item.importance)) &&
      (item.job_id === null || jobIds.has(item.job_id))) &&
    jobIds.size === jobs.length && jobs.every((job) => object(job) &&
      optional(job, ["id", "company", "period", "role", "start", "end", "technologies"],
        ["id", "company", "period", "role", "start", "end", "technologies", "observed_at", "observed_sources"]) &&
      typeof job.id === "string" && cited(job.company) && cited(job.period) && cited(job.role) &&
      typeof job.start === "string" && (job.end === null || typeof job.end === "string") &&
      (job.observed_at === undefined || job.observed_at === null || typeof job.observed_at === "string") &&
      (job.observed_sources === undefined || stringArray(job.observed_sources) &&
        job.observed_sources.every((id) => ids.has(id))) &&
      Array.isArray(job.technologies) && job.technologies.every(tech)) &&
    value.global_technologies.every(tech);
}
function validLegacyRecord(value: unknown): value is LegacyRecord {
  return object(value) && exact(value, ["format", "archive", "originalRef", "originalName", "originalSha256", "view"]) &&
    value.format === "v2" && validLegacyArchive(value.archive) &&
    typeof value.originalRef === "string" && safeArchivePath(value.originalRef) &&
    typeof value.originalName === "string" && value.originalName === value.archive.source_snapshot &&
    typeof value.originalSha256 === "string" && hashPattern.test(value.originalSha256) &&
    object(value.archive.source) && value.originalSha256 === value.archive.source.sha256 &&
    (value.view === null || object(value.view) && finite(value.view) && noCredentialKeys(value.view));
}
function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
function importedEntry(value: unknown): value is ImportedSource {
  if (!object(value) || !exact(value, ["result", "overlays"]) || !validateExtractResult(value.result) ||
      !strings(value.overlays)) return false;
  const result = value.result;
  let total = 0;
  return Object.entries(value.overlays).every(([key, text]) => {
    const length = encoder.encode(text).length;
    total += length;
    return length <= 64 * 1024 && total <= 1024 * 1024 &&
      (key.startsWith("unit:") ? result.units.some((unit) => key === `unit:${unit.id}`) :
        /^gap:(0|[1-9]\d*)$/.test(key) && Number(key.slice(4)) < result.gaps.length);
  });
}
function issues(value: unknown): boolean {
  return Array.isArray(value) && value.every((item: unknown) => object(item) &&
    exact(item, ["blockId", "code", "factId", "message"]) &&
    typeof item.blockId === "string" && typeof item.factId === "string" && typeof item.message === "string" &&
    ["MISSING_REQUIRED", "QUALIFIER_LOSS", "ATTRIBUTION_LOSS", "SOURCE_REVIEW"].includes(String(item.code)));
}
function blockState(value: unknown): boolean {
  return object(value) && exact(value, ["text", "origin", "locked", "factIds", "factRevisions"]) &&
    typeof value.text === "string" && ["source", "generated", "manual"].includes(String(value.origin)) &&
    typeof value.locked === "boolean" && stringArray(value.factIds) && object(value.factRevisions) &&
    Object.values(value.factRevisions).every((revision) => Number.isInteger(revision) && Number(revision) >= 1);
}
function review(value: unknown): boolean {
  return object(value) && exact(value, ["decisions", "acknowledgments"]) &&
    Array.isArray(value.decisions) && Array.isArray(value.acknowledgments) &&
    value.decisions.every((item: unknown) => object(item) &&
      exact(item, ["targetKind", "targetId", "disposition", "reason", "targetRevision"]) &&
      ["source_unit", "fact", "block"].includes(String(item.targetKind)) && typeof item.targetId === "string" &&
      ["shown", "condensed", "archived", "duplicate", "unresolved", "excluded"].includes(String(item.disposition)) &&
      (item.reason === null || typeof item.reason === "string") && Number.isInteger(item.targetRevision)) &&
    value.acknowledgments.every((item: unknown) => object(item) &&
      exact(item, ["issueId", "targetKind", "targetId", "targetRevision"]) && typeof item.issueId === "string" &&
      ["fact", "block"].includes(String(item.targetKind)) && typeof item.targetId === "string" &&
      Number.isInteger(item.targetRevision));
}
function coverage(value: unknown): boolean {
  return object(value) && exact(value, ["decisions", "acknowledgments"]) &&
    Array.isArray(value.decisions) && Array.isArray(value.acknowledgments) &&
    value.decisions.every((item: unknown) => object(item) &&
      exact(item, ["targetKind", "targetId", "disposition", "reason", "dependency"]) &&
      ["unit", "fact", "job"].includes(String(item.targetKind)) && typeof item.targetId === "string" &&
      ["shown", "condensed", "archived", "duplicate", "unresolved", "excluded"].includes(String(item.disposition)) &&
      (item.reason === null || typeof item.reason === "string") && typeof item.dependency === "string") &&
    value.acknowledgments.every((item: unknown) => object(item) && exact(item, ["issueId", "dependency"]) &&
      typeof item.issueId === "string" && typeof item.dependency === "string");
}
function checkpoints(value: unknown): boolean {
  return object(value) && Object.values(value).every((item) => object(item) &&
    exact(item, ["state", "revision", "visible", "status", "dependencyHash", "review", "issues",
      "issueDetails", "coverage", "manualEducation"]) && blockState(item.state) &&
    Number.isInteger(item.revision) && Number(item.revision) >= 1 && typeof item.visible === "boolean" &&
    ["empty", "running", "proposed", "ready", "stale", "error"].includes(String(item.status)) &&
    typeof item.dependencyHash === "string" && hashPattern.test(item.dependencyHash) && review(item.review) &&
    stringArray(item.issues) && issues(item.issueDetails) && (item.coverage === null || coverage(item.coverage)) &&
    (item.manualEducation === null || typeof item.manualEducation === "string"));
}
function json(value: unknown): Uint8Array {
  const bytes = encoder.encode(JSON.stringify(value));
  if (bytes.length > maxJson) throw new Error("Project metadata is too large.");
  return bytes;
}
function parse(bytes: Uint8Array | undefined): unknown {
  if (!bytes || bytes.length > maxJson) throw new Error("Missing or oversized project metadata.");
  try { return JSON.parse(decoder.decode(bytes)) as unknown; }
  catch { throw new Error("Invalid project metadata."); }
}
async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes));
  return Array.from(new Uint8Array(digest), (part) => part.toString(16).padStart(2, "0")).join("");
}
function trusted(project: Project): boolean {
  return project.template === null || project.template.id === "generic" && project.template.version === "1.0.0" &&
    project.template.packageSha256 === trustedTemplate && project.template.assets.every((asset) =>
      pinnedTemplate.assets[asset.path as keyof typeof pinnedTemplate.assets] === asset.sha256);
}

function verifiedTemplateAssets(files: Map<string, Uint8Array>): Promise<boolean> {
  return (async () => {
    const manifest = files.get("template/manifest.json");
    if (!manifest || await sha256(manifest) !== trustedTemplate) return false;
    const paths = Object.keys(pinnedTemplate.assets).map((path) => `template/${path}`);
    if (files.size !== paths.length + 1 || paths.some((path) => !files.has(path))) return false;
    for (const [path, expected] of Object.entries(pinnedTemplate.assets)) {
      const bytes = files.get(`template/${path}`);
      if (!bytes || await sha256(bytes) !== expected) return false;
    }
    return true;
  })();
}

export async function fetchTrustedTemplateAssets(): Promise<Map<string, Uint8Array> | null> {
  try {
    const response = await fetch("/v1/template-package", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok || response.headers.get("content-type")?.split(";")[0] !== "application/zip" ||
        Number(response.headers.get("content-length")) > 2 * 1024 * 1024) return null;
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length > 2 * 1024 * 1024) return null;
    const files = readZip(bytes);
    return await verifiedTemplateAssets(files) ? files : null;
  } catch { return null; }
}
function sanitizedProject(project: Project): Project {
  const copy = structuredClone(project);
  copy.operations = copy.operations.map((operation) => ["queued", "running"].includes(operation.status) ?
    { ...operation, status: "interrupted" } : operation);
  if (!validateContract("project", copy) || !trusted(copy)) throw new Error("Project contains invalid or untrusted data.");
  return copy;
}
function recordEditor(state: EditorState, project: Project): EditorRecord {
  const working = state.working;
  return { working: working ? { transportVersion: 1,
    sources: working.sources.map(({ entry }) => ({ entry: structuredClone(entry),
      originalRef: project.sources.find((source) => source.id === entry.result.sourceId)?.byteRef ??
        `sources/${entry.result.byteSha256}/original` })),
    sheet: structuredClone(working.sheet), priorSheet: structuredClone(working.priorSheet),
    sourceReviewStale: working.sourceReviewStale, manual: structuredClone(working.manual),
    draft: structuredClone(working.draft),
    ...(working.structuredCorrections === undefined ? {} : { structuredCorrections: { ...working.structuredCorrections } }),
    ...(working.coverage === undefined ? {} : { coverage: structuredClone(working.coverage) }) } : null,
  presentation: structuredClone(state.presentation), presentationDrafts: { ...state.presentationDrafts },
  presentationUndo: structuredClone(state.presentationUndo), stage: state.stage, panel: state.panel,
  selectedId: state.selectedId, drafts: { ...state.drafts }, factDrafts: { ...state.factDrafts },
  structuredDrafts: { ...state.structuredDrafts }, errors: { ...state.errors }, undo: structuredClone(state.undo),
  rewriteProposal: structuredClone(state.rewriteProposal), rewriteIssues: structuredClone(state.rewriteIssues),
  rewriteIssueDetails: structuredClone(state.rewriteIssueDetails), workingIssues: [...state.workingIssues],
  sourceText: state.sourceText, dirty: state.dirty };
}
function originalMap(input: ArchiveInput): Map<string, Uint8Array> {
  const result = new Map<string, Uint8Array>(Object.entries(input.projectOriginals).map(([id, bytes]) =>
    [id, Uint8Array.from(bytes)]));
  for (const [id, bytes] of Object.entries(input.imports.originals)) result.set(id, Uint8Array.from(bytes));
  for (const source of input.editor.working?.sources ?? []) result.set(source.entry.result.sourceId, Uint8Array.from(source.originalBytes));
  if (input.editor.project?.projectId === "project_synthetic") {
    for (const source of input.editor.project.sources) result.set(source.id, Uint8Array.from(syntheticSourceBytes));
  }
  return result;
}
function validatePresentation(value: unknown, project: Project): value is Presentation {
  if (!object(value) || !optional(value, ["name", "title", "sourceLanguage", "jobProseBlocks"],
      ["name", "title", "sourceLanguage", "jobProseBlocks", "languages"]) ||
      typeof value.name !== "string" || typeof value.title !== "string" ||
      !["ru", "en", "mixed"].includes(String(value.sourceLanguage)) || !strings(value.jobProseBlocks) ||
      !(value.languages === undefined || stringArray(value.languages))) return false;
  const jobs = project.employment.map((job) => job.id);
  const bindings = value.jobProseBlocks;
  return Object.keys(bindings).length === jobs.length && jobs.every((id) => Object.hasOwn(bindings, id)) &&
    new Set(Object.values(bindings)).size === jobs.length && Object.values(bindings).every((id) =>
      project.views.some((block) => block.id === id && block.kind === "job_prose"));
}
function validImportState(value: unknown): value is ImportState {
  if (!object(value) || !exact(value, ["entries", "selectedId", "pending", "error"]) ||
      !Array.isArray(value.entries) || value.entries.length > 10 ||
      value.pending !== false || value.error !== null ||
      !(value.selectedId === null || typeof value.selectedId === "string")) return false;
  return value.entries.every(importedEntry) &&
    new Set(value.entries.map((item: ImportedSource) => item.result.sourceId)).size === value.entries.length &&
    (value.selectedId === null || value.entries.some((item: ImportedSource) => item.result.sourceId === value.selectedId));
}
function validFacts(value: unknown): value is FactSnapshot {
  if (!object(value) || !exact(value, ["view", "assertions", "corrections"]) || !object(value.view) ||
      !exact(value.view, ["sheet", "pending", "stale", "error"]) ||
      value.view.pending !== false || value.view.error !== null ||
      typeof value.view.stale !== "boolean" ||
      !(value.view.sheet === null || validateFactSheet(value.view.sheet)) || !Array.isArray(value.assertions) ||
      !strings(value.corrections)) return false;
  const sheet = value.view.sheet;
  if (sheet === null) return value.assertions.length === 0 && Object.keys(value.corrections).length === 0;
  return value.assertions.every((item: unknown) => object(item) && item.origin === "user" && item.kind === "text" &&
    sheet.facts.some((fact: FactSheet["facts"][number]) => fact.id === item.id && JSON.stringify(fact) === JSON.stringify(item))) &&
    Object.entries(value.corrections).every(([sourceId, userId]) =>
      sheet.userCorrections?.[sourceId] === userId && sheet.facts.some((fact: FactSheet["facts"][number]) => fact.id === userId));
}
function validManual(value: unknown): value is ManualInput {
  if (!object(value) || !exact(value, ["name", "title", "asOf", "education", "language", "languages",
      "skills", "employment", "metrics", "leadership"]) ||
      !["name", "title", "asOf", "education"].every((key) => typeof value[key] === "string") ||
      !["ru", "en", "mixed"].includes(String(value.language)) ||
      !["languages", "skills", "employment", "metrics", "leadership"].every((key) => Array.isArray(value[key]))) return false;
  return (value.languages as unknown[]).every((item) => typeof item === "string") &&
    (value.skills as unknown[]).every((item) => typeof item === "string") &&
    (value.employment as unknown[]).every((item) => object(item) &&
      exact(item, ["id", "employer", "role", "start", "end", "description", "subprojects"]) &&
      ["id", "employer", "role", "start", "end", "description"].every((key) => typeof item[key] === "string") &&
      Array.isArray(item.subprojects) && item.subprojects.every((sub: unknown) => object(sub) &&
        exact(sub, ["id", "name", "start", "end", "description"]) &&
        ["id", "name", "start", "end", "description"].every((key) => typeof sub[key] === "string"))) &&
    (value.metrics as unknown[]).every((item) => object(item) &&
      exact(item, ["id", "jobId", "number", "upperNumber", "comparator", "unit", "period", "baseline",
        "result", "scope", "attribution", "qualifiers"]) && typeof item.id === "string" &&
      (item.jobId === null || typeof item.jobId === "string") && typeof item.number === "number" &&
      (item.upperNumber === null || typeof item.upperNumber === "number") &&
      ["exact", "at_least", "at_most", "approximately", "range"].includes(String(item.comparator)) &&
      (item.comparator === "range") === (item.upperNumber !== null) &&
      typeof item.unit === "string" && ["period", "baseline", "result", "scope"].every((key) =>
        item[key] === null || typeof item[key] === "string") &&
      ["personal", "team", "organization", "unknown"].includes(String(item.attribution)) &&
      stringArray(item.qualifiers)) &&
    (value.leadership as unknown[]).every((item) => object(item) &&
      exact(item, ["id", "jobId", "action", "attribution", "teamSize", "teamUnit", "teamBaseline"]) &&
      typeof item.id === "string" && typeof item.jobId === "string" && typeof item.action === "string" &&
      ["personal", "team", "organization", "unknown"].includes(String(item.attribution)) &&
      (item.teamSize === null || typeof item.teamSize === "number") && typeof item.teamUnit === "string" &&
      (item.teamBaseline === null || typeof item.teamBaseline === "string"));
}
function validWorking(value: unknown): value is WorkingRecord {
  return object(value) && optional(value, ["transportVersion", "sources", "sheet", "priorSheet",
    "sourceReviewStale", "manual", "draft"], ["transportVersion", "sources", "sheet", "priorSheet",
    "sourceReviewStale", "manual", "draft", "structuredCorrections", "coverage"]) &&
    value.transportVersion === 1 && Array.isArray(value.sources) &&
    value.sources.every((source: unknown) => object(source) && exact(source, ["entry", "originalRef"]) &&
      importedEntry(source.entry) &&
      typeof source.originalRef === "string" && safeArchivePath(source.originalRef)) &&
    validateFactSheet(value.sheet) && (value.priorSheet === null || validateFactSheet(value.priorSheet)) &&
    typeof value.sourceReviewStale === "boolean" && validManual(value.manual) &&
    (value.draft === null || validateDraftResult(value.draft)) &&
    (value.structuredCorrections === undefined || strings(value.structuredCorrections)) &&
    (value.coverage === undefined || coverage(value.coverage));
}
function validEditor(value: unknown, project: Project | null): value is EditorRecord {
  if (!object(value) || !exact(value, ["working", "presentation", "presentationDrafts", "presentationUndo", "stage",
      "panel", "selectedId", "drafts", "factDrafts", "structuredDrafts", "errors", "undo", "rewriteProposal",
      "rewriteIssues", "rewriteIssueDetails", "workingIssues", "sourceText", "dirty"]) ||
      !["import", "editor", "export"].includes(String(value.stage)) ||
      !["preview", "sources", "checks"].includes(String(value.panel)) ||
      !(value.selectedId === null || typeof value.selectedId === "string") ||
      !["drafts", "factDrafts", "structuredDrafts", "errors"].every((key) => strings(value[key])) ||
      !checkpoints(value.undo) || !object(value.rewriteIssues) ||
      !Object.values(value.rewriteIssues).every(stringArray) || !object(value.rewriteIssueDetails) ||
      !Object.values(value.rewriteIssueDetails).every(issues) ||
      !Array.isArray(value.workingIssues) || !value.workingIssues.every((item: unknown) => typeof item === "string") ||
      typeof value.sourceText !== "string" || typeof value.dirty !== "boolean" ||
      !(value.working === null || validWorking(value.working)) ||
      !(value.presentation === null || project && validatePresentation(value.presentation, project)) ||
      !(value.rewriteProposal === null || object(value.rewriteProposal) &&
        exact(value.rewriteProposal, ["result", "before"]) &&
        validateRewriteResult(value.rewriteProposal.result) && typeof value.rewriteProposal.before === "string") ||
      !(value.presentationUndo === null || project && validatePresentation(value.presentationUndo, project)) ||
      !object(value.presentationDrafts) || !optional(value.presentationDrafts, [], ["name", "title"]) ||
      !Object.values(value.presentationDrafts).every((item) => typeof item === "string")) return false;
  if (project === null && (value.working !== null || value.presentation !== null)) return false;
  if (project && (!object(value.undo) || !object(value.drafts) || !object(value.factDrafts) ||
      !object(value.rewriteIssues) || !object(value.rewriteIssueDetails) ||
      !Object.keys(value.undo).every((id) => project.views.some((block) => block.id === id)) ||
      !Object.keys(value.drafts).every((id) => project.views.some((block) => block.id === id)) ||
      !Object.keys(value.factDrafts).every((id) => project.facts.some((fact) => fact.id === id)) ||
      !Object.keys(value.rewriteIssues).every((id) => project.views.some((block) => block.id === id)) ||
      !Object.keys(value.rewriteIssueDetails).every((id) => project.views.some((block) => block.id === id)))) return false;
  if (project && object(value.undo) && Object.entries(value.undo).some(([id, checkpoint]) =>
    !object(checkpoint) || !blockState(checkpoint.state) ||
    !object(checkpoint.state) || !stringArray(checkpoint.state.factIds) ||
    checkpoint.state.factIds.some((factId) => !project.facts.some((fact) => fact.id === factId)) ||
    Number(checkpoint.revision) > (project.views.find((block) => block.id === id)?.revision ?? 0))) return false;
  return value.selectedId === null || project?.views.some((block) => block.id === value.selectedId) === true;
}

function coherentWorking(project: Project, working: WorkingDraft): boolean {
  const sources = new Map(project.sources.map((source) => [source.id, source]));
  if (working.sources.length !== sources.size || new Set(working.sources.map((source) => source.entry.result.sourceId)).size !== sources.size)
    return false;
  for (const { entry } of working.sources) {
    const source = sources.get(entry.result.sourceId);
    if (!source || source.byteSha256 !== entry.result.byteSha256 || source.originalName !== entry.result.originalName ||
        source.parser !== entry.result.parser || source.parserVersion !== entry.result.parserVersion ||
        source.units.length !== entry.result.units.length || source.units.some((unit, index) =>
          unit.id !== `view_${source.id}_${entry.result.units[index]?.id}` ||
          unit.text !== entry.result.units[index]?.text)) return false;
  }
  for (const job of working.manual.employment) {
    const fact = project.facts.find((item) => item.id === `fact_user_manual_job_${job.id}`);
    if (fact?.kind !== "text" || fact.value.text !== job.description.trim()) return false;
    for (const sub of job.subprojects) {
      const subFact = project.facts.find((item) => item.id === `fact_user_manual_sub_${sub.id}`);
      if (subFact?.kind !== "text" || subFact.value.text !== sub.description.trim()) return false;
    }
  }
  return true;
}
function validateManifest(value: unknown, files: Map<string, Uint8Array>): Manifest {
  if (!validateContract("archive_manifest", value) || !object(value) ||
      !exact(value, ["schemaVersion", "appVersion", "rendererVersion", "templatePackageSha256", "templateAssetsIncluded", "projectId", "entries"]) ||
      value.schemaVersion !== 4 || typeof value.appVersion !== "string" ||
      !(value.projectId === null || typeof value.projectId === "string") ||
      !(value.rendererVersion === null || typeof value.rendererVersion === "string") ||
      !(value.templatePackageSha256 === null || typeof value.templatePackageSha256 === "string") ||
      !Array.isArray(value.entries) || value.entries.length !== files.size - 1) throw new Error("Unsupported project version.");
  const seen = new Set<string>();
  const entries: ManifestEntry[] = [];
  for (const item of value.entries) {
    if (!object(item) || !exact(item, ["path", "role", "sha256", "uncompressedSize"]) ||
        typeof item.path !== "string" || !safeArchivePath(item.path) ||
        !["project", "workspace", "source_original", "template_asset", "render"].includes(String(item.role)) ||
        typeof item.sha256 !== "string" || !hashPattern.test(item.sha256) ||
        !Number.isInteger(item.uncompressedSize) || Number(item.uncompressedSize) < 0 || seen.has(item.path) ||
        !files.has(item.path)) throw new Error("Invalid project manifest.");
    seen.add(item.path);
    entries.push({ path: item.path, role: item.role as Role, sha256: item.sha256,
      uncompressedSize: Number(item.uncompressedSize) });
  }
  if (!seen.has("workspace.json") || entries.filter((item) => item.role === "workspace").length !== 1 ||
      entries.find((item) => item.role === "workspace")?.path !== "workspace.json" ||
      entries.filter((item) => item.role === "project").length !== (value.projectId === null ? 0 : 1) ||
      (value.projectId !== null && entries.find((item) => item.role === "project")?.path !== "project.json") ||
      [...files.keys()].some((name) => name !== "manifest.json" && !seen.has(name))) throw new Error("Incomplete project manifest.");
  if (entries.some((entry) => entry.role === "render" &&
      !["renders/preview.pdf", "renders/resume.docx", "renders/request.json"].includes(entry.path)) ||
      entries.some((entry) => entry.role === "template_asset" && !entry.path.startsWith("template/") ||
        entry.role === "source_original" && !entry.path.startsWith("sources/") && entry.path !== "legacy/v2/original"))
    throw new Error("Unknown project archive entry.");
  return { schemaVersion: 4, appVersion: value.appVersion, rendererVersion: value.rendererVersion,
    templatePackageSha256: value.templatePackageSha256, templateAssetsIncluded: value.templateAssetsIncluded as boolean,
    projectId: value.projectId, entries };
}

function validProject(value: unknown): value is Project {
  return validateContract("project", value) && trusted(value as Project);
}

async function openVersion3(raw: Record<string, unknown>, files: Map<string, Uint8Array>): Promise<OpenedArchive> {
  if (!validateContract("zip_manifest", raw) || !Array.isArray(raw.entries) ||
      raw.entries.length !== files.size - 1) throw new Error("Invalid version 3 manifest.");
  const entries = raw.entries as unknown[];
  for (const item of entries) {
    if (!object(item) || typeof item.path !== "string" || typeof item.sha256 !== "string" ||
        typeof item.uncompressedSize !== "number" || typeof item.role !== "string")
      throw new Error("Invalid version 3 entry.");
    const data = files.get(item.path);
    if (!data || data.length !== item.uncompressedSize || await sha256(data) !== item.sha256)
      throw new Error("Version 3 file hash does not match.");
  }
  const data = parse(files.get("project.json"));
  if (!validProject(data) || data.projectId !== raw.projectId) throw new Error("Invalid version 3 project.");
  const projectOriginals: Record<string, Uint8Array> = {};
  for (const source of data.sources) {
    const entry = entries.find((item) => object(item) && item.path === source.byteRef);
    const original = files.get(source.byteRef);
    if (!object(entry) || entry.role !== "source_original" || !original ||
        await sha256(original) !== source.byteSha256)
      throw new Error("Version 3 original is missing or changed.");
    projectOriginals[source.id] = Uint8Array.from(original);
  }
  const templateEntries = new Map(entries.filter((item) => object(item) && item.role === "template_asset" &&
    typeof item.path === "string").map((item) => [String((item as Record<string, unknown>).path),
    files.get(String((item as Record<string, unknown>).path))!]));
  if (templateEntries.size > 0 && (!data.template || !await verifiedTemplateAssets(templateEntries)))
    throw new Error("Version 3 template assets are invalid.");
  const editor: EditorState = { ...initialEditorState, project: data, loadId: crypto.randomUUID(),
    stage: "editor", selectedId: data.views[0]?.id ?? null, dirty: true,
    workingIssues: ["Архив v3 не содержит данные кандидата и привязку работ. Заполните их перед сборкой документа."] };
  return { editor, imports: { state: { entries: [], selectedId: null, pending: false, error: null }, originals: {} },
    facts: { view: { sheet: null, pending: false, stale: false, error: null }, assertions: [], corrections: {} },
    projectOriginals, legacy: null, trustedAssets: templateEntries.size ? templateEntries : null,
    manualForm: structuredClone(emptyManualInput), assertionDraft: "", factEdits: {},
    rewriteInstruction: "", render: null,
    migration: "Открыт архив v3. Данные кандидата и привязку работ нужно указать явно." };
}

async function openVersion2(files: Map<string, Uint8Array>): Promise<OpenedArchive> {
  const archive = parse(files.get("archive.json"));
  if (!validLegacyArchive(archive)) throw new Error("Invalid version 2 experiment archive.");
  const snapshotName = archive.source_snapshot;
  if (typeof snapshotName !== "string") throw new Error("Invalid version 2 source name.");
  if ([...files.keys()].some((name) => !["archive.json", "source.json", "units.txt", "view.json", snapshotName].includes(name)))
    throw new Error("Unexpected version 2 archive entry.");
  const original = files.get(snapshotName);
  if (!original || !original.length) throw new Error("Version 2 original is missing.");
  if (!object(archive.source) || archive.source.sha256 !== await sha256(original) ||
      JSON.stringify(archive.source) !== JSON.stringify(parse(files.get("source.json"))))
    throw new Error("Version 2 source does not match the original.");
  const rawView = files.has("view.json") ? parse(files.get("view.json")) : null;
  if (rawView !== null && (!object(rawView) || !finite(rawView) || !noCredentialKeys(rawView)))
    throw new Error("Invalid version 2 selected view.");
  const view = rawView as Record<string, unknown> | null;
  if (view && view.archive_sha256 !== await sha256(files.get("archive.json")!))
    throw new Error("Version 2 selected view does not match archive.");
  let editor: EditorState = { ...initialEditorState, dirty: true };
  let projectOriginals: Record<string, Uint8Array> = {};
  if (view) {
    const selected = migrateSelectedView(archive, view, await sha256(original), snapshotName);
    editor = { ...initialEditorState, project: selected.project, presentation: selected.presentation,
      loadId: crypto.randomUUID(), stage: "editor", selectedId: selected.project.views[0]?.id ?? null,
      dirty: true, workingIssues: ["Выбранный вид v2 перенесён как текст. Проверьте перенос перед новыми правками."] };
    projectOriginals = { [selected.project.sources[0]!.id]: Uint8Array.from(original) };
  }
  return { editor, imports: { state: { entries: [], selectedId: null, pending: false, error: null }, originals: {} },
    facts: { view: { sheet: null, pending: false, stale: false, error: null }, assertions: [], corrections: {} },
    projectOriginals, legacy: { archive, originalName: snapshotName,
      originalBytes: Uint8Array.from(original), view }, trustedAssets: null,
    manualForm: structuredClone(emptyManualInput),
    assertionDraft: "", factEdits: {}, rewriteInstruction: "", render: null,
    migration: view ? "Открыт выбранный вид v2. Текст перенесён без перевода и требует проверки." :
      "Открыт экспериментальный архив v2. Старые данные сохранены; повторите локальное извлечение исходника." };
}

export async function saveProject(input: ArchiveInput): Promise<Uint8Array> {
  const project = input.editor.project ? sanitizedProject(input.editor.project) : null;
  if (!project && !input.legacy && !input.imports.state.entries.length && !input.editor.sourceText.trim() &&
      JSON.stringify(input.manualForm) === JSON.stringify(emptyManualInput) && !input.facts.view.sheet &&
      !input.assertionDraft.trim() && !Object.keys(input.factEdits).length)
    throw new Error("There is no project data to save.");
  if (!validImportState({ ...input.imports.state, pending: false, error: null }) ||
      !validFacts({ ...input.facts, view: { ...input.facts.view, pending: false, error: null } }) ||
      !validManual(input.manualForm)) throw new Error("Project state is invalid.");
  const originals = originalMap(input);
  const entries = new Map<string, Uint8Array>();
  let legacy: LegacyRecord | null = null;
  if (input.legacy) {
    if (!validLegacyArchive(input.legacy.archive) ||
        input.legacy.originalName !== input.legacy.archive.source_snapshot ||
        !object(input.legacy.archive.source))
      throw new Error("Legacy project data is invalid.");
    const originalRef = "legacy/v2/original";
    const originalBytes = Uint8Array.from(input.legacy.originalBytes);
    const originalSha256 = await sha256(originalBytes);
    if (originalSha256 !== input.legacy.archive.source.sha256)
      throw new Error("Legacy original does not match its source archive.");
    entries.set(originalRef, originalBytes);
    legacy = { format: "v2", archive: structuredClone(input.legacy.archive), originalRef,
      originalName: input.legacy.originalName, originalSha256,
      view: input.legacy.view === null ? null : structuredClone(input.legacy.view) };
  }
  if (input.trustedAssets) {
    if (!project?.template || !await verifiedTemplateAssets(input.trustedAssets))
      throw new Error("Template assets do not match the trusted package.");
    for (const [path, bytes] of input.trustedAssets) entries.set(path, Uint8Array.from(bytes));
  }
  const refs: Record<string, string> = {};
  const sourceIds = new Set<string>();
  for (const entry of input.imports.state.entries) sourceIds.add(entry.result.sourceId);
  for (const source of input.editor.working?.sources ?? []) sourceIds.add(source.entry.result.sourceId);
  for (const source of project?.sources ?? []) sourceIds.add(source.id);
  for (const id of sourceIds) {
    const bytes = originals.get(id);
    const workingSource = input.editor.working?.sources.find((source) => source.entry.result.sourceId === id);
    const importedSource = input.imports.state.entries.find((entry) => entry.result.sourceId === id);
    const projectSource = project?.sources.find((source) => source.id === id);
    const expected = workingSource?.entry.result.byteSha256 ?? importedSource?.result.byteSha256 ?? projectSource?.byteSha256;
    if (!bytes || !expected || await sha256(bytes) !== expected) throw new Error("Original source bytes are missing or changed.");
    const path = projectSource?.byteRef ?? `sources/${expected}/original`;
    if (!safeArchivePath(path) || entries.has(path) && path !== legacy?.originalRef)
      throw new Error("Original source references conflict.");
    if (!entries.has(path)) entries.set(path, bytes);
    refs[id] = path;
  }
  const editor = project ? recordEditor(input.editor, project) : null;
  if (editor && !validEditor(editor, project)) throw new Error("Editor state is invalid.");
  if (project && input.editor.working && !coherentWorking(project, input.editor.working))
    throw new Error("Working source and project disagree.");
  const workspace: Workspace = { schemaVersion: 4, editor, importState: { ...structuredClone(input.imports.state), pending: false, error: null },
    importOriginals: Object.fromEntries(input.imports.state.entries.map((entry) =>
      [entry.result.sourceId, refs[entry.result.sourceId]!])),
    facts: { ...structuredClone(input.facts), view: { ...structuredClone(input.facts.view), pending: false, error: null } },
    manualForm: structuredClone(input.manualForm), assertionDraft: input.assertionDraft,
    factEdits: { ...input.factEdits }, rewriteInstruction: input.rewriteInstruction,
    preEditorSourceText: input.editor.sourceText, renderBinding: null, legacy };
  entries.set("workspace.json", json(workspace));
  if (project) entries.set("project.json", json(project));
  const manifestEntries: ManifestEntry[] = [];
  for (const [path, bytes] of entries) manifestEntries.push({ path,
    role: path === "workspace.json" ? "workspace" : path === "project.json" ? "project" :
      path.startsWith("renders/") ? "render" : path.startsWith("template/") ? "template_asset" : "source_original",
    sha256: await sha256(bytes), uncompressedSize: bytes.length });
  const manifest: Manifest = { schemaVersion: 4, appVersion: "0.1.0", projectId: project?.projectId ?? null,
    rendererVersion: project?.template ? "1.0.0" : null,
    templatePackageSha256: project?.template?.packageSha256 ?? null,
    templateAssetsIncluded: input.trustedAssets !== null,
    entries: manifestEntries };
  entries.set("manifest.json", json(manifest));
  return writeZip(entries);
}

export async function openProject(bytes: Uint8Array): Promise<OpenedArchive> {
  const files = readZip(bytes);
  if (!files.has("manifest.json") && files.has("archive.json")) return openVersion2(files);
  const rawManifest = parse(files.get("manifest.json"));
  if (object(rawManifest) && rawManifest.schemaVersion === 3) return openVersion3(rawManifest, files);
  const manifest = validateManifest(rawManifest, files);
  for (const entry of manifest.entries) {
    const bytes = files.get(entry.path);
    if (!bytes || bytes.length !== entry.uncompressedSize || await sha256(bytes) !== entry.sha256)
      throw new Error("Project file hash does not match.");
  }
  const rawProject = manifest.projectId === null ? null : parse(files.get("project.json"));
  if (rawProject !== null && (!validProject(rawProject) || rawProject.projectId !== manifest.projectId))
    throw new Error("Project data is invalid.");
  const project = rawProject as Project | null;
  if ((project?.template?.packageSha256 ?? null) !== manifest.templatePackageSha256 ||
      (project?.template ? "1.0.0" : null) !== manifest.rendererVersion)
    throw new Error("Project template identity does not match manifest.");
  const raw = parse(files.get("workspace.json"));
  const templateEntries = new Map(manifest.entries.filter((entry) => entry.role === "template_asset").map((entry) =>
    [entry.path, files.get(entry.path)!]));
  if (templateEntries.size > 0 && (!project?.template || !await verifiedTemplateAssets(templateEntries)))
    throw new Error("Archived template assets do not match the trusted package.");
  if (manifest.templateAssetsIncluded !== (templateEntries.size > 0))
    throw new Error("Template asset status does not match archive.");
  if (!object(raw) || !exact(raw, ["schemaVersion", "editor", "importState", "importOriginals", "facts",
      "manualForm", "assertionDraft", "factEdits", "rewriteInstruction", "preEditorSourceText", "renderBinding", "legacy"]) || !finite(raw) ||
      raw.schemaVersion !== 4 || !validImportState(raw.importState) || !strings(raw.importOriginals) ||
      !validFacts(raw.facts) || !validManual(raw.manualForm) || typeof raw.assertionDraft !== "string" ||
      !strings(raw.factEdits) || typeof raw.rewriteInstruction !== "string" ||
      typeof raw.preEditorSourceText !== "string" ||
      !(raw.renderBinding === null || typeof raw.renderBinding === "string" && hashPattern.test(raw.renderBinding)) ||
      !(raw.legacy === null || validLegacyRecord(raw.legacy)) ||
      !(raw.editor === null || validEditor(raw.editor, project)) || (project === null) !== (raw.editor === null))
    throw new Error("Project workspace is invalid.");
  const workspace = raw as Workspace;
  if (workspace.editor && workspace.editor.sourceText !== workspace.preEditorSourceText)
    throw new Error("Project source draft does not match workspace.");
  const referencedOriginals = new Set<string>();
  for (const source of project?.sources ?? []) referencedOriginals.add(source.byteRef);
  for (const source of workspace.importState.entries) {
    const ref = workspace.importOriginals[source.result.sourceId];
    if (ref) referencedOriginals.add(ref);
  }
  for (const source of workspace.editor?.working?.sources ?? []) referencedOriginals.add(source.originalRef);
  if (workspace.legacy) referencedOriginals.add(workspace.legacy.originalRef);
  if (Object.keys(workspace.importOriginals).length !== workspace.importState.entries.length ||
      workspace.importState.entries.some((entry) => !Object.hasOwn(workspace.importOriginals, entry.result.sourceId)) ||
      manifest.entries.some((entry) => entry.role === "source_original" && !referencedOriginals.has(entry.path)) ||
      [...referencedOriginals].some((path) => manifest.entries.find((entry) => entry.path === path)?.role !== "source_original"))
    throw new Error("Project source references are incomplete.");
  let legacy: LegacyV2 | null = null;
  if (workspace.legacy) {
    const data = files.get(workspace.legacy.originalRef);
    if (!data || !object(workspace.legacy.archive.source) ||
        workspace.legacy.originalSha256 !== workspace.legacy.archive.source.sha256 ||
        await sha256(data) !== workspace.legacy.originalSha256)
      throw new Error("Legacy original is missing or changed.");
    legacy = { archive: workspace.legacy.archive, originalName: workspace.legacy.originalName,
      originalBytes: Uint8Array.from(data), view: workspace.legacy.view };
  }
  const originals: Record<string, Uint8Array> = {};
  for (const entry of workspace.importState.entries) {
    const ref = workspace.importOriginals[entry.result.sourceId];
    const data = ref ? files.get(ref) : undefined;
    if (!data || await sha256(data) !== entry.result.byteSha256 || data.length !== entry.result.byteLength)
      throw new Error("Imported original does not match extraction.");
    originals[entry.result.sourceId] = data;
  }
  const working = workspace.editor?.working ?? null;
  const restoredWorking: WorkingDraft | null = working ? { ...working,
    sources: await Promise.all(working.sources.map(async ({ entry, originalRef }) => {
      const data = files.get(originalRef);
      if (!data || data.length !== entry.result.byteLength || await sha256(data) !== entry.result.byteSha256)
        throw new Error("Working original does not match extraction.");
      return { entry, originalBytes: Uint8Array.from(data) };
    })) } : null;
  if (project && restoredWorking && !coherentWorking(project, restoredWorking))
    throw new Error("Working source and project disagree.");
  const projectOriginals: Record<string, Uint8Array> = {};
  for (const source of project?.sources ?? []) {
    const original = files.get(source.byteRef);
    if (!original || await sha256(original) !== source.byteSha256) throw new Error("Project original is missing or changed.");
    projectOriginals[source.id] = Uint8Array.from(original);
  }
  const editor: EditorState = workspace.editor ? { ...workspace.editor, project, working: restoredWorking,
    loadId: crypto.randomUUID(), sourceIntegrity: null, dirty: true } :
    { project: null, loadId: null, working: null, sourceIntegrity: null, workingIssues: [],
      presentation: null, presentationDrafts: {}, presentationUndo: null, stage: "import", panel: "preview",
      selectedId: null, drafts: {}, factDrafts: {}, structuredDrafts: {}, errors: {}, undo: {}, rewriteProposal: null,
      rewriteIssues: {}, rewriteIssueDetails: {}, sourceText: workspace.preEditorSourceText, dirty: true };
  const pdf = files.get("renders/preview.pdf");
  const docx = files.get("renders/resume.docx");
  const request = files.get("renders/request.json");
  if ([pdf, docx, request].some(Boolean)) {
    const rawRequest = parse(request);
    if (!pdf || !docx || !project || !editor.presentation || !await validateRenderRequest(rawRequest))
      throw new Error("Saved render does not match this project.");
    const savedRequest = rawRequest as Rendered["request"];
    if (workspace.renderBinding !== await sha256(json({ project, presentation: editor.presentation })) ||
        savedRequest.baseRevision !== project.revision || savedRequest.snapshot.projectRevision !== project.revision ||
        savedRequest.document.candidate.name !== editor.presentation.name ||
        savedRequest.document.candidate.title !== editor.presentation.title ||
        savedRequest.snapshot.templatePackageSha256 !== trustedTemplate ||
        decoder.decode(pdf.subarray(0, 4)) !== "%PDF" || docx[0] !== 0x50 || docx[1] !== 0x4b)
      throw new Error("Saved render does not match this project.");
  } else if (workspace.renderBinding !== null) throw new Error("Render binding lacks artifacts.");
  const migration = [
    project?.template && !manifest.templateAssetsIncluded ?
      "Архив восстановлен без файлов шаблона. Локальный шаблон нужен для новой сборки." : null,
    pdf ? "Сохранённый PDF и DOCX требуют новой локальной сборки перед просмотром и скачиванием." : null,
  ].filter(Boolean).join(" ") || null;
  return { editor, imports: { state: workspace.importState, originals }, facts: workspace.facts,
    projectOriginals, legacy, trustedAssets: templateEntries.size ? templateEntries : null,
    manualForm: workspace.manualForm, assertionDraft: workspace.assertionDraft, factEdits: workspace.factEdits,
    rewriteInstruction: workspace.rewriteInstruction, render: null, migration };
}
