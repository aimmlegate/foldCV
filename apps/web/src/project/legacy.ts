import type { Project, Block, TextFact, SourceUnit, Job } from "../contracts/generated/project";
import type { Presentation } from "../contracts/generated/prepare_request";
import { validateContract } from "../contracts/validate";
import { parseDate } from "../facts/working";

const emptyHash = "0".repeat(64);
const templateHash = "d081df948bfd55d107c38d40387a9758f563f9c14a9cffc4a847f44cb687b8b9";
type Statement = { text: string; sources: string[] };
type OldJob = { id: string; company: Statement; role: Statement; start: string; end: string | null };
type OldView = { schema_version: 2; template: "generic-v1"; candidate: { name: Statement; title: Statement; summary: Statement };
  projects: { id: string; company?: Statement; period?: Statement; role?: Statement;
    stack?: Statement | null; description: Statement | null; tasks: Statement[]; results: Statement[] }[];
  earlier_experience: { job_ids: string[]; summary: Statement }[];
  focus: { label: Statement; duration?: Statement | null }[]; sidebar: { title: string; items: Statement[] }[];
  skill_groups: { title: string; items: Statement }[];
  achievements?: Statement[];
  coverage: Record<string, { decision: string; reason?: string }> };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function statement(value: unknown, units: Set<string>): value is Statement {
  return object(value) && typeof value.text === "string" && value.text.trim().length > 0 &&
    Array.isArray(value.sources) && value.sources.length > 0 && value.sources.every((id: unknown) =>
      typeof id === "string" && units.has(id));
}
function oldJob(value: unknown, units: Set<string>): value is OldJob {
  return object(value) && typeof value.id === "string" && value.id.length > 0 &&
    statement(value.company, units) && statement(value.role, units) && typeof value.start === "string" &&
    (value.end === null || typeof value.end === "string");
}
function oldView(value: unknown, units: Set<string>, jobIds: Set<string>): value is OldView {
  if (!object(value) || value.schema_version !== 2 || value.template !== "generic-v1" ||
      !object(value.candidate) || !statement(value.candidate.name, units) ||
      !statement(value.candidate.title, units) || !statement(value.candidate.summary, units) ||
      !Array.isArray(value.projects) || !Array.isArray(value.earlier_experience) ||
      !Array.isArray(value.focus) || !Array.isArray(value.sidebar) || !Array.isArray(value.skill_groups) ||
      !object(value.coverage)) return false;
  const projects = value.projects.every((item: unknown) => object(item) && typeof item.id === "string" &&
    jobIds.has(item.id) && (item.description === null || statement(item.description, units)) &&
    (item.company === undefined || statement(item.company, units)) &&
    (item.period === undefined || statement(item.period, units)) &&
    (item.role === undefined || statement(item.role, units)) &&
    (item.stack === undefined || item.stack === null || statement(item.stack, units)) &&
    Array.isArray(item.tasks) && item.tasks.every((entry: unknown) => statement(entry, units)) &&
    Array.isArray(item.results) && item.results.every((entry: unknown) => statement(entry, units)));
  const early = value.earlier_experience.every((item: unknown) => object(item) &&
    Array.isArray(item.job_ids) && item.job_ids.every((id: unknown) => typeof id === "string" && jobIds.has(id)) &&
    statement(item.summary, units));
  const projectsList = value.projects as OldView["projects"];
  const earlierList = value.earlier_experience as OldView["earlier_experience"];
  return projects && early && value.focus.every((item: unknown) => object(item) && statement(item.label, units) &&
      (item.duration === undefined || item.duration === null || statement(item.duration, units))) &&
    value.sidebar.every((item: unknown) => object(item) && typeof item.title === "string" &&
      Array.isArray(item.items) && item.items.every((entry: unknown) => statement(entry, units))) &&
    value.skill_groups.every((item: unknown) => object(item) && typeof item.title === "string" &&
      statement(item.items, units)) && Object.keys(value.coverage).length === units.size &&
    Object.entries(value.coverage).every(([id, decision]) => units.has(id) && object(decision) &&
      ["shown", "condensed", "archive_only", "duplicate", "metadata"].includes(String(decision.decision)) &&
      (decision.reason === undefined || typeof decision.reason === "string")) &&
    (value.achievements === undefined || Array.isArray(value.achievements) &&
      value.achievements.every((item: unknown) => statement(item, units))) &&
    [...jobIds].every((id) => projectsList.filter((item) => item.id === id).length +
      earlierList.reduce((count, item) => count + item.job_ids.filter((jobId) => jobId === id).length, 0) === 1);
}

