import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import projectSchema from "../../../../contracts/json-schema/project.schema.json" with { type: "json" };
import proposalSchema from "../../../../contracts/json-schema/proposal.schema.json" with { type: "json" };
import templateSchema from "../../../../contracts/json-schema/template.schema.json" with { type: "json" };
import zipSchema from "../../../../contracts/json-schema/zip_manifest.schema.json" with { type: "json" };
import renderSchema from "../../../../contracts/json-schema/render_request.schema.json" with { type: "json" };
import prepareSchema from "../../../../contracts/json-schema/prepare_request.schema.json" with { type: "json" };
import extractSchema from "../../../../contracts/json-schema/extract_result.schema.json" with { type: "json" };
import factSheetSchema from "../../../../contracts/json-schema/fact_sheet.schema.json" with { type: "json" };
import factRequestSchema from "../../../../contracts/json-schema/fact_request.schema.json" with { type: "json" };
import semanticProposalSchema from "../../../../contracts/json-schema/semantic_proposal.schema.json" with { type: "json" };
import draftRequestSchema from "../../../../contracts/json-schema/draft_request.schema.json" with { type: "json" };
import draftProposalSchema from "../../../../contracts/json-schema/draft_proposal.schema.json" with { type: "json" };
import draftResultSchema from "../../../../contracts/json-schema/draft_result.schema.json" with { type: "json" };
import rewriteRequestSchema from "../../../../contracts/json-schema/rewrite_request.schema.json" with { type: "json" };
import rewriteResultSchema from "../../../../contracts/json-schema/rewrite_result.schema.json" with { type: "json" };
import rewritePreflightFailureSchema from "../../../../contracts/json-schema/rewrite_preflight_failure.schema.json" with { type: "json" };
import type { Project, PartialDate, Period } from "./generated/project.js";
import type { ZipManifest } from "./generated/zip_manifest.js";
import type { TemplateManifest } from "./generated/template.js";
import type { RenderRequest } from "./generated/render_request.js";
import type { PrepareRequest } from "./generated/prepare_request.js";
import type { ExtractResult } from "./generated/extract_result.js";
import type { FactSheet } from "./generated/fact_sheet.js";
import type { FactRequest } from "./generated/fact_request.js";
import type { SemanticProposal } from "./generated/semantic_proposal.js";
import type { DraftRequest } from "./generated/draft_request.js";
import type { DraftProposal } from "./generated/draft_proposal.js";
import type { DraftResult } from "./generated/draft_result.js";
import type { RewriteRequest } from "./generated/rewrite_request.js";
import type { RewriteResult } from "./generated/rewrite_result.js";
import type { RewritePreflightFailure } from "./generated/rewrite_preflight_failure.js";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const projectShape = ajv.compile<Project>(projectSchema);
const proposalShape = ajv.compile(proposalSchema);
const templateShape = ajv.compile<TemplateManifest>(templateSchema);
const zipShape = ajv.compile<ZipManifest>(zipSchema);
const renderShape = ajv.compile<RenderRequest>(renderSchema);
const prepareShape = ajv.compile<PrepareRequest>(prepareSchema);
const extractShape = ajv.compile<ExtractResult>(extractSchema);
const factSheetShape = ajv.compile<FactSheet>(factSheetSchema);
const factRequestShape = ajv.compile<FactRequest>(factRequestSchema);
const semanticProposalShape = ajv.compile<SemanticProposal>(semanticProposalSchema);
const draftRequestShape = ajv.compile<DraftRequest>(draftRequestSchema);
const draftProposalShape = ajv.compile<DraftProposal>(draftProposalSchema);
const draftResultShape = ajv.compile<DraftResult>(draftResultSchema);
const rewriteRequestShape = ajv.compile<RewriteRequest>(rewriteRequestSchema);
const rewriteResultShape = ajv.compile<RewriteResult>(rewriteResultSchema);
const rewritePreflightFailureShape = ajv.compile<RewritePreflightFailure>(rewritePreflightFailureSchema);

export function validateRewriteRequest(value: unknown): value is RewriteRequest {
  if (!finiteJson(value) || !rewriteRequestShape(value) || !wellFormedUnicode(value)) return false;
  const ids = new Set(value.facts.map((fact) => fact.id));
  return ids.size === value.facts.length && unique(value.requiredFactIds) &&
    value.requiredFactIds.every((id) => ids.has(id)) && value.excerpts.every((item) => ids.has(item.factId));
}

