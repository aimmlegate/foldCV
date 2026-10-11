import type { FactSheet, Facts, TextFact } from "../contracts/generated/fact_sheet";
import type { ImportedSource } from "../import/workflow";
import type { Project, Block, Source, PartialDate, Period, Job } from "../contracts/generated/project";
import type { Presentation } from "../contracts/generated/prepare_request";
import type { DraftResult } from "../contracts/generated/draft_result";
import { validateContract } from "../contracts/validate";
import catalog from "../../../../contracts/technology-catalog.json" with { type: "json" };

export type ManualSubproject = { id: string; name: string; start: string; end: string; description: string };
export type ManualEmployment = { id: string; employer: string; role: string; start: string; end: string;
  description: string; subprojects: ManualSubproject[] };
export type ManualMetric = { id: string; jobId: string | null; number: number; upperNumber: number | null;
  comparator: "exact" | "at_least" | "at_most" | "approximately" | "range"; unit: string;
  period: string | null; baseline: string | null; result: string | null; scope: string | null;
  attribution: "personal" | "team" | "organization" | "unknown"; qualifiers: string[] };
export type ManualLeadership = { id: string; jobId: string; action: string;
  attribution: "personal" | "team" | "organization" | "unknown";
  teamSize: number | null; teamUnit: string; teamBaseline: string | null };
export type ManualInput = { name: string; title: string; asOf: string; education: string; language: Presentation["sourceLanguage"];
  languages: string[]; skills: string[]; employment: ManualEmployment[]; metrics: ManualMetric[];
  leadership: ManualLeadership[] };
export type WorkingSource = { entry: ImportedSource; originalBytes: Uint8Array };
export type WorkingDraft = { transportVersion: 1; sources: WorkingSource[]; sheet: FactSheet;
  priorSheet: FactSheet | null; sourceReviewStale: boolean; manual: ManualInput; draft: DraftResult | null;
  structuredCorrections?: Record<string, string> };

const templateHash = "d081df948bfd55d107c38d40387a9758f563f9c14a9cffc4a847f44cb687b8b9";
const emptyHash = "0".repeat(64);
const aliases = new Map(catalog.entries.flatMap((entry) => entry.aliases.map((alias) => [alias, entry.canonicalId] as const)));

function manualCanonicalId(display: string, index: number): string {
  let name = display.normalize("NFKC").toLowerCase().trim().replace(/\s+/g, " ");
  if (name.startsWith("microsoft ")) name = name.slice("microsoft ".length);
  const version = name.match(/\s+(?:v)?\d+(?:\.\d+)*(?:[-+][a-z0-9.]+)?$/i);
  let base = version ? name.slice(0, version.index) : name;
  if (base === "go" && version) base = "golang";
  if (["go", "drf", "r", "node"].includes(base)) return `unknown_user_${index}`;
  return aliases.get(base) ?? `unknown_user_${index}`;
}

