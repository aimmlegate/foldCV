import type { FactSheet } from "../contracts/generated/fact_sheet";
import type { Facts, Project, PartialDate } from "../contracts/generated/project";
import type { Presentation } from "../contracts/generated/prepare_request";
import type { RewriteIssue } from "../contracts/generated/rewrite_result";
import { adaptWorking } from "../facts/working";
import type { WorkingDraft, WorkingSource } from "../facts/working";
import { validateContract, validateFactSheet } from "../contracts/validate";

type Fact = Facts[number];
export type CoverageDecision = NonNullable<WorkingDraft["coverage"]>["decisions"][number];
export type CoverageAcknowledgment = NonNullable<WorkingDraft["coverage"]>["acknowledgments"][number];
export type CoverageTarget = { kind: "unit" | "fact"; id: string; disposition: CoverageDecision["disposition"];
  dependency: string; reason: string | null; sourceId?: string; unitId?: string; blockId?: string;
  fact?: Fact; confirmable?: boolean };
export type CoverageIssue = { id: string; code: string; group: "fix" | "decide" | "check";
  severity: "blocker" | "warning"; message: string; action: string; dependency: string;
  sourceId?: string; unitId?: string; factId?: string; blockId?: string; jobId?: string;
  acknowledged: boolean };
export type CoverageReadiness = { kind: "document_readiness"; status: "ready" | "blocked";
  blockers: CoverageIssue[]; warnings: CoverageIssue[]; units: CoverageTarget[]; facts: CoverageTarget[];
  projectSaveAllowed: true };
export type CoverageInput = { project: Project; working: WorkingDraft | null; presentation: Presentation | null;
  rewriteIssues?: Record<string, RewriteIssue[]>; sourceIntegrity?: SourceIntegrity | null;
  standaloneAcknowledgments?: CoverageAcknowledgment[]; standaloneDecisions?: CoverageDecision[] };

export type SourceIntegrity = { valid: boolean; matches: (sources: WorkingSource[]) => boolean };

const policy = "coverage-1";
const key = (sourceId: string, unitId: string): string => `${sourceId}\u0000${unitId}`;
const unitId = (sourceId: string, id: string): string => `view_${sourceId}_${id}`;

function oldEnd(end: PartialDate | null, asOf: PartialDate | null): boolean {
  if (!end || !asOf || asOf.year <= 15) return false;
  const month = asOf.month ?? 1;
  const day = asOf.day ?? 1;
  const cutoff = Date.UTC(asOf.year - 15, month - 1,
    Math.min(day, new Date(Date.UTC(asOf.year - 15, month, 0)).getUTCDate()));
  const upper = Date.UTC(end.year, (end.month ?? 12) - 1,
    end.day ?? new Date(Date.UTC(end.year, end.month ?? 12, 0)).getUTCDate());
  return upper < cutoff;
}

function oldJob(project: Project, jobId: string): boolean {
  const job = project.employment.find((item) => item.id === jobId);
  return Boolean(job?.periods.length && job.periods.every((period) => oldEnd(period.end, project.asOf)));
}

function jobBlock(input: CoverageInput, jobId: string): Project["views"][number] | undefined {
  const id = input.presentation?.jobProseBlocks[jobId];
  return input.project.views.find((item) => item.id === id);
}

function factBlock(input: CoverageInput, fact: Fact): Project["views"][number] | undefined {
  if (fact.jobId) return jobBlock(input, fact.jobId);
  return input.project.views.find((item) => item.kind === "profile" && item.state.factIds.includes(fact.id));
}

function acceptedBlock(input: CoverageInput, block: Project["views"][number]): boolean {
  const reviewed = block.status !== "proposed" || input.project.review.decisions.some((decision) =>
    decision.targetKind === "block" && decision.targetId === block.id &&
    decision.targetRevision === block.revision && decision.disposition === "shown");
  return block.visible && block.status !== "stale" && reviewed;
}

