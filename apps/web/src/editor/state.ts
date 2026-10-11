import type { Block, BlockState, Facts, Project, Review } from "../contracts/generated/project";
import { syntheticProject } from "./example";
import type { Presentation } from "../contracts/generated/prepare_request";
import type { WorkingDraft } from "../facts/working";
import { validateFactSheet } from "../contracts/validate";

type Fact = Facts[number];

export type Stage = "import" | "editor" | "export";
export type Panel = "preview" | "sources" | "checks";
type Drafts = Record<string, string>;
type Checkpoint = { state: BlockState; visible: boolean; status: Block["status"]; review: Review };
export type EditorState = {
  project: Project | null;
  working: WorkingDraft | null;
  workingIssues: string[];
  presentation: Presentation | null;
  presentationDrafts: { name?: string; title?: string };
  presentationUndo: Presentation | null;
  stage: Stage;
  panel: Panel;
  selectedId: string | null;
  drafts: Drafts;
  factDrafts: Drafts;
  errors: Drafts;
  undo: Record<string, Checkpoint>;
  sourceText: string;
  dirty: boolean;
};
export type Action =
  | { type: "loadExample" }
  | { type: "loadImported"; project: Project; presentation: Presentation; working: WorkingDraft; issues: string[] }
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
  | { type: "fact"; id: string; value: string };

export const initialEditorState: EditorState = {
  project: null, working: null, workingIssues: [], presentation: null, presentationDrafts: {}, presentationUndo: null,
  stage: "import", panel: "preview", selectedId: null,
  drafts: {}, factDrafts: {}, errors: {}, undo: {}, sourceText: "", dirty: false,
};

export function selectedBlock(state: EditorState): Block | undefined {
  return state.project?.views.find((block) => block.id === state.selectedId);
}

export function draftFor(state: EditorState, block: Block): string {
  return state.drafts[block.id] ?? block.state.text;
}