export function validateRewriteResult(value: unknown): value is RewriteResult {
  return finiteJson(value) && rewriteResultShape(value) && wellFormedUnicode(value) && unique(value.factIds);
}

export function validateRewritePreflightFailure(value: unknown): value is RewritePreflightFailure {
  return finiteJson(value) && rewritePreflightFailureShape(value) && wellFormedUnicode(value) &&
    unique(value.issues.map((issue) => issue.factId)) &&
    value.issues.every((issue) => issue.code === "SOURCE_REVIEW" && issue.blockId === value.blockId);
}

export function validateDraftRequest(value: unknown): value is DraftRequest {
  return finiteJson(value) && draftRequestShape(value) && wellFormedUnicode(value) &&
    value.sourceFingerprint === value.sheet.sourceFingerprint && value.baseRevision === value.sheet.revision &&
    validateFactSheet(value.sheet);
}

export function validateDraftProposal(value: unknown): value is DraftProposal {
  return finiteJson(value) && draftProposalShape(value) && wellFormedUnicode(value) &&
    unique(value.blocks.map((block) => block.blockId)) && value.blocks.every((block) => unique(block.factIds));
}

export function validateDraftResult(value: unknown): value is DraftResult {
  return finiteJson(value) && draftResultShape(value) && wellFormedUnicode(value) &&
    unique(value.blocks.map((block) => block.blockId));
}

export function validateFactRequest(value: unknown): value is FactRequest {
  if (!finiteJson(value) || !factRequestShape(value) || !wellFormedUnicode(value)) return false;
  const ids = new Set(value.sources.map((source) => source.result.sourceId));
  if (ids.size !== value.sources.length) return false;
  let originalBytes = 0;
  let extractedBytes = 0;
  let overlayBytes = 0;
  for (const source of value.sources) {
    if (!validateExtractResult(source.result)) return false;
    originalBytes += source.result.byteLength;
    extractedBytes += source.result.units.reduce((count, unit) => count + new TextEncoder().encode(unit.text).length, 0);
    const targets = new Set([...source.result.units.map((unit) => `unit:${unit.id}`),
      ...source.result.gaps.map((_, index) => `gap:${index}`)]);
    for (const [target, text] of Object.entries(source.overlays)) {
      const size = new TextEncoder().encode(text).length;
      if (!targets.has(target) || size > 65_536) return false;
      overlayBytes += size;
    }
  }
  return originalBytes <= 32 * 1024 * 1024 && extractedBytes <= 8 * 1024 * 1024 && overlayBytes <= 1024 * 1024;
}

export function validateSemanticProposal(value: unknown): value is SemanticProposal {
  if (!finiteJson(value) || !semanticProposalShape(value) || !wellFormedUnicode(value)) return false;
  return value.facts.every((fact) => {
    const candidate = fact.value;
    if (typeof candidate !== "object" || candidate === null) return false;
    if (fact.kind === "text") return "text" in candidate;
    if (fact.kind === "technology") return "canonicalId" in candidate;
    if (fact.kind === "date") return "precision" in candidate;
    if (fact.kind === "metric") return "comparator" in candidate;
    return "action" in candidate;
  });
}