function eligibleTextBlocks(input: CoverageInput, fact: Fact): Project["views"] {
  const profile = input.project.views.find((block) => block.kind === "profile" &&
    block.state.factIds.includes(fact.id));
  const prose = fact.jobId && !oldJob(input.project, fact.jobId) ? jobBlock(input, fact.jobId) : undefined;
  return [profile, prose].filter((block): block is Project["views"][number] =>
    Boolean(block && (block.kind === "profile" || block.kind === "job_prose") &&
      block.state.factIds.includes(fact.id) && acceptedBlock(input, block)));
}

function linkedBlock(input: CoverageInput, fact: Fact): Project["views"][number] | undefined {
  const block = factBlock(input, fact);
  return block && acceptedBlock(input, block) && block.state.factIds.includes(fact.id) ? block : undefined;
}

function textReviewBlock(input: CoverageInput, fact: Fact): Project["views"][number] | undefined {
  const blocks = eligibleTextBlocks(input, fact);
  return blocks.find((block) => textContains(block.state.text, fact.kind === "text" ? fact.value.text : null)) ??
    blocks.find((block) => block.kind === "profile" && block.status === "ready") ??
    blocks.find((block) => block.status === "ready") ?? blocks[0];
}

function confirmableText(input: CoverageInput, fact: Fact): boolean {
  if (fact.kind !== "text" || !input.project.facts.some((item) => item.id === fact.id)) return false;
  return eligibleTextBlocks(input, fact).some((block) => block.status === "ready");
}

function identityField(input: CoverageInput, fact: Fact): "name" | "title" | null {
  if (fact.kind !== "text" || fact.jobId !== null || !input.presentation) return null;
  const value = fact.value.text.trim();
  if (!value) return null;
  if (value === input.presentation.name.trim()) return "name";
  if (value === input.presentation.title.trim()) return "title";
  return null;
}

function identityRepresented(input: CoverageInput, fact: Fact): boolean {
  return identityField(input, fact) !== null;
}

function factDisposition(input: CoverageInput, fact: Fact): CoverageTarget["disposition"] {
  if (fact.kind === "technology") {
    const skills = input.project.views.find((block) => block.kind === "skills");
    const rendered = skills?.visible !== false && fact.value.display.trim() &&
      input.project.facts.some((item) => item.id === fact.id && item.kind === "technology" &&
        item.value.display === fact.value.display);
    return rendered ? "shown" : "unresolved";
  }
  if (fact.kind === "text") return identityRepresented(input, fact) || eligibleTextBlocks(input, fact).some((block) =>
    textContains(block.state.text, fact.value.text)) ? "shown" : "unresolved";
  if (fact.jobId && oldJob(input.project, fact.jobId)) return "unresolved";
  const block = linkedBlock(input, fact);
  if (!block) return "unresolved";
  return "shown";
}

function factDependency(input: CoverageInput, fact: Fact): string {
  const linked = factBlock(input, fact);
  const block = fact.kind === "text" && (fact.jobId && oldJob(input.project, fact.jobId) ||
    !linked?.state.factIds.includes(fact.id)) ? undefined : linked;
  const profile = fact.kind === "text" ? input.project.views.find((item) =>
    item.kind === "profile" && item.state.factIds.includes(fact.id)) : undefined;
  const skills = fact.kind === "technology" ? input.project.views.find((item) => item.kind === "skills") : undefined;
  const job = input.project.employment.find((item) => item.id === fact.jobId);
  const early = fact.jobId && oldJob(input.project, fact.jobId) ?
    input.project.views.find((item) => item.kind === "early_career") : undefined;
  const identity = identityField(input, fact);
  return JSON.stringify([policy, fact, input.project.facts.some((item) => item.id === fact.id),
    skills && [skills.id, skills.revision, skills.visible],
    block && [block.id, block.revision, block.visible, block.status,
    block.state.text, block.state.factIds, block.contentPolicyVersion], job,
  profile && profile.id !== block?.id && [profile.id, profile.revision, profile.visible,
    profile.status, profile.state.text, profile.state.factIds, profile.contentPolicyVersion],
  early && [early.id, early.revision, early.visible], fact.jobId ? input.project.asOf : null,
  fact.kind === "text" && fact.jobId === null ?
    identity === "name" ? ["name", input.presentation?.name] :
    identity === "title" ? ["title", input.presentation?.title] :
    [input.presentation?.name, input.presentation?.title] : null]);
}