export function migrateSelectedView(archive: Record<string, unknown>, rawView: unknown,
                                    originalSha256: string, originalName: string):
  { project: Project; presentation: Presentation } {
  const rawUnits = archive.units;
  const rawJobs = archive.jobs;
  if (!Array.isArray(rawUnits) || !Array.isArray(rawJobs)) throw new Error("Invalid version 2 records.");
  const unitIds = new Set<string>();
  for (const unit of rawUnits) {
    if (!object(unit) || typeof unit.id !== "string" || typeof unit.text !== "string" ||
        !Number.isInteger(unit.page) || unitIds.has(unit.id)) throw new Error("Invalid version 2 source units.");
    unitIds.add(unit.id);
  }
  if (!rawJobs.every((job: unknown) => oldJob(job, unitIds))) throw new Error("Unsupported version 2 employment view.");
  const jobs = rawJobs as OldJob[];
  const jobIds = new Set(jobs.map((job) => job.id));
  if (jobIds.size !== jobs.length || !oldView(rawView, unitIds, jobIds))
    throw new Error("Unsupported version 2 selected view.");
  const view = rawView;
  const sourceId = `source_${originalSha256.slice(0, 24)}`;
  const factId = (id: string) => `legacy_fact_${id}`;
  const unitId = (id: string) => `legacy_unit_${id}`;
  const classifications = object(archive.classifications) ? archive.classifications : {};
  if (Object.keys(classifications).length !== unitIds.size)
    throw new Error("Version 2 selected view has incomplete unit decisions.");
  const facts: TextFact[] = rawUnits.map((raw) => {
    if (!object(raw)) throw new Error("Invalid version 2 unit.");
    const id = String(raw.id);
    const classification = classifications[id];
    const jobId = object(classification) && typeof classification.job_id === "string" && jobIds.has(classification.job_id) ?
      classification.job_id : null;
    return { id: factId(id), revision: 1, kind: "text", value: { text: String(raw.text) },
      evidence: [{ sourceId, sourceRevision: 1, unitId: unitId(id), unitRevision: 1 }],
      origin: "source", importance: object(classification) && classification.importance === "essential" ? "essential" :
        object(classification) && classification.importance === "administrative" ? "minor" : "normal",
      jobId, subprojectId: null };
  });
  const units: SourceUnit[] = rawUnits.map((raw, index) => {
    if (!object(raw)) throw new Error("Invalid version 2 unit.");
    return { id: unitId(String(raw.id)), revision: 1, order: index, text: String(raw.text),
      location: { kind: "page", index: Number(raw.page), row: null, column: null },
      disposition: "unresolved", representedFactIds: [factId(String(raw.id))] };
  });
  const employment: Job[] = jobs.map((job) => {
    const start = parseDate(job.start);
    const end = job.end === null ? null : parseDate(job.end);
    if (!start) throw new Error("Version 2 job date is missing.");
    const selected = view.projects.find((item) => item.id === job.id);
    return { id: job.id, employer: selected?.company?.text ?? job.company.text,
      role: selected?.role?.text ?? job.role.text, periods: [{ start, end }],
      subprojects: [], factIds: facts.filter((fact) => fact.jobId === job.id).map((fact) => fact.id) };
  });
  function block(id: string, kind: Block["kind"], text: string, sources: string[]): Block {
    const factIds = [...new Set(sources)].map(factId);
    return { id, kind, revision: 1, status: "ready", visible: true, dependencyHash: emptyHash,
      contentPolicyVersion: "generic-1", previous: null,
      state: { text, origin: "source", locked: false, factIds,
        factRevisions: Object.fromEntries(factIds.map((factId) => [factId, 1])) } };
  }
  const achievements = view.achievements ?? [];
  const views: Block[] = [block("profile", "profile",
    [view.candidate.summary.text, ...achievements.map((item) => item.text)].join("\n"),
    [...view.candidate.summary.sources, ...achievements.flatMap((item) => item.sources)])];
  const bindings: Record<string, string> = {};
  for (const job of jobs) {
    const selected = view.projects.find((item) => item.id === job.id);
    const early = view.earlier_experience.find((item) => item.job_ids.includes(job.id));
    const statements = selected ? [selected.period, selected.stack, selected.description,
      ...selected.tasks, ...selected.results].filter(
      (item): item is Statement => item !== null && item !== undefined) : early ? [early.summary] : [];
    const id = `legacy_prose_${job.id}`;
    views.push(block(id, "job_prose", statements.map((item) => item.text).join("\n") || `${job.company.text} · ${job.role.text}`,
      statements.flatMap((item) => item.sources)));
    bindings[job.id] = id;
  }
  const side: { text: string; sources: string[] }[] = [
    ...view.focus.map((item) => ({ text: [item.label.text, item.duration?.text].filter(Boolean).join(" · "),
      sources: [...item.label.sources, ...(item.duration?.sources ?? [])] })),
    ...view.sidebar.flatMap((item) => item.items.map((entry) => ({ text: `${item.title}: ${entry.text}`,
      sources: entry.sources }))),
    ...view.skill_groups.map((item) => ({ text: `${item.title}: ${item.items.text}`, sources: item.items.sources })),
    ...view.earlier_experience.map((item) => ({ text: item.summary.text, sources: item.summary.sources })),
  ];
  views.push(block("education", "education", side.map((item) => item.text).join("\n"),
    side.flatMap((item) => item.sources)));
  const asOf = parseDate(String(archive.as_of));
  const project: Project = { schemaVersion: 3, projectId: `legacy_${crypto.randomUUID()}`, revision: 1,
    asOf, createdAt: new Date().toISOString(), sources: [{ id: sourceId, revision: 1,
      originalName, mimeType: originalName.toLowerCase().endsWith(".pdf") ? "application/pdf" :
        originalName.toLowerCase().endsWith(".docx") ?
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "text/plain",
      byteSha256: originalSha256, byteRef: "legacy/v2/original", parser: "legacy-v2", parserVersion: "2",
      units, overlays: [], warnings: [] }], facts, employment, views,
    template: { id: "generic", version: "1.0.0", packageSha256: templateHash,
      contentPolicyVersion: "generic-1", assets: [] },
    review: { decisions: [], acknowledgments: [] }, operations: [], proposals: [], renders: [] };
  if (!validateContract("project", project)) throw new Error("Version 2 view cannot be migrated safely.");
  const presentation: Presentation = { name: view.candidate.name.text, title: view.candidate.title.text,
    sourceLanguage: "mixed", jobProseBlocks: bindings };
  return { project, presentation };
}