export function validateFactSheet(value: unknown): value is FactSheet {
  if (!finiteJson(value) || !factSheetShape(value) || !wellFormedUnicode(value)) return false;
  const facts = new Map(value.facts.map((fact) => [fact.id, fact]));
  if (facts.size !== value.facts.length || !unique(value.candidates.map((item) => item.id)) ||
      !unique(value.issues.map((item) => item.id))) return false;
  const units = new Map<string, Set<string>>();
  for (const unit of value.units) {
    const key = `${unit.sourceId}:${unit.unitId}`;
    if (units.has(key) || !unique(unit.factIds) || !unit.factIds.every((id) => facts.has(id))) return false;
    units.set(key, new Set(unit.factIds));
  }
  const proposed = new Set(value.proposedFactIds ?? []);
  if (proposed.size !== (value.proposedFactIds ?? []).length || [...proposed].some((id) => !facts.has(id))) return false;
  const overlayRefs = value.overlayFactRefs ?? {};
  if (Object.entries(overlayRefs).some(([id]) => !proposed.has(id) || facts.get(id)?.origin !== "user")) return false;
  if (Object.entries(value.userCorrections ?? {}).some(([sourceId, userId]) =>
      facts.get(sourceId)?.origin !== "source" || facts.get(userId)?.origin !== "user")) return false;
  for (const unit of value.units) {
    if ((unit.disposition === "duplicate" && (!unit.duplicateOf || unit.factIds.length > 0)) ||
        (unit.duplicateOf && !units.has(unit.duplicateOf))) return false;
  }
  for (const fact of value.facts) {
    if (fact.origin === "source" ? fact.evidence.length === 0 : fact.evidence.length > 0) return false;
    if (![...fact.evidence, ...(overlayRefs[fact.id] ?? [])].every((evidence) =>
      evidence.sourceRevision === 1 && evidence.unitRevision === 1 &&
      units.get(`${evidence.sourceId}:${evidence.unitId}`)?.has(fact.id))) return false;
    if (fact.kind === "date" && !dateOk(fact.value)) return false;
    if (fact.kind === "metric" && !metricOk(fact.value) ||
        fact.kind === "leadership" && fact.value.teamSize !== null && !metricOk(fact.value.teamSize)) return false;
  }
  if (value.candidates.some((item) => !units.has(`${item.sourceId}:${item.unitId}`)) ||
      value.issues.some((item) => item.unitId != null && !units.has(`${item.sourceId}:${item.unitId}`))) return false;
  const employment = value.employment ?? [];
  const jobs = new Map(employment.map((job) => [job.id, job]));
  if (jobs.size !== employment.length) return false;
  const subprojects = new Set<string>();
  for (const job of employment) {
    if (job.periods.some((period) => !periodOk(period)) ||
        job.unitIds.some((id) => !units.has(`${job.sourceId}:${id}`)) ||
        job.factIds.some((id) => !facts.has(id)) ||
        !unique(job.factIds) ||
        job.factIds.length !== value.facts.filter((fact) => fact.jobId === job.id).length ||
        value.facts.some((fact) => fact.jobId === job.id && !job.factIds.includes(fact.id))) return false;
    for (const sub of job.subprojects) {
      if (subprojects.has(sub.id) || sub.sourceId !== job.sourceId ||
          sub.period != null && !periodOk(sub.period) ||
          sub.unitIds.some((id) => !units.has(`${sub.sourceId}:${id}`))) return false;
      subprojects.add(sub.id);
    }
  }
  return value.facts.every((fact) => fact.jobId === null ? fact.subprojectId === null :
    jobs.has(fact.jobId) && (fact.subprojectId === null ||
      jobs.get(fact.jobId)?.subprojects.some((sub) => sub.id === fact.subprojectId)));
}

export function validateExtractResult(value: unknown): value is ExtractResult {
  if (!finiteJson(value) || !extractShape(value) || !wellFormedUnicode(value)) return false;
  if (value.sourceId !== `source_${value.byteSha256.slice(0, 24)}` || value.byteRef !== `memory:sha256:${value.byteSha256}` ||
      (value.sourceKind === "pdf") !== (value.pageCount !== null && value.pageCount !== undefined)) return false;
  let bytes = 0;
  let chars = 0;
  for (const [index, unit] of value.units.entries()) {
    if (unit.order !== index || unit.id !== `unit_${index + 1}`) return false;
    bytes += new TextEncoder().encode(unit.text).length;
    chars += [...unit.text].length;
    if (bytes > 2 * 1024 * 1024 || chars > 750_000) return false;
  }
  return value.pageCount === null || value.pageCount === undefined ||
    [...value.units.map((unit) => unit.location), ...value.gaps.map((gap) => gap.location)]
      .every((location) => location.page === null || location.page === undefined || location.page <= value.pageCount!);
}

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b, "en")).map(([key, part]) => [key, ordered(part)]));
  }
  return value;
}

function safeRenderText(value: unknown): boolean {
  let size = 0;
  function visit(part: unknown): boolean {
    if (typeof part === "string") {
      size += [...part].length;
      return size <= 100_000 && [...part].every((character) => character === "\n" || character === "\t" || character.charCodeAt(0) >= 32);
    }
    if (Array.isArray(part)) return part.every(visit);
    if (typeof part === "object" && part !== null) return Object.values(part).every(visit);
    return true;
  }
  return visit(value);
}

