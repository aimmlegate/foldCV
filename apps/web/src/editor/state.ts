import type { Block, BlockState, Facts, Project, Review } from "../contracts/generated/project";
import { syntheticProject } from "./example";
import type { Presentation } from "../contracts/generated/prepare_request";
import type { WorkingDraft } from "../facts/working";
import { validateContract, validateFactSheet } from "../contracts/validate";
import type { RewriteResult } from "../contracts/generated/rewrite_result";
import type { RewritePreflightFailure } from "../contracts/generated/rewrite_preflight_failure";
import type { RewriteIssue } from "../contracts/generated/rewrite_result";
import { parseDate } from "../facts/working";
import { coverageDependency, coverageReview } from "./coverage";
import type { CoverageDecision, SourceIntegrity } from "./coverage";
import type { WorkingSource } from "../facts/working";
import catalog from "../../../../contracts/technology-catalog.json" with { type: "json" };

type Fact = Facts[number];

export type Stage = "import" | "editor" | "export";
export type Panel = "preview" | "sources" | "checks";
type Drafts = Record<string, string>;
type Checkpoint = { state: BlockState; revision: number; visible: boolean; status: Block["status"]; dependencyHash: string;
  review: Review; issues: string[]; issueDetails: RewriteIssue[];
  coverage: NonNullable<WorkingDraft["coverage"]> | null; manualEducation: string | null };
export type PendingRewrite = { result: RewriteResult; before: string };
export type EditorState = {
  project: Project | null;
  loadId: string | null;
  working: WorkingDraft | null;
  sourceIntegrity: SourceIntegrity | null;
  workingIssues: string[];
  presentation: Presentation | null;
  presentationDrafts: { name?: string; title?: string };
  presentationUndo: Presentation | null;
  stage: Stage;
  panel: Panel;
  selectedId: string | null;
  drafts: Drafts;
  factDrafts: Drafts;
  structuredDrafts: Drafts;
  errors: Drafts;
  undo: Record<string, Checkpoint>;
  rewriteProposal: PendingRewrite | null;
  rewriteIssues: Record<string, string[]>;
  rewriteIssueDetails: Record<string, RewriteIssue[]>;
  sourceText: string;
  dirty: boolean;
};
export type Action =
  | { type: "loadExample"; loadId: string }
  | { type: "loadImported"; loadId: string; project: Project; presentation: Presentation; working: WorkingDraft; issues: string[] }
  | { type: "sourceIntegrity"; loadId: string; sources: WorkingSource[]; proof: SourceIntegrity }
  | { type: "resetProject" }
  | { type: "stage"; stage: Stage }
  | { type: "panel"; panel: Panel }
  | { type: "select"; id: string }
  | { type: "sourceText"; text: string }
  | { type: "presentationDraft"; field: "name" | "title"; text: string }
  | { type: "presentationApply"; field: "name" | "title" }
  | { type: "presentationCancel"; field: "name" | "title" }
  | { type: "presentationLanguage"; language: Presentation["sourceLanguage"] }
  | { type: "presentationUndo" }
  | { type: "draft"; id: string; text: string }
  | { type: "factDraft"; id: string; text: string }
  | { type: "cancelFact"; id: string }
  | { type: "cancel"; id: string }
  | { type: "apply"; id: string }
  | { type: "lock"; id: string }
  | { type: "visible"; id: string }
  | { type: "undo"; id: string }
  | { type: "review"; id: string }
  | { type: "fact"; id: string; value: string }
  | { type: "structuredDraft"; key: string; text: string }
  | { type: "structuredCancel"; key: string }
  | { type: "jobField"; id: string; field: "employer" | "role" | "start" | "end"; value: string }
  | { type: "subprojectField"; jobId: string; id: string; field: "name" | "start" | "end"; value: string }
  | { type: "languages"; value: string }
  | { type: "asOf"; value: string }
  | { type: "rewriteProposed"; result: RewriteResult }
  | { type: "rewritePreflight"; result: RewritePreflightFailure; loadId: string }
  | { type: "rewriteApply"; id: string }
  | { type: "rewriteDiscard" }
  | { type: "reconcile"; id: string; projectId: string; loadId: string; baseRevision: number; blockRevision: number; dependencyHash: string }
  | { type: "coverageDecision"; targetKind: CoverageDecision["targetKind"]; targetId: string;
      disposition: CoverageDecision["disposition"]; reason: string; dependency: string }
  | { type: "coverageClear"; targetKind: CoverageDecision["targetKind"]; targetId: string }
  | { type: "coverageAcknowledge"; issueId: string; dependency: string };

export const initialEditorState: EditorState = {
  project: null, loadId: null, working: null, sourceIntegrity: null, workingIssues: [], presentation: null, presentationDrafts: {}, presentationUndo: null,
  stage: "import", panel: "preview", selectedId: null,
  drafts: {}, factDrafts: {}, structuredDrafts: {}, errors: {}, undo: {}, rewriteProposal: null,
  rewriteIssues: {}, rewriteIssueDetails: {}, sourceText: "", dirty: false,
};

export function selectedBlock(state: EditorState): Block | undefined {
  return state.project?.views.find((block) => block.id === state.selectedId);
}

export function recentJobIds(project: Project): Set<string> {
  const asOf = project.asOf;
  if (!asOf) return new Set();
  const cutoffYear = asOf.year - 15;
  const month = asOf.month ?? 1;
  const day = Math.min(asOf.day ?? 1, new Date(Date.UTC(cutoffYear, month, 0)).getUTCDate());
  const cutoff = cutoffYear < 1 ? null : Date.UTC(cutoffYear, month - 1, day);
  return new Set(project.employment.filter((job) => job.periods.length > 0 && job.periods.some((period) => {
    if (!period.end || cutoff === null) return true;
    const end = period.end;
    const upper = Date.UTC(end.year, (end.month ?? 12) - 1,
      end.day ?? new Date(Date.UTC(end.year, end.month ?? 12, 0)).getUTCDate());
    return upper >= cutoff;
  })).map((job) => job.id));
}