function reviewableFacts(input: CoverageInput): Fact[] {
  const replacements = new Set(Object.keys(input.working?.sheet.userCorrections ?? {}));
  const retained = new Map<string, Fact>();
  if (input.working) {
    try {
      for (const fact of adaptWorking(input.working).project.facts) retained.set(fact.id, fact);
    } catch {
      for (const fact of input.working.sheet.facts) if (!replacements.has(fact.id)) retained.set(fact.id, fact);
    }
  }
  for (const fact of input.project.facts) if (!replacements.has(fact.id)) retained.set(fact.id, fact);
  return [...retained.values()];
}

function sourceFactIds(sheet: FactSheet, sourceId: string, sourceUnitId: string): string[] {
  const account = sheet.units.find((item) => item.sourceId === sourceId && item.unitId === sourceUnitId);
  return account?.factIds ?? sheet.facts.filter((fact) => fact.evidence.some((evidence) =>
    evidence.sourceId === sourceId && evidence.unitId === sourceUnitId)).map((fact) => fact.id);
}

function sourceLinkForFact(input: CoverageInput, fact: Fact): { sourceId: string; unitId: string } | null {
  const direct = fact.evidence[0];
  if (direct) return { sourceId: direct.sourceId,
    unitId: direct.unitId.replace(`view_${direct.sourceId}_`, "") };
  const originalId = Object.entries(input.working?.sheet.userCorrections ?? {})
    .find(([, replacement]) => replacement === fact.id)?.[0];
  const original = input.working?.sheet.facts.find((item) => item.id === originalId);
  const evidence = original?.evidence[0];
  return evidence ? { sourceId: evidence.sourceId, unitId: evidence.unitId } : null;
}

function unitDependency(input: CoverageInput, sourceId: string, sourceUnitId: string,
                        retainedFacts = reviewableFacts(input)): string {
  const source = input.working?.sources.find((item) => item.entry.result.sourceId === sourceId);
  const unit = source?.entry.result.units.find((item) => item.id === sourceUnitId);
  const overlay = source?.entry.overlays[`unit:${sourceUnitId}`];
  const sheet = input.working?.sheet;
  const account = sheet?.units.find((item) => item.sourceId === sourceId && item.unitId === sourceUnitId);
  const linked = sheet ? sourceFactIds(sheet, sourceId, sourceUnitId).map((id) => {
    const replacement = sheet.userCorrections?.[id] ?? id;
    const effective = retainedFacts.find((item) => item.id === replacement);
    return [id, replacement, effective && factDependency(input, effective)];
  }) : [];
  return JSON.stringify([policy, source?.entry.result.byteSha256, unit, overlay, account, linked]);
}

function jobDependency(input: CoverageInput, jobId: string): string | null {
  const job = input.project.employment.find((item) => item.id === jobId);
  const retained = input.working?.sheet.employment?.find((item) => item.id === jobId) ??
    input.working?.manual.employment.find((item) => item.id === jobId);
  if (!job && !retained) return null;
  const prose = jobBlock(input, jobId);
  const early = input.project.views.find((block) => block.kind === "early_career");
  return JSON.stringify([policy, job, retained, prose && [prose.id, prose.revision, prose.visible],
    early && [early.id, early.revision, early.visible], input.project.asOf]);
}

function activeDecision(input: CoverageInput, kind: CoverageDecision["targetKind"], id: string,
                        dependency: string): CoverageDecision | undefined {
  return (input.working?.coverage?.decisions ?? input.standaloneDecisions)?.find((item) => item.targetKind === kind &&
    item.targetId === id && item.dependency === dependency);
}