function wellFormedUnicode(value: unknown): boolean {
  if (typeof value === "string") return [...value].every((character) =>
    character.length !== 1 || character.charCodeAt(0) < 0xd800 || character.charCodeAt(0) > 0xdfff);
  if (Array.isArray(value)) return value.every(wellFormedUnicode);
  if (typeof value === "object" && value !== null) return Object.values(value).every(wellFormedUnicode);
  return true;
}

export async function validateRenderRequest(value: unknown): Promise<boolean> {
  if (!finiteJson(value) || !renderShape(value) || !wellFormedUnicode(value)) return false;
  if (value.baseRevision !== value.snapshot.projectRevision) return false;
  if (!safeRenderText(value.document)) return false;
  const boundedItem = (item: string): boolean => [...item].length <= 4000;
  if (value.document.sidebar.some((section) => !section.items.every(boundedItem)) ||
      value.document.projects.some((project) => !project.tasks.every(boundedItem) || !project.results.every(boundedItem)) ||
      !value.document.achievements.every(boundedItem)) return false;
  const { snapshotSha256, ...snapshot } = value.snapshot;
  const bytes = new TextEncoder().encode(JSON.stringify(ordered({ baseRevision: value.baseRevision, document: value.document, snapshot })));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (part) => part.toString(16).padStart(2, "0")).join("");
  return hex === snapshotSha256;
}

function finiteJson(value: unknown, seen = new WeakSet<object>()): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || value === null) return true;
  if (seen.has(value)) return false;
  seen.add(value);
  const values: unknown[] = Array.isArray(value) ? value : Object.values(value);
  return values.every((part) => finiteJson(part, seen));
}

function unique(ids: string[]): boolean {
  return new Set(ids).size === ids.length;
}

function refs(ids: string[], valid: Set<string>): boolean {
  return ids.every((id) => valid.has(id));
}

function safePath(path: string): boolean {
  return path.length > 0 && !path.startsWith("/") && !path.includes("\\") && path.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}