export function scopedFactsForBlock(state: EditorState, block: Block): Facts {
  const project = state.project;
  if (!project || !state.presentation) return [];
  if (block.kind === "profile") {
    const recent = recentJobIds(project);
    const corrected = new Set(Object.values(state.working?.sheet.userCorrections ?? {}));
    return project.facts.filter((fact) => fact.jobId !== null ? recent.has(fact.jobId) ||
      block.state.factIds.includes(fact.id) : fact.importance === "essential" || corrected.has(fact.id) ||
      fact.origin === "user" || fact.kind === "metric" || fact.kind === "leadership" ||
      block.state.factIds.includes(fact.id));
  }
  if (block.kind !== "job_prose") return [];
  const jobId = Object.entries(state.presentation.jobProseBlocks).find(([, id]) => id === block.id)?.[0];
  return jobId ? project.facts.filter((fact) => fact.jobId === jobId) : [];
}

export function draftFor(state: EditorState, block: Block): string {
  return state.drafts[block.id] ?? block.state.text;
}

export function hasUnappliedDraft(state: EditorState): boolean {
  return Boolean(state.project && (Object.entries(state.presentationDrafts).some(([field, text]) =>
      text !== state.presentation?.[field as "name" | "title"])
    || state.project.views.some((block) => draftFor(state, block) !== block.state.text)
    || state.project.facts.some((fact) => state.factDrafts[fact.id] !== undefined && state.factDrafts[fact.id] !== factDisplay(fact))
    || Object.keys(state.structuredDrafts).length > 0));
}

export function renderStale(project: Project): boolean {
  return !project.renders.some((render) => render.projectRevision === project.revision && render.pdf !== null);
}

function reviewForCurrent(project: Project, review: Review): Review {
  const revision = (kind: string, id: string): number | undefined =>
    kind === "fact" ? project.facts.find((fact) => fact.id === id)?.revision
      : kind === "block" ? project.views.find((block) => block.id === id)?.revision
        : project.sources.flatMap((source) => source.units).find((unit) => unit.id === id)?.revision;
  return {
    decisions: review.decisions.filter((decision) => revision(decision.targetKind, decision.targetId) === decision.targetRevision),
    acknowledgments: review.acknowledgments.filter((ack) => revision(ack.targetKind, ack.targetId) === ack.targetRevision),
  };
}

function cloneState(state: BlockState): BlockState {
  return { ...state, factIds: [...state.factIds], factRevisions: { ...state.factRevisions } };
}

function syncWorkingPresentation(working: WorkingDraft | null, presentation: Presentation): WorkingDraft | null {
  return working ? { ...working, manual: { ...working.manual, name: presentation.name,
    title: presentation.title, language: presentation.sourceLanguage,
    languages: presentation.languages ?? [] } } : null;
}

function replaceBlock(state: EditorState, id: string, update: (block: Block) => Block): EditorState {
  const project = state.project;
  const block = project?.views.find((item) => item.id === id);
  if (!project || !block) return state;
  const checkpoint: Checkpoint = {
    state: block.state, revision: block.revision, visible: block.visible, status: block.status,
    dependencyHash: block.dependencyHash,
    issues: state.rewriteIssues[id] ?? [],
    issueDetails: state.rewriteIssueDetails[id] ?? [],
    coverage: state.working?.coverage ? structuredClone(state.working.coverage) : null,
    manualEducation: block.kind === "education" ? state.working?.manual.education ?? null : null,
    review: {
      decisions: project.review.decisions.filter((decision) => decision.targetKind === "block" && decision.targetId === id),
      acknowledgments: project.review.acknowledgments.filter((ack) => ack.targetKind === "block" && ack.targetId === id),
    },
  };
  const proposed = update(block);
  const updated: Block = { ...proposed, state: cloneState(proposed.state), previous: proposed.previous ? cloneState(proposed.previous) : null };
  if (proposed === block) return state;
  return {
    ...state, dirty: true, undo: { ...state.undo, [id]: checkpoint },
    rewriteProposal: state.rewriteProposal?.result.blockId === id ? null : state.rewriteProposal,
    project: {
      ...project, revision: project.revision + 1,
      views: project.views.map((item) => item.id === id ? updated : item),
      review: {
        decisions: project.review.decisions.filter((decision) => !(decision.targetKind === "block" && decision.targetId === id)),
        acknowledgments: project.review.acknowledgments.filter((ack) => !(ack.targetKind === "block" && ack.targetId === id)),
      },
    },
  };
}

function relatedCoverageTargets(state: EditorState, blockId: string, priorFactIds: string[] = []): Set<string> {
  const project = state.project;
  const block = project?.views.find((item) => item.id === blockId);
  const ids = new Set<string>();
  if (!project || !block) return ids;
  const jobIds = block.kind === "job_prose" ? Object.entries(state.presentation?.jobProseBlocks ?? {})
    .filter(([, id]) => id === blockId).map(([jobId]) => jobId) : [];
  for (const jobId of jobIds) ids.add(`job:${jobId}`);
  const addProjectUnit = (unitId: string): void => { ids.add(`unit:${unitId}`); };
  const addSheetUnit = (sourceId: string, unitId: string): void => {
    ids.add(`unit:view_${sourceId}_${unitId}`);
  };
  const facts = project.facts.filter((fact) => block.state.factIds.includes(fact.id) ||
    priorFactIds.includes(fact.id) ||
    jobIds.includes(fact.jobId ?? ""));
  for (const fact of facts) {
    ids.add(`fact:${fact.id}`);
    for (const evidence of fact.evidence) addProjectUnit(evidence.unitId);
    for (const [sourceId, correctedId] of Object.entries(state.working?.sheet.userCorrections ?? {})) {
      if (correctedId !== fact.id) continue;
      for (const evidence of state.working?.sheet.facts.find((item) => item.id === sourceId)?.evidence ?? [])
        addSheetUnit(evidence.sourceId, evidence.unitId);
    }
  }
  return ids;
}