function issue(input: CoverageInput, code: string, group: CoverageIssue["group"],
               severity: CoverageIssue["severity"], target: string, dependency: string,
               message: string, action: string, links: Pick<CoverageIssue,
               "sourceId" | "unitId" | "factId" | "blockId" | "jobId"> = {}): CoverageIssue {
  const id = `${code}:${target}`;
  return { id, code, group, severity, message, action, dependency, ...links,
    acknowledged: Boolean((input.working?.coverage?.acknowledgments ?? input.standaloneAcknowledgments)?.some((item) =>
      item.issueId === id && item.dependency === dependency)) };
}

function visibleFactIssue(input: CoverageInput, fact: Fact, blockId: string | undefined,
                          code: string, message: string): CoverageIssue {
  return issue(input, code, "check", "warning", fact.id, factDependency(input, fact), message,
    "Сверьте формулировку с фактом и исходником; затем подтвердите предупреждение.",
    { factId: fact.id, ...(blockId ? { blockId } : {}), ...(sourceLinkForFact(input, fact) ?? {}) });
}

function textContains(text: string, value: string | null): boolean {
  return value === null || !value.trim() || text.toLocaleLowerCase().includes(value.toLocaleLowerCase());
}

function containsNumber(text: string, number: number): boolean {
  const token = String(number).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![\\p{N}.,])${token}(?![\\p{N}.,])`, "u").test(text);
}

export async function verifyWorkingSources(sources: WorkingSource[]): Promise<SourceIntegrity> {
  const snapshots = sources.map((source) => ({ sourceId: source.entry.result.sourceId,
    expected: source.entry.result.byteSha256, bytes: Uint8Array.from(source.originalBytes) }));
  let valid = true;
  try {
    const digests = await Promise.all(snapshots.map(async ({ bytes }) => {
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest), (part) => part.toString(16).padStart(2, "0")).join("");
    }));
    valid = snapshots.every((source, index) => source.expected === digests[index]);
  } catch { valid = false; }
  return { valid, matches: (current) => current.length === snapshots.length && current.every((source, index) => {
    const snapshot = snapshots[index];
    return snapshot?.sourceId === source.entry.result.sourceId &&
      snapshot.expected === source.entry.result.byteSha256 &&
      snapshot.bytes.length === source.originalBytes.length &&
      sameBytes(snapshot.bytes, source.originalBytes);
  }) };
}

function sameBytes(expected: Uint8Array, current: Uint8Array): boolean {
  if (expected.length !== current.length) return false;
  const left = new DataView(expected.buffer, expected.byteOffset, expected.byteLength);
  const right = new DataView(current.buffer, current.byteOffset, current.byteLength);
  const whole = expected.length - expected.length % 8;
  for (let offset = 0; offset < whole; offset += 8) {
    if (left.getBigUint64(offset) !== right.getBigUint64(offset)) return false;
  }
  for (let offset = whole; offset < expected.length; offset += 1) {
    if (expected[offset] !== current[offset]) return false;
  }
  return true;
}

export function coverageReview(input: CoverageInput): CoverageReadiness {
  const { project, working } = input;
  const issues: CoverageIssue[] = [];
  const facts: CoverageTarget[] = [];
  const units: CoverageTarget[] = [];
  const allFacts = reviewableFacts(input);
  const validProject = validateContract("project", project);
  if (!validProject || working && (!validateFactSheet(working.sheet) ||
      working.sources.some((source) => source.originalBytes.length !== source.entry.result.byteLength) ||
      input.sourceIntegrity && (!input.sourceIntegrity.valid || !input.sourceIntegrity.matches(working.sources)))) {
    issues.push(issue(input, "CORRUPT_DATA", "fix", "blocker", project.projectId,
      JSON.stringify([policy, project.revision]), "Данные проекта повреждены или содержат неверные связи.",
      "Исправьте данные проекта перед экспортом."));
  }
  if (working && !input.sourceIntegrity) issues.push(issue(input, "SOURCE_INTEGRITY_PENDING", "fix", "blocker",
    project.projectId, JSON.stringify([policy, working.sources.map((source) => source.entry.result.byteSha256)]),
    "Проверка исходных байтов ещё не завершена.", "Дождитесь проверки оригинального источника."));
  if (!input.presentation?.name.trim() || !input.presentation.title.trim()) {
    issues.push(issue(input, "REQUIRED_FIELD", "fix", "blocker", "identity",
      JSON.stringify([policy, input.presentation?.name, input.presentation?.title]),
      "Не заполнены обязательные данные кандидата.", "Укажите имя и должность."));
  }
  const retainedJobs = [...(working?.sheet.employment ?? []), ...(working?.manual.employment ?? [])];
  for (const retained of retainedJobs) {
    if (project.employment.some((job) => job.id === retained.id)) continue;
    const dependency = jobDependency(input, retained.id);
    const decision = dependency ? activeDecision(input, "job", retained.id, dependency) : undefined;
    if (!dependency || decision?.disposition === "excluded" && decision.reason?.trim()) continue;
    issues.push(issue(input, "MISSING_JOB", "fix", "blocker", retained.id, dependency,
      `Работа ${retained.employer} отсутствует в документе.`, "Восстановите запись работы или объясните исключение.",
      { jobId: retained.id }));
  }
  for (const job of project.employment) {
    const prose = jobBlock(input, job.id);
    const old = oldJob(project, job.id);
    const early = project.views.find((block) => block.kind === "early_career");
    const missing = old ? early?.visible === false : !prose || !prose.visible;
    const dependency = jobDependency(input, job.id)!;
    const excluded = activeDecision(input, "job", job.id, dependency);
    if (missing && !(excluded?.disposition === "excluded" && excluded.reason?.trim())) {
      issues.push(issue(input, "MISSING_JOB", "fix", "blocker", job.id,
        dependency,
        `Работа ${job.employer} отсутствует в документе.`, "Покажите работу или ранний опыт.",
        { jobId: job.id, ...(prose ? { blockId: prose.id } : {}) }));
    }
    if (!job.employer.trim() || !job.role.trim() || !prose ||
        !old && prose.visible && !prose.state.text.trim()) {
      issues.push(issue(input, "REQUIRED_JOB_FIELD", "fix", "blocker", job.id,
        JSON.stringify([policy, job, prose && [prose.id, prose.revision, prose.state.text]]),
        "У работы не заполнено обязательное поле.", "Заполните организацию, роль и видимый текст работы.",
        { jobId: job.id, ...(prose ? { blockId: prose.id } : {}) }));
    }
  }
  if (input.presentation && validProject && !validateContract("prepare_request",
      { project, presentation: input.presentation })) {
    issues.push(issue(input, "BROKEN_JOB_BINDING", "fix", "blocker", "jobs",
      JSON.stringify([policy, input.presentation, project.employment.map((job) => job.id)]),
      "Связи работ или обязательные данные документа некорректны.", "Проверьте поля кандидата и связи работ с текстовыми блоками."));
  }
  const effective = new Set(allFacts.map((fact) => fact.id));
  for (const fact of allFacts) {
    const dependency = factDependency(input, fact);
    const saved = activeDecision(input, "fact", fact.id, dependency);
    const derived = factDisposition(input, fact);
    const disposition = saved?.disposition ?? derived;
    const block = fact.kind === "text" ? textReviewBlock(input, fact) : factBlock(input, fact);
    const confirmable = confirmableText(input, fact) && derived === "unresolved";
    const sourceLink = sourceLinkForFact(input, fact);
    facts.push({ kind: "fact", id: fact.id, fact, disposition, dependency,
      reason: saved?.reason ?? null, confirmable, ...(block ? { blockId: block.id } : {}),
      ...(sourceLink ?? {}) });
    if (disposition === "unresolved" && fact.importance === "essential" ||
        fact.importance === "essential" && disposition === "excluded" && !saved?.reason?.trim()) {
      issues.push(issue(input, "MISSING_ESSENTIAL", "decide", "blocker", fact.id, dependency,
        "Важный факт не представлен и не имеет решения.", "Покажите факт или укажите причину исключения.",
        { factId: fact.id, ...(block ? { blockId: block.id } : {}), ...(sourceLink ?? {}) }));
    } else if (disposition === "unresolved" && !saved && fact.importance !== "minor") {
      issues.push(issue(input, "OMITTED_FACT", "decide", "warning", fact.id, dependency,
        "Факт остался только в данных проекта.", "Покажите факт, сократите или объясните исключение.",
        { factId: fact.id, ...(block ? { blockId: block.id } : {}), ...(sourceLink ?? {}) }));
    }
    if (disposition === "shown" && identityRepresented(input, fact) && !block) {
      issues.push(visibleFactIssue(input, fact, undefined, "TEXT_MEANING",
        "Проверьте, что имя или должность сохраняет смысл факта из исходника."));
      continue;
    }
    if (disposition !== "shown" || !block?.visible || block.status === "stale") continue;
    const text = block.state.text;
    if (fact.kind === "text") issues.push(visibleFactIssue(input, fact, block.id, "TEXT_MEANING",
      "Проверьте, что изложение сохраняет смысл факта и не добавляет утверждений."));
    if (fact.kind === "metric") {
      const value = fact.value;
      const required = [value.unit, value.period, value.baseline, value.result, value.scope,
        ...value.qualifiers].filter((part): part is string => Boolean(part));
      if (!containsNumber(text, value.number) || required.some((part) => !textContains(text, part)) ||
          value.comparator !== "exact" || value.upperNumber !== null) {
        issues.push(visibleFactIssue(input, fact, block.id, "METRIC_MEANING",
          "Проверьте число, диапазон, предел, единицу и контекст метрики."));
      }
      if (value.attribution !== "personal") issues.push(visibleFactIssue(input, fact, block.id,
        "ATTRIBUTION", "Проверьте, чей вклад описывает метрика."));
    }
    if (fact.kind === "leadership") {
      issues.push(visibleFactIssue(input, fact, block.id, "LEADERSHIP_SCOPE",
        "Проверьте действие, состав команды и личный вклад."));
    }
  }
  if (working) {
    for (const source of working.sources) for (const unit of source.entry.result.units) {
      const sourceId = source.entry.result.sourceId;
      const id = unitId(sourceId, unit.id);
      const dependency = unitDependency(input, sourceId, unit.id, allFacts);
      const account = working.sheet.units.find((item) => item.sourceId === sourceId && item.unitId === unit.id);
      const corrected = sourceFactIds(working.sheet, sourceId, unit.id).some((factId) =>
        Boolean(working.sheet.userCorrections?.[factId]));
      const linked = sourceFactIds(working.sheet, sourceId, unit.id)
        .map((factId) => working.sheet.userCorrections?.[factId] ?? factId)
        .filter((factId) => effective.has(factId));
      const dispositions = linked.map((factId) => facts.find((item) => item.id === factId)?.disposition);
      const oldEmployment = working.sheet.employment?.some((job) => job.sourceId === sourceId &&
        job.unitIds.includes(unit.id) && oldJob(project, job.id)) ?? false;
      const early = project.views.find((block) => block.kind === "early_career");
      const derived = account?.disposition === "duplicate" ? "duplicate" :
        account?.disposition === "administrative" ? "archived" :
          account?.disposition === "unresolved" || corrected ? "unresolved" :
            linked.length && dispositions.every((item) => item === "shown") ? "shown" :
              linked.length && dispositions.every((item) => item === "shown" || item === "condensed") ? "condensed" :
                !linked.length && oldEmployment && early?.visible !== false ? "condensed" : "unresolved";
      const saved = activeDecision(input, "unit", id, dependency);
      const disposition = saved?.disposition ?? derived;
      units.push({ kind: "unit", id, disposition, dependency, reason: saved?.reason ?? null,
        sourceId, unitId: unit.id });
      if (!saved && disposition === "unresolved" && unit.text.trim()) {
        issues.push(issue(input, "UNRESOLVED_UNIT", "decide", "warning", id, dependency,
          "Фрагмент исходника не связан с принятым фактом.", "Свяжите факт или укажите причину сохранения только в проекте.",
          { sourceId, unitId: unit.id }));
      }
    }
    for (const sourceIssue of working.sheet.issues) {
      const dependency = JSON.stringify([unitDependency(input, sourceIssue.sourceId, sourceIssue.unitId ?? "", allFacts), sourceIssue]);
      issues.push(issue(input, sourceIssue.code, "check", "warning", sourceIssue.id, dependency,
        "Связь или смысл исходного фрагмента требуют проверки.", "Сверьте исходник и подтвердите предупреждение.",
        { sourceId: sourceIssue.sourceId, ...(sourceIssue.unitId ? { unitId: sourceIssue.unitId } : {}) }));
    }
    for (const draftIssue of working.draft?.issues ?? []) {
      const fact = project.facts.find((item) => item.id === draftIssue.factId);
      const block = project.views.find((item) => item.id === draftIssue.blockId);
      if (!fact || !block || block.status === "stale" ||
          working.draft?.blocks.find((item) => item.blockId === block.id)?.text !== block.state.text) continue;
      issues.push(issue(input, `DRAFT_${draftIssue.code}`, "check", "warning",
        `${block.id}:${fact.id}`, JSON.stringify([policy, factDependency(input, fact), block.revision]),
        "Проверьте обязательный факт, контекст или смысл предложенного текста.",
        "Сверьте блок с фактом и исходником.", { factId: fact.id, blockId: block.id }));
    }
  }
  for (const [blockId, typed] of Object.entries(input.rewriteIssues ?? {})) for (const item of typed) {
    const fact = project.facts.find((candidate) => candidate.id === item.factId);
    const block = project.views.find((candidate) => candidate.id === blockId);
    if (!fact || !block || block.status === "stale") continue;
    issues.push(issue(input, `REWRITE_${item.code}`, "check", "warning", `${blockId}:${fact.id}`,
      JSON.stringify([policy, factDependency(input, fact), block.revision]),
      "Проверьте факт и смысл переписанного блока.", "Сверьте блок с фактом и исходником.",
      { factId: fact.id, blockId }));
  }
  for (const block of project.views.filter((item) => item.visible && item.state.origin === "generated")) {
    issues.push(issue(input, "SOURCE_MEANING", "check", "warning", block.id,
      JSON.stringify([policy, block.revision, block.state.text, block.state.factIds,
        block.state.factIds.map((id) => project.facts.find((fact) => fact.id === id))]),
      "Связанные ID не доказывают точность смысла или отсутствие добавленных утверждений.",
      "Сверьте весь текст блока с исходником и фактами.", { blockId: block.id }));
  }
  const unique = [...new Map(issues.map((item) => [item.id, item])).values()];
  const blockers = unique.filter((item) => item.severity === "blocker");
  const warnings = unique.filter((item) => item.severity === "warning");
  return { kind: "document_readiness", status: blockers.length ? "blocked" : "ready",
    blockers, warnings, units, facts, projectSaveAllowed: true };
}

export function coverageDependency(input: CoverageInput, kind: CoverageDecision["targetKind"], id: string): string | null {
  if (kind === "fact") {
    const fact = reviewableFacts(input).find((item) => item.id === id);
    return fact ? factDependency(input, fact) : null;
  }
  if (kind === "job") {
    return jobDependency(input, id);
  }
  const source = input.working?.sources.find((item) => id.startsWith(`view_${item.entry.result.sourceId}_`));
  if (!source) return null;
  const sourceId = source.entry.result.sourceId;
  const originalId = id.slice(`view_${sourceId}_`.length);
  return source.entry.result.units.some((item) => item.id === originalId) ?
    unitDependency(input, sourceId, originalId) : null;
}
