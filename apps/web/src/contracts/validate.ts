import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import projectSchema from "../../../../contracts/json-schema/project.schema.json" with { type: "json" };
import proposalSchema from "../../../../contracts/json-schema/proposal.schema.json" with { type: "json" };
import templateSchema from "../../../../contracts/json-schema/template.schema.json" with { type: "json" };
import zipSchema from "../../../../contracts/json-schema/zip_manifest.schema.json" with { type: "json" };
import type { Project, PartialDate, Period } from "./generated/project.js";
import type { ZipManifest } from "./generated/zip_manifest.js";
import type { TemplateManifest } from "./generated/template.js";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const projectShape = ajv.compile<Project>(projectSchema);
const proposalShape = ajv.compile(proposalSchema);
const templateShape = ajv.compile<TemplateManifest>(templateSchema);
const zipShape = ajv.compile<ZipManifest>(zipSchema);

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
      if (metric && ((metric.comparator === "range") !== (metric.upperNumber !== null) || (metric.upperNumber !== null && metric.upperNumber < metric.number))) return false;
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

export function validateContract(kind: string, data: unknown): boolean {
  if (!finiteJson(data)) return false;
  switch (kind) {
    case "project": return projectShape(data) && semanticProject(data);
    case "proposal": return proposalShape(data);
    case "template": return templateShape(data) && data.assets.every((asset) => safePath(asset.path));
    case "zip_manifest": return safeZip(data);
    default: return false;
  }
}