function factDisplay(fact: Fact): string | null {
  if (fact.kind === "text") return fact.value.text;
  if (fact.kind === "metric") return String(fact.value.number);
  if (fact.kind === "technology") return fact.value.display;
  return null;
}

export function editableFactValue(fact: Fact): string | null { return factDisplay(fact); }

export function structuredKey(kind: "job" | "subproject", id: string, field: string): string {
  return `${kind}:${id}:${field}`;
}

function structuredError(state: EditorState, key: string): EditorState {
  return { ...state, errors: { ...state.errors, [key]: "Введите корректное значение." } };
}

function staleViews(project: Project, ids: string[]): Project {
  return { ...project, views: project.views.map((view) => ids.includes(view.id) ? { ...view, status: "stale" } : view),
    review: { decisions: project.review.decisions.filter((item) => !(item.targetKind === "block" && ids.includes(item.targetId))),
      acknowledgments: project.review.acknowledgments.filter((item) => !(item.targetKind === "block" && ids.includes(item.targetId))) } };
}

function dateText(value: Project["asOf"]): string {
  return value ? `${value.year}${value.month === null ? "" : `-${String(value.month).padStart(2, "0")}`}${value.day === null ? "" : `-${String(value.day).padStart(2, "0")}`}` : "";
}

export function jobFieldValue(state: EditorState, id: string, field: "employer" | "role" | "start" | "end"): string {
  const job = state.project?.employment.find((item) => item.id === id);
  if (!job) return "";
  if (field === "employer" || field === "role") return job[field];
  return dateText(field === "start" ? job.periods[0]?.start ?? null : job.periods[0]?.end ?? null);
}

export function asOfValue(state: EditorState): string { return dateText(state.project?.asOf ?? null); }

export function subprojectFieldValue(state: EditorState, jobId: string, id: string, field: "name" | "start" | "end"): string {
  const sub = state.project?.employment.find((job) => job.id === jobId)?.subprojects.find((item) => item.id === id);
  if (!sub) return "";
  return field === "name" ? sub.name : dateText(field === "start" ? sub.period?.start ?? null : sub.period?.end ?? null);
}