function isLeap(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function dateOk(value: PartialDate): boolean {
  if (!Number.isInteger(value.year) || value.year < 1 || value.year > 9999) return false;
  if (value.precision === "year") return value.month === null && value.day === null;
  if (value.month === null || !Number.isInteger(value.month) || value.month < 1 || value.month > 12) return false;
  if (value.precision === "month") return value.day === null;
  if (value.day === null || !Number.isInteger(value.day)) return false;
  const monthDays = [31, isLeap(value.year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return value.day >= 1 && value.day <= (monthDays[value.month - 1] ?? 0);
}

function dateLower(value: PartialDate): number {
  return value.year * 10000 + (value.month ?? 1) * 100 + (value.day ?? 1);
}

function dateUpper(value: PartialDate): number {
  if (value.precision === "year") return value.year * 10000 + 1231;
  if (value.precision === "month") {
    const monthDays = [31, isLeap(value.year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return value.year * 10000 + (value.month ?? 1) * 100 + (monthDays[(value.month ?? 1) - 1] ?? 0);
  }
  return dateLower(value);
}

function periodOk(value: Period): boolean {
  return dateOk(value.start) && (value.end === null || (dateOk(value.end) && dateLower(value.start) <= dateUpper(value.end)));
}

function metricOk(value: { comparator: string; number: number; upperNumber: number | null }): boolean {
  return (value.comparator === "range") === (value.upperNumber !== null) &&
    (value.upperNumber === null || value.upperNumber >= value.number);
}

function semanticProject(p: Project): boolean {
  if (p.asOf !== null && !dateOk(p.asOf)) return false;
  const sourceIds = p.sources.map((s) => s.id);
  const factIds = p.facts.map((f) => f.id);
  const jobIds = p.employment.map((j) => j.id);
  const blockIds = p.views.map((b) => b.id);
  const operationIds = p.operations.map((o) => o.id);
  const subIds = p.employment.flatMap((j) => j.subprojects.map((s) => s.id));
  if (!unique(p.sources.map((s) => JSON.stringify([s.id, s.revision]))) || ![factIds, jobIds, blockIds, operationIds, subIds].every(unique)) return false;
  const sourceSet = new Set(sourceIds);
  const factSet = new Set(factIds);
  const jobSet = new Set(jobIds);
  const blockSet = new Set(blockIds);
  const operationSet = new Set(operationIds);
  const subSet = new Set(subIds);
  const factById = new Map(p.facts.map((fact) => [fact.id, fact]));
  const jobById = new Map(p.employment.map((job) => [job.id, job]));
  const unitOwners = new Map<string, string>();

  for (const source of p.sources) {
    if (!safePath(source.byteRef)) return false;
    const units = new Set(source.units.map((u) => u.id));
    if (!unique(source.units.map((u) => u.id)) || !unique(source.units.map((u) => String(u.order))) || !unique(source.overlays.map((o) => o.id))) return false;
    if (!refs(source.overlays.map((o) => o.unitId), units)) return false;
    if (source.units.some((u) => !refs(u.representedFactIds, factSet))) return false;
    for (const unit of source.units) {
      const owner = unitOwners.get(unit.id);
      if (owner !== undefined && owner !== source.id) return false;
      unitOwners.set(unit.id, source.id);
      for (const factId of unit.representedFactIds) {
        const fact = factById.get(factId);
        if (!fact || fact.origin !== "source" || !fact.evidence.some((evidence) =>
          evidence.sourceId === source.id && evidence.sourceRevision === source.revision &&
          evidence.unitId === unit.id && evidence.unitRevision === unit.revision)) return false;
      }
      const l = unit.location;
      if (l.kind === "table_cell") {
        if (l.row === null || l.column === null || l.row < 0 || l.column < 0) return false;
      } else if (l.row !== null || l.column !== null) return false;
    }
  }
  if (p.template !== null && p.template.assets.some((asset) => !safePath(asset.path))) return false;
  for (const fact of p.facts) {
    if ((fact.origin === "source") !== (fact.evidence.length > 0)) return false;
    if (fact.jobId !== null && !jobSet.has(fact.jobId)) return false;
    if (fact.jobId !== null && !jobById.get(fact.jobId)?.factIds.includes(fact.id)) return false;
    if (fact.subprojectId !== null) {
      if (!subSet.has(fact.subprojectId) || !p.employment.some((j) => j.id === fact.jobId && j.subprojects.some((s) => s.id === fact.subprojectId))) return false;
      if (!p.employment.some((j) => j.id === fact.jobId && j.subprojects.some((s) => s.id === fact.subprojectId && s.factIds.includes(fact.id)))) return false;
    }
    for (const evidence of fact.evidence) {
      if (!sourceSet.has(evidence.sourceId)) return false;
      const source = p.sources.find((s) => s.id === evidence.sourceId && s.revision === evidence.sourceRevision);
      const unit = source?.units.find((u) => u.id === evidence.unitId);
      if (!source || !unit || unit.revision !== evidence.unitRevision || !unit.representedFactIds.includes(fact.id)) return false;
    }
    if (fact.kind === "date" && !dateOk(fact.value)) return false;
    if (fact.kind === "metric" || fact.kind === "leadership") {
      const metric = fact.kind === "metric" ? fact.value : fact.value.teamSize;
      if (metric && !metricOk(metric)) return false;
    }
    if (fact.kind === "technology" && fact.value.scope === "global" && (fact.jobId !== null || fact.subprojectId !== null)) return false;
  }
  for (const job of p.employment) {
    if (!refs(job.factIds, factSet) || job.periods.some((period) => !periodOk(period))) return false;
    if (job.factIds.some((factId) => factById.get(factId)?.jobId !== job.id)) return false;
    for (const sub of job.subprojects) {
      if (!refs(sub.factIds, factSet) || (sub.period !== null && !periodOk(sub.period))) return false;
      if (sub.factIds.some((factId) => {
        const fact = factById.get(factId);
        return fact?.jobId !== job.id || fact.subprojectId !== sub.id;
      })) return false;
      if (sub.period !== null && job.periods.length > 0 && !job.periods.some((period) =>
        dateLower(period.start) <= dateLower(sub.period!.start) && (period.end === null || (sub.period!.end !== null && dateUpper(sub.period!.end) <= dateUpper(period.end))))) return false;
    }
  }
  for (const block of p.views) {
    if (block.previous !== null && block.revision < 2) return false;
    for (const state of block.previous === null ? [block.state] : [block.state, block.previous]) {
      if (!refs(state.factIds, factSet) || !unique(state.factIds) || !unique(Object.keys(state.factRevisions))) return false;
      if (state.factIds.length !== Object.keys(state.factRevisions).length || !state.factIds.every((id) => id in state.factRevisions)) return false;
      if (Object.entries(state.factRevisions).some(([factId, revision]) => revision > (factById.get(factId)?.revision ?? 0))) return false;
    }
  }
  for (const proposal of p.proposals) {
    if (!blockSet.has(proposal.blockId) || !operationSet.has(proposal.operationId) || !refs(proposal.evidenceFactIds, factSet)) return false;
    const block = p.views.find((b) => b.id === proposal.blockId);
    const operation = p.operations.find((o) => o.id === proposal.operationId);
    if (!block || !operation || !["profile", "job_prose"].includes(block.kind) || proposal.baseBlockRevision > block.revision || operation.kind !== proposal.kind) return false;
  }
  for (const decision of p.review.decisions) {
    const valid = decision.targetKind === "source_unit" ? new Set(p.sources.flatMap((s) => s.units.filter((u) => u.revision === decision.targetRevision).map((u) => u.id))) : decision.targetKind === "fact" ? factSet : blockSet;
    if (!valid.has(decision.targetId)) return false;
    if (decision.targetKind === "fact" && decision.targetRevision > (factById.get(decision.targetId)?.revision ?? 0)) return false;
    if (decision.targetKind === "block" && decision.targetRevision > (p.views.find((block) => block.id === decision.targetId)?.revision ?? 0)) return false;
  }
  for (const ack of p.review.acknowledgments) {
    const target = ack.targetKind === "fact" ? p.facts.find((f) => f.id === ack.targetId) : p.views.find((b) => b.id === ack.targetId);
    if (!target || ack.targetRevision !== target.revision) return false;
  }
  for (const render of p.renders) {
    if (render.projectRevision > p.revision) return false;
    if (p.template === null || render.templateId !== p.template.id || render.templateVersion !== p.template.version || !refs(render.blocks.map((b) => b.blockId), blockSet)) return false;
    if (render.blocks.some((b) => b.blockRevision > (p.views.find((view) => view.id === b.blockId)?.revision ?? 0))) return false;
    if ([render.docx, render.pdf].some((asset) => asset !== null && !safePath(asset.path))) return false;
  }
  const modelKinds = new Set(["normalize_semantics", "draft_prose", "rewrite_prose"]);
  for (const operation of p.operations) {
    if (operation.baseRevision > p.revision) return false;
    if (!modelKinds.has(operation.kind) && operation.usage !== null && operation.usage.logicalAttempts !== 0) return false;
    if (!unique(operation.events.map((event) => String(event.sequence))) || operation.events.some((event) => event.requestId !== operation.id)) return false;
  }
  return true;
}

function safeZip(data: unknown): boolean {
  if (!zipShape(data)) return false;
  const paths = data.entries.map((entry) => entry.path);
  const projectEntries = data.entries.filter((entry) => entry.role === "project");
  return unique(paths) && paths.every(safePath) && projectEntries.length === 1 && projectEntries[0]?.path === "project.json";
}

function safePrepare(data: unknown): boolean {
  if (!prepareShape(data) || !semanticProject(data.project)) return false;
  const project = data.project;
  const presentation = data.presentation;
  if (project.schemaVersion !== 3 || project.template?.id !== "generic" || project.template.version !== "1.0.0" ||
      project.template.packageSha256 !== "d081df948bfd55d107c38d40387a9758f563f9c14a9cffc4a847f44cb687b8b9") return false;
  const jobs = project.employment.map((job) => job.id);
  const bindings = presentation.jobProseBlocks;
  const bound = Object.values(bindings);
  if (!unique(bound) || !unique(jobs) || jobs.length !== Object.keys(bindings).length ||
      !jobs.every((id) => Object.hasOwn(bindings, id))) return false;
  const blocks = new Map(project.views.map((block) => [block.id, block]));
  if (project.views.filter((block) => block.kind === "profile").length !== 1) return false;
  if (bound.some((id) => blocks.get(id)?.kind !== "job_prose")) return false;
  return !project.views.some((block) => block.kind === "job_prose" && block.visible && !bound.includes(block.id));
}

export function validateContract(kind: string, data: unknown): boolean {
  if (!finiteJson(data)) return false;
  switch (kind) {
    case "project": return projectShape(data) && semanticProject(data);
    case "proposal": return proposalShape(data);
    case "template": return templateShape(data) && data.assets.every((asset) => safePath(asset.path));
    case "zip_manifest": return safeZip(data);
    case "prepare_request": return safePrepare(data);
    default: return false;
  }
}