export function hasUnappliedDraft(state: EditorState): boolean {
  return Boolean(state.project && (Object.entries(state.presentationDrafts).some(([field, text]) =>
      text !== state.presentation?.[field as "name" | "title"])
    || state.project.views.some((block) => draftFor(state, block) !== block.state.text)
    || state.project.facts.some((fact) => state.factDrafts[fact.id] !== undefined && state.factDrafts[fact.id] !== factDisplay(fact))));
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

function replaceBlock(state: EditorState, id: string, update: (block: Block) => Block): EditorState {
  const project = state.project;
  const block = project?.views.find((item) => item.id === id);
  if (!project || !block) return state;
  const checkpoint: Checkpoint = {
    state: block.state, visible: block.visible, status: block.status,
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

function factDisplay(fact: Fact): string | null {
  if (fact.kind === "text") return fact.value.text;
  if (fact.kind === "metric") return String(fact.value.number);
  return null;
}

export function editableFactValue(fact: Fact): string | null { return factDisplay(fact); }

export function editorReducer(state: EditorState, action: Action): EditorState {
  switch (action.type) {
    case "loadImported":
      if (state.project) return state;
      return { ...initialEditorState, project: action.project, presentation: action.presentation,
        working: action.working, workingIssues: action.issues, stage: "editor",
        selectedId: action.project.views[0]?.id ?? null, sourceText: state.sourceText, dirty: true };
    case "loadExample": {
      if (state.project) return state;
      const project = syntheticProject();
      return { ...initialEditorState, project,
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
      return { ...state, presentationDrafts: { ...state.presentationDrafts, [action.field]: action.text },
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
      return { ...state, presentationUndo: state.presentation,
        presentation: { ...state.presentation, [action.field]: value }, presentationDrafts,
        project: { ...state.project, revision: state.project.revision + 1 }, dirty: true };
    }
    case "presentationLanguage":
      return !state.project || !state.presentation || state.presentation.sourceLanguage === action.language ? state :
        { ...state, presentationUndo: state.presentation,
          presentation: { ...state.presentation, sourceLanguage: action.language },
          project: { ...state.project, revision: state.project.revision + 1 }, dirty: true };
    case "presentationUndo":
      return !state.project || !state.presentationUndo ? state :
        { ...state, presentation: state.presentationUndo, presentationUndo: null,
          project: { ...state.project, revision: state.project.revision + 1 }, dirty: true };
    case "draft": return { ...state, drafts: { ...state.drafts, [action.id]: action.text }, errors: { ...state.errors, [action.id]: "" } };
    case "factDraft": {
      const fact = state.project?.facts.find((item) => item.id === action.id);
      if (!fact || editableFactValue(fact) === null) return state;
      return { ...state, factDrafts: { ...state.factDrafts, [action.id]: action.text }, errors: { ...state.errors, [action.id]: "" } };
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
      return { ...next, drafts, errors: { ...next.errors, [action.id]: "" } };
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
        state: cloneState(checkpoint.state), visible: checkpoint.visible,
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
      return { ...state, dirty: true, undo, project: { ...project, revision: project.revision + 1, views, review } };
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
      if (!value || new TextEncoder().encode(value).length > 4096 || (!sourceCorrection && fact.kind === "metric" && (!/^\d+$/.test(value) || Number(value) > 1000000000
        || (fact.value.upperNumber !== null && Number(value) > fact.value.upperNumber)))) {
        return { ...state, errors: { ...state.errors, [action.id]: "Введите корректное значение факта." } };
      }
      if ((fact.kind === "metric" && Number(value) === fact.value.number) || value === factDisplay(fact)) {
        return editorReducer(state, { type: "cancelFact", id: action.id });
      }
      let updated: Fact;
      let working = state.working;
      const oldId = action.id;
      if (working && sourceCorrection) {
        const source = working.sheet.facts.find((item) => item.id === action.id && item.origin === "source");
        if (!source) return state;
        const id = `fact_user_${crypto.randomUUID()}`;
        updated = { id, revision: 1, kind: "text", value: { text: value }, evidence: [], origin: "user",
          importance: source.importance, jobId: source.jobId, subprojectId: source.subprojectId };
        working = { ...working, sheet: { ...working.sheet, revision: (working.sheet.revision ?? 1) + 1,
          facts: [...working.sheet.facts, updated],
          userCorrections: { ...working.sheet.userCorrections, [source.id]: id },
          ...(working.sheet.employment ? { employment: working.sheet.employment.map((job) => job.id === source.jobId ?
            { ...job, factIds: [...job.factIds, id] } : job) } : {}) } };
      } else {
        if (fact.kind === "text") updated = { ...fact, revision: fact.revision + 1, value: { text: value } };
        else if (fact.kind === "metric") updated = { ...fact, revision: fact.revision + 1, value: { ...fact.value, number: Number(value) } };
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
          } else return state;
        }
      }
      if (working && !validateFactSheet(working.sheet)) return { ...state,
        errors: { ...state.errors, [action.id]: "Не удалось сохранить исправление в листе фактов." } };
      const affected = project.views.filter((block) => block.state.factIds.includes(action.id)).map((block) => block.id);
      const next: Project = {
        ...project, revision: project.revision + 1,
        facts: sourceCorrection ? [...project.facts.filter((item) => item.id !== action.id), updated] :
          project.facts.map((item) => item.id === action.id ? updated : item),
        sources: sourceCorrection ? project.sources.map((source) => ({ ...source, units: source.units.map((unit) =>
          ({ ...unit, representedFactIds: unit.representedFactIds.filter((id) => id !== oldId) })) })) : project.sources,
        employment: sourceCorrection ? project.employment.map((job) => ({ ...job,
          factIds: job.factIds.map((id) => id === oldId ? updated.id : id),
          subprojects: job.subprojects.map((sub) => ({ ...sub,
            factIds: sub.factIds.map((id) => id === oldId ? updated.id : id) })) })) : project.employment,
        views: project.views.map((block) => affected.includes(block.id) ? { ...block, status: "stale",
          previous: sourceCorrection ? null : block.previous,
          state: sourceCorrection ? { ...block.state,
            factIds: block.state.factIds.map((id) => id === oldId ? updated.id : id),
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
      return { ...state, project: next, working, factDrafts, undo, dirty: true,
        errors: { ...state.errors, [action.id]: "" } };
    }
  }
}