function reduceEditorState(state: EditorState, action: Action): EditorState {
  switch (action.type) {
    case "coverageDecision": {
      if (!state.project || !state.working) return state;
      const input = { project: state.project, working: state.working, presentation: state.presentation,
        rewriteIssues: state.rewriteIssueDetails, sourceIntegrity: state.sourceIntegrity };
      if (coverageDependency(input, action.targetKind, action.targetId) !== action.dependency) return state;
      const review = coverageReview(input);
      const target = [...review.units, ...review.facts].find((item) =>
        item.kind === action.targetKind && item.id === action.targetId);
      const missingJob = action.targetKind === "job" && review.blockers.some((item) =>
        item.code === "MISSING_JOB" && item.jobId === action.targetId);
      if (!target && !missingJob) return state;
      const reason = action.reason.trim();
      if ((action.disposition === "excluded" || action.disposition === "archived" ||
          action.disposition === "shown" && target?.confirmable) && !reason) return state;
      if (action.targetKind === "job" && action.disposition !== "excluded") return state;
      if (target && ["shown", "condensed", "duplicate"].includes(action.disposition) &&
        target.disposition !== action.disposition && !(action.disposition === "shown" && target.confirmable)) return state;
      const decisions = state.working.coverage?.decisions.filter((item) =>
        item.targetKind !== action.targetKind || item.targetId !== action.targetId) ?? [];
      return { ...state, dirty: true, working: { ...state.working, coverage: {
        decisions: [...decisions, { targetKind: action.targetKind, targetId: action.targetId,
          disposition: action.disposition, reason: reason || null, dependency: action.dependency }],
        acknowledgments: state.working.coverage?.acknowledgments ?? [] } } };
    }
    case "coverageClear": {
      if (!state.working?.coverage) return state;
      return { ...state, dirty: true, working: { ...state.working, coverage: {
        ...state.working.coverage, decisions: state.working.coverage.decisions.filter((item) =>
          item.targetKind !== action.targetKind || item.targetId !== action.targetId) } } };
    }
    case "coverageAcknowledge": {
      if (!state.project || !state.working) return state;
      const review = coverageReview({ project: state.project, working: state.working,
        presentation: state.presentation, rewriteIssues: state.rewriteIssueDetails,
        sourceIntegrity: state.sourceIntegrity });
      const warning = review.warnings.find((item) => item.id === action.issueId &&
        item.dependency === action.dependency);
      if (!warning) return state;
      const acknowledgments = state.working.coverage?.acknowledgments.filter((item) =>
        item.issueId !== action.issueId) ?? [];
      return { ...state, dirty: true, working: { ...state.working, coverage: {
        decisions: state.working.coverage?.decisions ?? [],
        acknowledgments: warning.acknowledged ? acknowledgments :
          [...acknowledgments, { issueId: action.issueId, dependency: action.dependency }] } } };
    }
    case "rewritePreflight": {
      const block = state.project?.views.find((item) => item.id === action.result.blockId);
      if (!block || state.loadId !== action.loadId || state.project?.revision !== action.result.baseRevision ||
          block.revision !== action.result.blockRevision) return state;
      const issues = action.result.issues.map((issue) =>
        `${issue.blockId} · ${issue.factId}: Требуемый факт или фрагмент скрыт из-за возможных контактных данных. Проверьте вручную.`);
      return { ...state, rewriteIssues: { ...state.rewriteIssues, [block.id]: issues },
        rewriteIssueDetails: { ...state.rewriteIssueDetails, [block.id]: action.result.issues } };
    }
    case "rewriteProposed": {
      const block = state.project?.views.find((item) => item.id === action.result.blockId);
      if (!block || !state.working || !["profile", "job_prose"].includes(block.kind) || hasUnappliedDraft(state) ||
          state.project?.revision !== action.result.baseRevision || block.revision !== action.result.blockRevision ||
          block.state.locked || state.drafts[block.id] !== undefined && state.drafts[block.id] !== block.state.text)
        return state;
      return { ...state, rewriteProposal: { result: action.result, before: block.state.text } };
    }
    case "structuredDraft": return { ...state, rewriteProposal: null,
      structuredDrafts: { ...state.structuredDrafts, [action.key]: action.text },
      errors: { ...state.errors, [action.key]: "" } };
    case "structuredCancel": {
      const structuredDrafts = { ...state.structuredDrafts };
      delete structuredDrafts[action.key];
      return { ...state, structuredDrafts, errors: { ...state.errors, [action.key]: "" } };
    }
    case "languages": {
      if (!state.project || !state.presentation || !state.working) return state;
      const key = "languages";
      const languages = action.value.split(",").map((item) => item.trim()).filter(Boolean);
      if (languages.length > 20 || languages.some((item) => item.length > 80)) return structuredError(state, key);
      if (JSON.stringify(languages) === JSON.stringify(state.presentation.languages ?? []))
        return editorReducer(state, { type: "structuredCancel", key });
      const structuredDrafts = { ...state.structuredDrafts };
      delete structuredDrafts[key];
      return { ...state, structuredDrafts, dirty: true, presentationUndo: state.presentation,
        presentation: { ...state.presentation, languages },
        working: syncWorkingPresentation(state.working, { ...state.presentation, languages }),
        project: { ...state.project, revision: state.project.revision + 1 }, rewriteProposal: null };
    }
    case "asOf": {
      if (!state.project || !state.working) return state;
      const key = "asOf";
      let asOf: Project["asOf"];
      try { asOf = parseDate(action.value.trim()); } catch { return structuredError(state, key); }
      if (dateText(asOf) === dateText(state.project.asOf)) return editorReducer(state, { type: "structuredCancel", key });
      const affected = state.project.views.filter((view) => view.kind === "profile" || view.kind === "job_prose")
        .map((view) => view.id);
      const candidate = staleViews({ ...state.project, asOf, revision: state.project.revision + 1 }, affected);
      if (!validateContract("project", candidate)) return structuredError(state, key);
      const structuredDrafts = { ...state.structuredDrafts };
      delete structuredDrafts[key];
      return { ...state, project: candidate, working: { ...state.working,
        manual: { ...state.working.manual, asOf: action.value.trim() } }, structuredDrafts,
        rewriteProposal: null, undo: {}, dirty: true, errors: { ...state.errors, [key]: "" } };
    }
    case "jobField": {
      const project = state.project;
      const working = state.working;
      const job = project?.employment.find((item) => item.id === action.id);
      if (!project || !working || !job) return state;
      const key = structuredKey("job", action.id, action.field);
      const value = action.value.trim();
      if (value === jobFieldValue(state, action.id, action.field)) return editorReducer(state, { type: "structuredCancel", key });
      if (value.length > 240 || (action.field === "employer" || action.field === "role") && !value)
        return structuredError(state, key);
      let periods = job.periods;
      if (action.field === "start" || action.field === "end") {
        try {
          const parsed = parseDate(value);
          const first = periods[0];
          if (action.field === "start" && !parsed || action.field === "end" && !first && parsed) return structuredError(state, key);
          if (first && (parsed || action.field === "end")) periods = [{ ...first, [action.field]: parsed }, ...periods.slice(1)];
          else if (parsed) periods = [{ start: parsed, end: null }];
        } catch { return structuredError(state, key); }
      }
      const employment = project.employment.map((item) => item.id === action.id ?
        { ...item, ...(action.field === "employer" || action.field === "role" ? { [action.field]: value } : { periods }) } : item);
      const affected = project.views.filter((view) => view.kind === "profile" ||
        state.presentation?.jobProseBlocks[action.id] === view.id).map((view) => view.id);
      const candidate = staleViews({ ...project, revision: project.revision + 1, employment }, affected);
      if (!validateContract("project", candidate)) return structuredError(state, key);
      const manualJob = working.manual.employment.find((item) => item.id === action.id);
      const nextWorking = manualJob ? { ...working, manual: { ...working.manual,
        employment: working.manual.employment.map((item) => item.id === action.id ?
          { ...item, [action.field]: value } : item) } } :
        { ...working, structuredCorrections: { ...working.structuredCorrections, [key]: value } };
      const structuredDrafts = { ...state.structuredDrafts };
      delete structuredDrafts[key];
      const undo = { ...state.undo };
      for (const id of affected) delete undo[id];
      return { ...state, project: candidate, working: nextWorking, structuredDrafts, undo,
        rewriteProposal: null, dirty: true, errors: { ...state.errors, [key]: "" } };
    }
    case "subprojectField": {
      const project = state.project;
      const working = state.working;
      const job = project?.employment.find((item) => item.id === action.jobId);
      const sub = job?.subprojects.find((item) => item.id === action.id);
      if (!project || !working || !job || !sub) return state;
      const key = structuredKey("subproject", action.id, action.field);
      const value = action.value.trim();
      if (value === subprojectFieldValue(state, action.jobId, action.id, action.field))
        return editorReducer(state, { type: "structuredCancel", key });
      if (value.length > 240 || action.field === "name" && !value) return structuredError(state, key);
      let period = sub.period;
      if (action.field === "start" || action.field === "end") {
        try {
          const parsed = parseDate(value);
          if (action.field === "start" && !parsed || action.field === "end" && !period && parsed) return structuredError(state, key);
          if (period && (parsed || action.field === "end")) period = { ...period, [action.field]: parsed };
          else if (parsed) period = { start: parsed, end: null };
        } catch { return structuredError(state, key); }
      }
      const employment = project.employment.map((item) => item.id === action.jobId ? { ...item,
        subprojects: item.subprojects.map((part) => part.id === action.id ?
          { ...part, ...(action.field === "name" ? { name: value } : { period }) } : part) } : item);
      const affected = project.views.filter((view) => view.kind === "profile" ||
        state.presentation?.jobProseBlocks[action.jobId] === view.id).map((view) => view.id);
      const candidate = staleViews({ ...project, revision: project.revision + 1, employment }, affected);
      if (!validateContract("project", candidate)) return structuredError(state, key);
      const manualJob = working.manual.employment.find((item) => item.id === action.jobId);
      const nextWorking = manualJob ? { ...working, manual: { ...working.manual,
        employment: working.manual.employment.map((item) => item.id === action.jobId ? { ...item,
          subprojects: item.subprojects.map((part) => part.id === action.id ? { ...part, [action.field]: value } : part) } : item) } } :
        { ...working, structuredCorrections: { ...working.structuredCorrections, [key]: value } };
      const structuredDrafts = { ...state.structuredDrafts };
      delete structuredDrafts[key];
      const undo = { ...state.undo };
      for (const id of affected) delete undo[id];
      return { ...state, project: candidate, working: nextWorking, structuredDrafts, undo,
        rewriteProposal: null, dirty: true, errors: { ...state.errors, [key]: "" } };
    }
    case "rewriteDiscard": return state.rewriteProposal ? { ...state, rewriteProposal: null } : state;
    case "rewriteApply": {
      const proposal = state.rewriteProposal;
      const block = state.project?.views.find((item) => item.id === action.id);
      if (!proposal || !block || hasUnappliedDraft(state) || proposal.result.blockId !== action.id ||
          state.project?.revision !== proposal.result.baseRevision || block.revision !== proposal.result.blockRevision ||
          block.state.text !== proposal.before || block.state.locked)
        return { ...state, rewriteProposal: null, errors: { ...state.errors, [action.id]: "Предложение устарело. Запросите новое." } };
      const scopedIds = scopedFactsForBlock(state, block).map((fact) => fact.id);
      const next = replaceBlock(state, action.id, (current) => ({ ...current, revision: current.revision + 1,
        status: "ready", dependencyHash: proposal.result.dependencyHash, previous: current.state,
        state: { ...current.state, text: proposal.result.replacementText, origin: "generated",
          factIds: scopedIds,
          factRevisions: Object.fromEntries(scopedIds.map((id) => [id,
            state.project?.facts.find((fact) => fact.id === id)?.revision ?? 1])) } }));
      const issues = proposal.result.issues.map((issue) => `${issue.blockId} · ${issue.factId}: ${issue.message}`);
      return { ...next, rewriteProposal: null, errors: { ...next.errors, [action.id]: "" },
        rewriteIssues: { ...next.rewriteIssues, [action.id]: issues },
        rewriteIssueDetails: { ...next.rewriteIssueDetails, [action.id]: proposal.result.issues } };
    }
    case "reconcile": {
      const block = state.project?.views.find((item) => item.id === action.id);
      if (!block || block.status !== "stale" || state.drafts[action.id] !== undefined &&
          state.drafts[action.id] !== block.state.text || state.selectedId !== action.id ||
          state.project?.projectId !== action.projectId || state.loadId !== action.loadId ||
          state.project?.revision !== action.baseRevision ||
          block.revision !== action.blockRevision || !/^[0-9a-f]{64}$/.test(action.dependencyHash)) return state;
      const scopedIds = scopedFactsForBlock(state, block).map((fact) => fact.id);
      return replaceBlock(state, action.id, (current) => ({ ...current, revision: current.revision + 1,
        status: "ready", dependencyHash: action.dependencyHash, previous: current.state, state: { ...current.state,
          factIds: scopedIds,
          factRevisions: Object.fromEntries(scopedIds.map((id) => [id,
            state.project?.facts.find((fact) => fact.id === id)?.revision ?? 1])) } }));
    }
    case "loadImported":
      if (state.project) return state;
      return { ...initialEditorState, project: action.project, loadId: action.loadId, presentation: action.presentation,
        working: action.working, workingIssues: action.issues, stage: "editor",
        selectedId: action.project.views[0]?.id ?? null, sourceText: state.sourceText, dirty: true };
    case "sourceIntegrity":
      return state.loadId === action.loadId && state.working?.sources === action.sources ?
        { ...state, sourceIntegrity: action.proof } : state;
    case "loadExample": {
      if (state.project) return state;
      const project = syntheticProject();
      return { ...initialEditorState, project, loadId: action.loadId,
        presentation: { name: "Мария Примерова", title: "Engineer", sourceLanguage: "en",
          jobProseBlocks: { job_1: "job_1_prose", job_2: "job_2_prose" } },
        stage: "editor", selectedId: project.views[0]?.id ?? null, sourceText: state.sourceText, dirty: true };
    }
    case "resetProject":
      return { ...initialEditorState, sourceText: state.sourceText,
        dirty: state.sourceText.length > 0 };
    case "stage":
      return action.stage !== "import" && !state.project ? state : { ...state, stage: action.stage };
    case "panel": return { ...state, panel: action.panel };
    case "select":
      return state.project?.views.some((block) => block.id === action.id) ? { ...state, selectedId: action.id } : state;
    case "sourceText": return { ...state, sourceText: action.text, dirty: state.dirty || action.text.length > 0 };
    case "presentationDraft":
      return { ...state, rewriteProposal: null,
        presentationDrafts: { ...state.presentationDrafts, [action.field]: action.text },
        errors: { ...state.errors, [action.field]: "" } };
    case "presentationCancel": {
      const presentationDrafts = { ...state.presentationDrafts };
      delete presentationDrafts[action.field];
      return { ...state, presentationDrafts, errors: { ...state.errors, [action.field]: "" } };
    }
    case "presentationApply": {
      if (!state.project || !state.presentation) return state;
      const value = (state.presentationDrafts[action.field] ?? state.presentation[action.field]).trim();
      if (!value || value.length > (action.field === "name" ? 160 : 240))
        return { ...state, errors: { ...state.errors, [action.field]: "Введите корректное значение." } };
      if (value === state.presentation[action.field]) return editorReducer(state, { type: "presentationCancel", field: action.field });
      const presentationDrafts = { ...state.presentationDrafts };
      delete presentationDrafts[action.field];
      const presentation = { ...state.presentation, [action.field]: value };
      return { ...state, presentationUndo: state.presentation,
        presentation, working: syncWorkingPresentation(state.working, presentation), presentationDrafts,
        project: { ...state.project, revision: state.project.revision + 1 }, dirty: true };
    }
    case "presentationLanguage":
      return !state.project || !state.presentation || state.presentation.sourceLanguage === action.language ? state :
        { ...state, presentationUndo: state.presentation,
          presentation: { ...state.presentation, sourceLanguage: action.language },
          working: syncWorkingPresentation(state.working, { ...state.presentation, sourceLanguage: action.language }),
          project: { ...state.project, revision: state.project.revision + 1 }, dirty: true };
    case "presentationUndo":
      return !state.project || !state.presentationUndo ? state :
        { ...state, presentation: state.presentationUndo, presentationUndo: null,
          working: syncWorkingPresentation(state.working, state.presentationUndo),
          project: { ...state.project, revision: state.project.revision + 1 }, dirty: true };
    case "draft": return { ...state, rewriteProposal: state.rewriteProposal?.result.blockId === action.id ? null : state.rewriteProposal,
      drafts: { ...state.drafts, [action.id]: action.text }, errors: { ...state.errors, [action.id]: "" } };
    case "factDraft": {
      const fact = state.project?.facts.find((item) => item.id === action.id);
      if (!fact || editableFactValue(fact) === null) return state;
      return { ...state, rewriteProposal: null,
        factDrafts: { ...state.factDrafts, [action.id]: action.text }, errors: { ...state.errors, [action.id]: "" } };
    }
    case "cancelFact": {
      const factDrafts = { ...state.factDrafts };
      delete factDrafts[action.id];
      return { ...state, factDrafts, errors: { ...state.errors, [action.id]: "" } };
    }
    case "cancel": {
      const drafts = { ...state.drafts };
      delete drafts[action.id];
      return { ...state, drafts, errors: { ...state.errors, [action.id]: "" } };
    }
    case "apply": {
      const block = state.project?.views.find((item) => item.id === action.id);
      if (!block) return state;
      const text = draftFor(state, block).trim();
      if (!text) return { ...state, errors: { ...state.errors, [action.id]: "Введите текст блока." } };
      if (block.status === "stale" && text === block.state.text)
        return { ...state, errors: { ...state.errors, [action.id]: "Измените текст с учётом исправленного факта." } };
      if (text === block.state.text && block.status !== "stale") return editorReducer(state, { type: "cancel", id: action.id });
      const next = replaceBlock(state, action.id, (current) => {
        const factRevisions = { ...current.state.factRevisions };
        for (const fact of state.project?.facts ?? []) {
          if (current.state.factIds.includes(fact.id)) factRevisions[fact.id] = fact.revision;
        }
        return {
          ...current, revision: current.revision + 1, status: "ready",
          state: { ...current.state, text, origin: "manual", locked: true, factRevisions },
          previous: current.state,
        };
      });
      const drafts = { ...next.drafts };
      delete drafts[action.id];
      return { ...next, drafts, rewriteIssues: { ...next.rewriteIssues, [action.id]: [] },
        rewriteIssueDetails: { ...next.rewriteIssueDetails, [action.id]: [] },
        working: block.kind === "education" && next.working ?
        { ...next.working, manual: { ...next.working.manual, education: text } } : next.working,
        errors: { ...next.errors, [action.id]: "" } };
    }
    case "lock": return replaceBlock(state, action.id, (block) => ({
      ...block, revision: block.revision + 1, previous: block.state,
      state: { ...block.state, locked: !block.state.locked },
    }));
    case "visible": return replaceBlock(state, action.id, (block) => ({
      ...block, revision: block.revision + 1, visible: !block.visible, previous: block.state,
    }));
    case "undo": {
      const project = state.project;
      const checkpoint = state.undo[action.id];
      const block = project?.views.find((item) => item.id === action.id);
      if (!project || !checkpoint || !block) return state;
      const factRevisions = checkpoint.state.factRevisions;
      const dependenciesCurrent = Object.entries(factRevisions).every(([id, revision]) =>
        project.facts.find((fact) => fact.id === id)?.revision === revision);
      const restored: Block = {
        ...block, revision: block.revision + 1,
        state: cloneState(checkpoint.state), visible: checkpoint.visible, dependencyHash: checkpoint.dependencyHash,
        previous: cloneState(block.state),
        status: dependenciesCurrent ? checkpoint.status : "stale",
      };
      const views = project.views.map((item) => item.id === action.id ? restored : item);
      const otherReview: Review = {
        decisions: project.review.decisions.filter((decision) => !(decision.targetKind === "block" && decision.targetId === action.id)),
        acknowledgments: project.review.acknowledgments.filter((ack) => !(ack.targetKind === "block" && ack.targetId === action.id)),
      };
      const review = reviewForCurrent({ ...project, views }, {
        decisions: [...otherReview.decisions, ...(dependenciesCurrent ? checkpoint.review.decisions.map((decision) => ({ ...decision, targetRevision: restored.revision })) : [])],
        acknowledgments: [...otherReview.acknowledgments, ...(dependenciesCurrent ? checkpoint.review.acknowledgments.map((ack) => ({ ...ack, targetRevision: restored.revision })) : [])],
      });
      const undo = { ...state.undo };
      delete undo[action.id];
      let working = checkpoint.manualEducation !== null && state.working ? { ...state.working,
        manual: { ...state.working.manual, education: checkpoint.manualEducation } } : state.working;
      const related = relatedCoverageTargets(state, action.id, checkpoint.state.factIds);
      if (working && checkpoint.coverage && dependenciesCurrent) {
        const restoredProject = { ...project, views, review };
        const input = { project: restoredProject, working, presentation: state.presentation,
          rewriteIssues: { ...state.rewriteIssueDetails, [action.id]: checkpoint.issueDetails },
          sourceIntegrity: state.sourceIntegrity };
        const expectedViews = views.map((item) => item.id === action.id ?
          { ...item, revision: checkpoint.revision } : item);
        const expectedReview = reviewForCurrent({ ...project, views: expectedViews }, {
          decisions: [...otherReview.decisions, ...checkpoint.review.decisions],
          acknowledgments: [...otherReview.acknowledgments, ...checkpoint.review.acknowledgments],
        });
        const expectedInput = { ...input, project: { ...project, views: expectedViews,
          review: expectedReview }, working: { ...working, coverage: checkpoint.coverage } };
        const retained = working.coverage?.decisions.filter((item) =>
          !related.has(`${item.targetKind}:${item.targetId}`)) ?? [];
        const restored = checkpoint.coverage.decisions.filter((item) =>
          related.has(`${item.targetKind}:${item.targetId}`)).flatMap((item) => {
            if (coverageDependency(expectedInput, item.targetKind, item.targetId) !== item.dependency) return [];
            const dependency = coverageDependency(input, item.targetKind, item.targetId);
            return dependency ? [{ ...item, dependency }] : [];
          });
        const candidate = { ...working, coverage: { decisions: [...retained, ...restored],
          acknowledgments: working.coverage?.acknowledgments ?? [] } };
        const active = coverageReview({ ...input, working: candidate });
        const relatedIssues = active.warnings.filter((item) => item.blockId === action.id ||
          item.factId && related.has(`fact:${item.factId}`) ||
          item.sourceId && item.unitId && related.has(`unit:view_${item.sourceId}_${item.unitId}`));
        const relatedIssueIds = new Set(relatedIssues.map((item) => item.id));
        const expectedWarnings = new Map(coverageReview(expectedInput).warnings.map((item) =>
          [item.id, item.dependency]));
        const acknowledgments = candidate.coverage.acknowledgments.filter((item) =>
          !relatedIssueIds.has(item.issueId));
        for (const item of relatedIssues) {
          if (checkpoint.coverage.acknowledgments.some((ack) => ack.issueId === item.id &&
              expectedWarnings.get(ack.issueId) === ack.dependency))
            acknowledgments.push({ issueId: item.id, dependency: item.dependency });
        }
        working = { ...candidate, coverage: { decisions: candidate.coverage.decisions, acknowledgments } };
      }
      return { ...state, dirty: true, undo, rewriteProposal: state.rewriteProposal?.result.blockId === action.id ? null : state.rewriteProposal,
        rewriteIssues: { ...state.rewriteIssues, [action.id]: checkpoint.issues },
        rewriteIssueDetails: { ...state.rewriteIssueDetails, [action.id]: checkpoint.issueDetails },
        working,
        project: { ...project, revision: project.revision + 1, views, review } };
    }
    case "review": {
      const project = state.project;
      const block = project?.views.find((item) => item.id === action.id);
      if (!project || !block || block.status === "stale") return state;
      const previous = project.review.decisions.filter((decision) => !(decision.targetKind === "block" && decision.targetId === action.id));
      const isReviewed = project.review.decisions.some((decision) => decision.targetKind === "block" && decision.targetId === action.id && decision.targetRevision === block.revision);
      return { ...state, dirty: true, project: {
        ...project, revision: project.revision + 1,
        review: { ...project.review, decisions: isReviewed ? previous : [...previous, { targetKind: "block", targetId: action.id, targetRevision: block.revision, disposition: "shown", reason: null }] },
      } };
    }
    case "fact": {
      const project = state.project;
      const fact = project?.facts.find((item) => item.id === action.id);
      if (!project || !fact || factDisplay(fact) === null) return state;
      const value = action.value.trim();
      const sourceCorrection = Boolean(state.working && fact.origin === "source");
      const knownSkill = fact.kind === "technology" ? catalog.entries.find((entry) => entry.canonicalId === value) : undefined;
      if (!value || new TextEncoder().encode(value).length > 4096 || fact.kind === "technology" && !knownSkill ||
          (!sourceCorrection && fact.kind === "metric" && (!/^\d+$/.test(value) || Number(value) > 1000000000
        || (fact.value.upperNumber !== null && Number(value) > fact.value.upperNumber)))) {
        return { ...state, errors: { ...state.errors, [action.id]: "Введите корректное значение факта." } };
      }
      if ((fact.kind === "metric" && Number(value) === fact.value.number) || value === factDisplay(fact) ||
          fact.kind === "technology" && knownSkill?.canonicalId === fact.value.canonicalId) {
        return editorReducer(state, { type: "cancelFact", id: action.id });
      }
      let updated: Fact;
      let working = state.working;
      const oldId = action.id;
      if (working && sourceCorrection) {
        const source = working.sheet.facts.find((item) => item.id === action.id && item.origin === "source");
        if (!source) return state;
        const id = `fact_user_${crypto.randomUUID()}`;
        updated = fact.kind === "technology" && knownSkill ? { id, revision: 1, kind: "technology",
          value: { canonicalId: knownSkill.canonicalId, display: knownSkill.aliases[0] ?? knownSkill.canonicalId,
            scope: fact.value.scope }, evidence: [], origin: "user", importance: source.importance,
          jobId: source.jobId, subprojectId: source.subprojectId } :
          { id, revision: 1, kind: "text", value: { text: value }, evidence: [], origin: "user",
            importance: source.importance, jobId: source.jobId, subprojectId: source.subprojectId };
        working = { ...working, sheet: { ...working.sheet, revision: (working.sheet.revision ?? 1) + 1,
          facts: [...working.sheet.facts, updated],
          userCorrections: { ...working.sheet.userCorrections, [source.id]: id },
          ...(working.sheet.employment ? { employment: working.sheet.employment.map((job) => job.id === source.jobId ?
            { ...job, factIds: [...job.factIds, id] } : job) } : {}) } };
      } else {
        if (fact.kind === "text") updated = { ...fact, revision: fact.revision + 1, value: { text: value } };
        else if (fact.kind === "metric") updated = { ...fact, revision: fact.revision + 1, value: { ...fact.value, number: Number(value) } };
        else if (fact.kind === "technology" && knownSkill) updated = { ...fact, revision: fact.revision + 1,
          value: { ...fact.value, canonicalId: knownSkill.canonicalId, display: knownSkill.aliases[0] ?? knownSkill.canonicalId } };
        else return state;
        if (working) {
          const sheetFact = working.sheet.facts.find((item) => item.id === action.id);
          const manualMetric = working.manual.metrics.find((item) => item.id === action.id);
          if (sheetFact && sheetFact.origin === "user") {
            working = { ...working, sheet: { ...working.sheet, revision: (working.sheet.revision ?? 1) + 1,
              facts: working.sheet.facts.map((item) => item.id === action.id ? updated : item) } };
          } else if (manualMetric && updated.kind === "metric") {
            const number = updated.value.number;
            working = { ...working, manual: { ...working.manual, metrics: working.manual.metrics.map((item) =>
              item.id === action.id ? { ...item, number } : item) } };
          } else if (updated.kind === "text" && action.id.startsWith("fact_user_manual_")) {
            const manualJob = working.manual.employment.find((job) =>
              action.id === `fact_user_manual_job_${job.id}` || job.subprojects.some((sub) =>
                action.id === `fact_user_manual_sub_${sub.id}`));
            if (!manualJob) return state;
            working = { ...working, manual: { ...working.manual, employment: working.manual.employment.map((job) =>
              job.id === manualJob.id ? { ...job,
                description: action.id === `fact_user_manual_job_${job.id}` ? value : job.description,
                subprojects: job.subprojects.map((sub) => action.id === `fact_user_manual_sub_${sub.id}` ?
                  { ...sub, description: value } : sub) } : job) } };
          } else if (updated.kind === "technology" && action.id.startsWith("fact_user_skill_")) {
            const index = Number(action.id.slice("fact_user_skill_".length));
            if (!Number.isInteger(index) || !working.manual.skills[index]) return state;
            const display = updated.value.display;
            working = { ...working, manual: { ...working.manual, skills: working.manual.skills.map((item, at) =>
              at === index ? display : item) } };
          } else return state;
        }
      }
      if (working && !validateFactSheet(working.sheet)) return { ...state,
        errors: { ...state.errors, [action.id]: "Не удалось сохранить исправление в листе фактов." } };
      const facts: Facts = sourceCorrection ? [...project.facts.filter((item) => item.id !== oldId), updated] :
        project.facts.map((item) => item.id === oldId ? updated : item);
      const sources = sourceCorrection ? project.sources.map((source) => ({ ...source, units: source.units.map((unit) =>
        ({ ...unit, representedFactIds: unit.representedFactIds.filter((id) => id !== oldId) })) })) : project.sources;
      const employment = sourceCorrection ? project.employment.map((job) => ({ ...job,
        factIds: job.factIds.map((id) => id === oldId ? updated.id : id),
        subprojects: job.subprojects.map((sub) => ({ ...sub,
          factIds: sub.factIds.map((id) => id === oldId ? updated.id : id) })) })) : project.employment;
      const candidateState: EditorState = { ...state, working, project: { ...project, facts, employment } };
      const affected = project.views.filter((block) => block.state.factIds.includes(oldId) ||
        scopedFactsForBlock(state, block).some((item) => item.id === oldId) ||
        scopedFactsForBlock(candidateState, block).some((item) => item.id === updated.id)).map((block) => block.id);
      const next: Project = {
        ...project, revision: project.revision + 1,
        facts, sources, employment,
        views: project.views.map((block) => affected.includes(block.id) ? { ...block, status: "stale",
          previous: sourceCorrection ? null : block.previous,
          state: sourceCorrection ? { ...block.state,
            factIds: block.state.factIds.includes(oldId) ? block.state.factIds.map((id) => id === oldId ? updated.id : id) :
              [...block.state.factIds, updated.id],
            factRevisions: { ...Object.fromEntries(Object.entries(block.state.factRevisions).filter(([id]) => id !== oldId)),
              [updated.id]: updated.revision } } : block.state } : block),
        review: {
          decisions: project.review.decisions.filter((decision) => !(decision.targetKind === "fact" && decision.targetId === action.id) && !(decision.targetKind === "block" && affected.includes(decision.targetId))),
          acknowledgments: project.review.acknowledgments.filter((ack) => !(ack.targetKind === "fact" && ack.targetId === action.id) && !(ack.targetKind === "block" && affected.includes(ack.targetId))),
        },
      };
      const factDrafts = { ...state.factDrafts };
      delete factDrafts[action.id];
      const undo = { ...state.undo };
      for (const id of affected) delete undo[id];
      const rewriteIssues = { ...state.rewriteIssues };
      for (const id of affected) delete rewriteIssues[id];
      const rewriteIssueDetails = { ...state.rewriteIssueDetails };
      for (const id of affected) delete rewriteIssueDetails[id];
      return { ...state, project: next, working, factDrafts, undo, dirty: true,
        rewriteIssues, rewriteIssueDetails,
        rewriteProposal: affected.includes(state.rewriteProposal?.result.blockId ?? "") ? null : state.rewriteProposal,
        errors: { ...state.errors, [action.id]: "" } };
    }
  }
}

export function editorReducer(state: EditorState, action: Action): EditorState {
  const next = reduceEditorState(state, action);
  if (!next.project || !next.working?.coverage) return next;
  const input = { project: next.project, working: next.working,
    presentation: next.presentation, rewriteIssues: next.rewriteIssueDetails,
    sourceIntegrity: next.sourceIntegrity };
  const decisions = next.working.coverage.decisions.filter((item) =>
    coverageDependency(input, item.targetKind, item.targetId) === item.dependency);
  const review = coverageReview(input);
  const warnings = new Map(review.warnings.map((item) => [item.id, item.dependency]));
  const acknowledgments = next.working.coverage.acknowledgments.filter((item) =>
    warnings.get(item.issueId) === item.dependency);
  if (decisions.length === next.working.coverage.decisions.length &&
      acknowledgments.length === next.working.coverage.acknowledgments.length) return next;
  return { ...next, working: { ...next.working, coverage: { decisions, acknowledgments } } };
}