export function parseDate(text: string): PartialDate | null {
  if (!text.trim()) return null;
  if (!/^\d{4}(?:-\d{2}(?:-\d{2})?)?$/.test(text)) throw new Error("Укажите дату как YYYY, YYYY-MM или YYYY-MM-DD.");
  const [year = 0, month, day] = text.split("-").map(Number);
  const days = month === undefined ? 31 : [31, year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28,
    31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  if (!year || year > 9999 || month !== undefined && (month < 1 || month > 12) ||
      day !== undefined && (day < 1 || day > (days ?? 0)))
    throw new Error("Дата некорректна.");
  return { precision: day !== undefined ? "day" : month !== undefined ? "month" : "year",
    year, month: month ?? null, day: day ?? null };
}

function period(start: string, end: string): Period[] {
  const first = parseDate(start);
  const last = parseDate(end);
  if (!first && last) throw new Error("Укажите начало периода перед его концом.");
  if (!first) return [];
  if (last && (last.year < first.year || last.year === first.year && (last.month ?? 12) < (first.month ?? 1)))
    throw new Error("Конец периода раньше начала.");
  return [{ start: first, end: last }];
}

function effectiveFacts(sheet: FactSheet): Facts {
  const replaced = new Set(Object.keys(sheet.userCorrections ?? {}));
  return sheet.facts.filter((fact) => !replaced.has(fact.id));
}

function credit(value: ManualMetric["attribution"], language: ManualInput["language"]): string {
  if (language !== "ru") return value;
  return { personal: "личный вклад", team: "команда", organization: "организация", unknown: "вклад не указан" }[value];
}

function metricLine(metric: ManualMetric, language: ManualInput["language"]): string {
  const compare = language === "ru" ?
    { exact: "", at_least: "не менее ", at_most: "не более ", approximately: "примерно ", range: "" }[metric.comparator] :
    { exact: "", at_least: "at least ", at_most: "at most ", approximately: "about ", range: "" }[metric.comparator];
  const amount = metric.upperNumber === null ? String(metric.number) : `${metric.number}–${metric.upperNumber}`;
  return language === "ru" ?
    `${credit(metric.attribution, language)}: ${compare}${amount} ${metric.unit}${metric.period ? ` за ${metric.period}` : ""}${metric.scope ? ` (${metric.scope})` : ""}${metric.baseline ? `; было ${metric.baseline}` : ""}${metric.result ? `; результат ${metric.result}` : ""}${metric.qualifiers.length ? `; ${metric.qualifiers.join(", ")}` : ""}` :
    `${credit(metric.attribution, language)}: ${compare}${amount} ${metric.unit}${metric.period ? ` per ${metric.period}` : ""}${metric.scope ? ` (${metric.scope})` : ""}${metric.baseline ? `; from ${metric.baseline}` : ""}${metric.result ? `; result ${metric.result}` : ""}${metric.qualifiers.length ? `; ${metric.qualifiers.join(", ")}` : ""}`;
}

function leadershipLine(item: ManualLeadership, language: ManualInput["language"]): string {
  const size = item.teamSize === null ? "" : language === "ru" ?
    `; размер команды ${item.teamSize} ${item.teamUnit}${item.teamBaseline ? `, было ${item.teamBaseline}` : ""}` :
    `; team size ${item.teamSize} ${item.teamUnit}${item.teamBaseline ? ` from ${item.teamBaseline}` : ""}`;
  return `${credit(item.attribution, language)}: ${item.action}${size}`;
}

function sourceLocation(entry: ImportedSource, unit: ImportedSource["result"]["units"][number]): Source["units"][number]["location"] {
  const location = unit.location;
  if (location.kind === "pasted") return { kind: "pasted", index: unit.order, row: null, column: null };
  if (location.kind === "table_cell" && location.row != null && location.column != null)
    return { kind: "table_cell", index: location.table ?? unit.order, row: location.row, column: location.column };
  if (entry.result.sourceKind === "pdf") return { kind: "page", index: location.page ?? unit.order, row: null, column: null };
  return { kind: "paragraph", index: location.paragraph ?? unit.order, row: null, column: null };
}

function block(id: string, kind: Block["kind"], text: string, factIds: string[], facts: Facts): Block {
  return { id, kind, revision: 1, state: { text, origin: "manual", locked: false, factIds,
    factRevisions: Object.fromEntries(factIds.map((factId) => [factId, facts.find((fact) => fact.id === factId)?.revision ?? 1])) },
  previous: null, visible: true, status: "ready", dependencyHash: emptyHash, contentPolicyVersion: "generic-1" };
}

export function adaptWorking(working: WorkingDraft): { project: Project; presentation: Presentation; issues: string[] } {
  const { sheet, manual } = working;
  if (!manual.name.trim() || !manual.title.trim()) throw new Error("Укажите имя кандидата и должность.");
  if (!working.sources.length || !working.sources.every(({ entry, originalBytes }) =>
    originalBytes.length === entry.result.byteLength)) throw new Error("Не найдены байты оригинального источника.");
  const asOf = parseDate(manual.asOf);
  const viewUnitId = (sourceId: string, unitId: string): string => `view_${sourceId}_${unitId}`;
  const facts: Facts = effectiveFacts(sheet).map((fact) => ({ ...fact, evidence: fact.evidence.map((evidence) => ({
    ...evidence, unitId: viewUnitId(evidence.sourceId, evidence.unitId) })) }));
  for (const [index, skill] of manual.skills.entries()) {
    if (!skill.trim()) continue;
    facts.push({ id: `fact_user_skill_${index}`, revision: 1, kind: "technology", value: {
      canonicalId: manualCanonicalId(skill, index), display: skill.trim(), scope: "global" },
      evidence: [], origin: "user", importance: "normal", jobId: null, subprojectId: null });
  }
  const manualIds = new Set(manual.employment.map((job) => job.id));
  if (manualIds.size !== manual.employment.length || manual.employment.some((job) =>
    !job.employer.trim() || !job.role.trim() || !job.description.trim() || job.subprojects.some((sub) =>
      !sub.name.trim() || !sub.description.trim()))) throw new Error("Заполните каждую работу и подпроект дословным текстом.");
  for (const job of manual.employment) {
    const descriptions = [{ id: `fact_user_manual_job_${job.id}`, text: job.description.trim(), subprojectId: null },
      ...job.subprojects.map((sub) => ({ id: `fact_user_manual_sub_${sub.id}`, text: sub.description.trim(), subprojectId: sub.id }))];
    for (const item of descriptions) {
      if (item.text.length > 4_000 || facts.some((fact) => fact.id === item.id))
        throw new Error("Проверьте длину и уникальность ручного описания работы.");
      facts.push({ id: item.id, revision: 1, kind: "text", value: { text: item.text },
        evidence: [], origin: "user", importance: "normal", jobId: job.id, subprojectId: item.subprojectId });
    }
  }
  for (const metric of manual.metrics) {
    if (!metric.unit.trim() || !Number.isFinite(metric.number) || metric.upperNumber !== null &&
        (!Number.isFinite(metric.upperNumber) || metric.upperNumber < metric.number) ||
        (metric.comparator === "range") !== (metric.upperNumber !== null) ||
        metric.jobId !== null && !manualIds.has(metric.jobId)) throw new Error("Проверьте число, единицу и привязку к работе.");
    facts.push({ id: metric.id, revision: 1, kind: "metric", value: { number: metric.number,
      upperNumber: metric.upperNumber, comparator: metric.comparator, unit: metric.unit,
      period: metric.period, baseline: metric.baseline, result: metric.result, scope: metric.scope,
      attribution: metric.attribution, qualifiers: metric.qualifiers }, evidence: [], origin: "user",
      importance: "normal", jobId: metric.jobId, subprojectId: null });
  }
  for (const item of manual.leadership) {
    if (!manualIds.has(item.jobId) || !item.action.trim() || item.teamSize !== null &&
        (!Number.isFinite(item.teamSize) || item.teamSize < 0 || !item.teamUnit.trim()))
      throw new Error("Заполните действие руководства, работу и вклад команды.");
    facts.push({ id: item.id, revision: 1, kind: "leadership", value: { action: item.action.trim(),
      attribution: item.attribution, teamSize: item.teamSize === null ? null : {
        number: item.teamSize, upperNumber: null, comparator: "exact", unit: item.teamUnit.trim(),
        period: null, baseline: item.teamBaseline, result: null, scope: null,
        attribution: item.attribution, qualifiers: [] } }, evidence: [], origin: "user",
      importance: "normal", jobId: item.jobId, subprojectId: null });
  }
  const sources: Source[] = working.sources.map(({ entry }) => ({ id: entry.result.sourceId, revision: 1,
    originalName: entry.result.originalName, mimeType: entry.result.mimeType,
    byteSha256: entry.result.byteSha256, byteRef: `sources/${entry.result.sourceId}/original`,
    parser: entry.result.parser, parserVersion: entry.result.parserVersion,
    units: entry.result.units.map((unit) => ({ id: viewUnitId(entry.result.sourceId, unit.id), revision: 1, order: unit.order, text: unit.text,
      location: sourceLocation(entry, unit), disposition: sheet.units.find((account) =>
        account.sourceId === entry.result.sourceId && account.unitId === unit.id)?.disposition === "duplicate" ? "duplicate" : "unresolved",
      representedFactIds: facts.filter((fact) => fact.origin === "source" && fact.evidence.some((evidence) =>
        evidence.sourceId === entry.result.sourceId && evidence.unitId === viewUnitId(entry.result.sourceId, unit.id))).map((fact) => fact.id) })),
    overlays: Object.entries(entry.overlays).filter(([key]) => key.startsWith("unit:")).map(([key, text]) => ({
      id: `overlay_${entry.result.sourceId}_${key.slice(5)}`, revision: 1,
      unitId: viewUnitId(entry.result.sourceId, key.slice(5)), text, origin: "user" })),
    warnings: entry.result.gaps.map((gap) => gap.code),
  }));
  const employment: Job[] = [
    ...(sheet.employment ?? []).map((job) => ({ id: job.id, employer: job.employer, role: job.role,
      periods: job.periods, subprojects: job.subprojects.map((sub) => ({ id: sub.id, name: sub.name,
        period: sub.period ?? null, factIds: facts.filter((fact) => fact.subprojectId === sub.id).map((fact) => fact.id) })),
      factIds: facts.filter((fact) => fact.jobId === job.id).map((fact) => fact.id) })),
    ...manual.employment.map((job) => ({ id: job.id, employer: job.employer, role: job.role,
      periods: period(job.start, job.end), subprojects: job.subprojects.map((sub) => ({ id: sub.id,
        name: sub.name, period: period(sub.start, sub.end)[0] ?? null,
        factIds: facts.filter((fact) => fact.subprojectId === sub.id).map((fact) => fact.id) })),
      factIds: facts.filter((fact) => fact.jobId === job.id).map((fact) => fact.id) })),
  ].map((job) => {
    const corrections = working.structuredCorrections ?? {};
    const employer = corrections[`job:${job.id}:employer`] ?? job.employer;
    const role = corrections[`job:${job.id}:role`] ?? job.role;
    const start = corrections[`job:${job.id}:start`];
    const end = corrections[`job:${job.id}:end`];
    const first = job.periods[0];
    const periods = first && (start !== undefined || end !== undefined) ?
      [{ start: start === undefined ? first.start : parseDate(start) ?? first.start,
        end: end === undefined ? first.end : parseDate(end) }, ...job.periods.slice(1)] :
      !first && start ? [{ start: parseDate(start)!, end: end === undefined ? null : parseDate(end) }] : job.periods;
    const subprojects = job.subprojects.map((sub) => {
      const subStart = corrections[`subproject:${sub.id}:start`];
      const subEnd = corrections[`subproject:${sub.id}:end`];
      const subPeriod = sub.period && (subStart !== undefined || subEnd !== undefined) ?
        { start: subStart === undefined ? sub.period.start : parseDate(subStart) ?? sub.period.start,
          end: subEnd === undefined ? sub.period.end : parseDate(subEnd) } :
        !sub.period && subStart ? { start: parseDate(subStart)!, end: subEnd === undefined ? null : parseDate(subEnd) } : sub.period;
      return { ...sub, name: corrections[`subproject:${sub.id}:name`] ?? sub.name, period: subPeriod };
    });
    return { ...job, employer, role, periods, subprojects };
  });
  const jobProseBlocks: Record<string, string> = {};
  const views: Block[] = [];
  const profileFacts = facts.filter((fact): fact is TextFact => fact.kind === "text" && fact.jobId === null)
    .filter((fact) => !/^(e-?mail|phone|телефон|почта|возраст|age)\b/i.test(fact.value.text));
  const profileText = profileFacts.map((fact) => fact.value.text);
  const globalMetrics = manual.metrics.filter((metric) => metric.jobId === null);
  views.push(block("profile", "profile", [...profileText, ...globalMetrics.map((metric) => metricLine(metric, manual.language))].join("\n"),
    [...profileFacts.map((fact) => fact.id), ...globalMetrics.map((metric) => metric.id)], facts));
  const issues: string[] = sheet.issues.map((issue) => issue.message);
  if (!employment.length) issues.push("Нет записей о работе. Добавьте работу вручную или проверьте лист фактов.");
  for (const job of manual.employment) {
    const spans = period(job.start, job.end);
    if (!spans.length) issues.push(`У работы ${job.employer} не указан период. Добавьте даты работы.`);
    else if (spans.some((span) => span.start.precision !== "day" || span.end?.precision !== "day" && span.end !== null))
      issues.push(`У работы ${job.employer} даты указаны частично. Проверьте точность периода.`);
    for (const sub of job.subprojects) {
      const subspans = period(sub.start, sub.end);
      if (!subspans.length) issues.push(`У подпроекта ${sub.name} не указан период. Добавьте даты подпроекта.`);
      else if (subspans.some((span) => span.start.precision !== "day" || span.end?.precision !== "day" && span.end !== null))
        issues.push(`У подпроекта ${sub.name} даты указаны частично. Проверьте точность периода.`);
    }
  }
  if (asOf === null && employment.some((job) => job.periods.some((span) => span.end === null)))
    issues.push("Нет даты наблюдения для текущей работы. Укажите её, чтобы рассчитать длительность.");
  if (working.sourceReviewStale) issues.push("Проверка исходника устарела. Сверьте факты и исправления перед использованием черновика.");
  if (working.priorSheet) issues.push("Прежний принятый лист фактов сохранён в памяти для сравнения.");
  if (working.priorSheet && Object.keys(working.priorSheet.userCorrections ?? {}).some((id) =>
    !Object.hasOwn(sheet.userCorrections ?? {}, id)))
    issues.push("Часть прежних исправлений не связана с новым листом фактов. Сверьте оба листа перед использованием.");
  for (const job of employment) {
    const manualJob = manual.employment.find((item) => item.id === job.id);
    const reviewed = sheet.employment?.find((item) => item.id === job.id);
    const sourceText = reviewed ? working.sources.flatMap(({ entry }) => entry.result.sourceId === reviewed.sourceId ?
      entry.result.units.filter((unit) => reviewed.unitIds.includes(unit.id)).map((unit) => {
        const corrected = Object.entries(sheet.userCorrections ?? {}).filter(([sourceId]) =>
          sheet.facts.some((fact) => fact.id === sourceId && fact.evidence.some((evidence) =>
            evidence.sourceId === reviewed.sourceId && evidence.unitId === unit.id)));
        if (corrected.length) {
          issues.push(`Проверьте исправление для ${job.employer}, фрагмент ${unit.id}: другие факты этого фрагмента могут требовать переноса.`);
          return corrected.flatMap(([, userId]) => sheet.facts.flatMap((fact) =>
            fact.id === userId && fact.kind === "text" ? [fact.value.text] : [])).join("\n");
        }
        return entry.overlays[`unit:${unit.id}`]?.trim() || unit.text;
      }) : []).join("\n") : "";
    const jobFacts = facts.filter((fact) => fact.jobId === job.id);
    const manualText = manualJob ? [manualJob.description.trim(), ...manualJob.subprojects.map((sub) =>
      `${sub.name}: ${sub.description}`), ...manual.metrics.filter((metric) => metric.jobId === job.id).map((metric) => metricLine(metric, manual.language)),
      ...manual.leadership.filter((item) => item.jobId === job.id).map((item) => leadershipLine(item, manual.language))]
      .filter(Boolean).join("\n") : "";
    const text = manualText || sourceText || jobFacts.flatMap((fact) => fact.kind === "text" ? [fact.value.text] : []).join("\n");
    if (!text) issues.push(`Нет текста работы ${job.employer}. Введите его перед просмотром PDF.`);
    const id = `prose_${job.id}`;
    jobProseBlocks[job.id] = id;
    views.push(block(id, "job_prose", text, jobFacts.map((fact) => fact.id), facts));
  }
  views.push(block("focus", "focus", "", [], facts));
  views.push(block("skills", "skills", "", [], facts));
  views.push(block("early_career", "early_career", "", [], facts));
  views.push(block("education", "education", manual.education.trim(), [], facts));
  const project: Project = { schemaVersion: 3, projectId: `working_${crypto.randomUUID()}`, revision: 1,
    asOf, createdAt: new Date().toISOString(), sources, facts, employment, views,
    template: { id: "generic", version: "1.0.0", packageSha256: templateHash, contentPolicyVersion: "generic-1", assets: [] },
    review: { decisions: [], acknowledgments: [] }, operations: [], proposals: [], renders: [] };
  if (!validateContract("project", project)) throw new Error("Проверьте связи импортированных фактов перед открытием редактора.");
  return { project, presentation: { name: manual.name.trim(), title: manual.title.trim(),
    sourceLanguage: manual.language, languages: manual.languages, jobProseBlocks }, issues };
}

export function adaptDraftedWorking(working: WorkingDraft): { project: Project; presentation: Presentation; issues: string[] } {
  const adapted = adaptWorking(working);
  const draft = working.draft;
  if (!draft || draft.sourceFingerprint !== working.sheet.sourceFingerprint ||
      draft.baseRevision !== working.sheet.revision) throw new Error("Черновик относится к старому листу фактов.");
  const allowed = new Set(effectiveFacts(working.sheet).map((fact) => fact.id));
  const blocks = new Set(adapted.project.views.filter((block) => block.kind === "profile" || block.kind === "job_prose")
    .map((block) => block.id));
  if (draft.blocks.some((item) => !blocks.has(item.blockId) ||
      item.factIds.some((id) => !allowed.has(id)))) throw new Error("Черновик содержит неверные связи фактов.");
  const byId = new Map(draft.blocks.map((item) => [item.blockId, item]));
  const preserveProfile = working.manual.metrics.some((metric) => metric.jobId === null);
  const project: Project = { ...adapted.project, revision: adapted.project.revision + 1,
    views: adapted.project.views.map((block) => {
      const proposed = byId.get(block.id);
      if (!proposed || block.id === "profile" && preserveProfile) return block;
      return { ...block, revision: block.revision + 1, previous: block.state, status: "proposed",
        state: { text: proposed.text, origin: "generated", locked: false, factIds: proposed.factIds,
          factRevisions: Object.fromEntries(proposed.factIds.map((id) =>
            [id, adapted.project.facts.find((fact) => fact.id === id)?.revision ?? 1])) } };
    }) };
  if (!validateContract("project", project)) throw new Error("Проверьте связи черновика перед открытием редактора.");
  return { ...adapted, project, issues: [...adapted.issues, ...draft.issues.map((issue) =>
    `${issue.blockId} · ${issue.factId}: ${issue.message}`),
    ...(preserveProfile ? ["Модельный текст профиля не запрашивался: сохранены ручные числа и вклад."] : []),
    "Текст предложен моделью. Проверьте смысл по исходнику перед подтверждением."] };
}
