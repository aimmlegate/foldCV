import { hasUnappliedDraft } from "../editor/state";
import type { EditorState } from "../editor/state";
import { coverageReview } from "../editor/coverage";
import type { CoverageIssue, CoverageReadiness } from "../editor/coverage";

export type ExportReadiness = { allowed: boolean; review: CoverageReadiness | null;
  blockers: CoverageIssue[]; unacknowledged: CoverageIssue[]; pendingInput: boolean };

export function exportReadiness(state: EditorState): ExportReadiness {
  const review = state.project ? coverageReview({ project: state.project, working: state.working,
    presentation: state.presentation, rewriteIssues: state.rewriteIssueDetails,
    sourceIntegrity: state.sourceIntegrity,
    standaloneAcknowledgments: state.standaloneAcknowledgments,
    standaloneDecisions: state.standaloneDecisions }) : null;
  const pendingInput = hasUnappliedDraft(state) || state.rewriteProposal !== null;
  const blockers = review?.blockers ?? [];
  const unacknowledged = review?.warnings.filter((issue) => !issue.acknowledged) ?? [];
  return { allowed: Boolean(review && state.presentation && !pendingInput &&
    blockers.length === 0 && unacknowledged.length === 0),
    review, blockers, unacknowledged, pendingInput };
}
