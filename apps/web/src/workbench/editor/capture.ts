import type { CapturedEditorSelection } from "../../rich/Editor";
import type { SessionHistory } from "../../rich/history";

export function capturedSelectionCurrent(capture: CapturedEditorSelection | null, history: Pick<SessionHistory, "revision"> | null, session: string): boolean {
  return capture !== null && history !== null && capture.session === session
    && [...capture.epochs].every(([key, revision]) => history.revision(key) === revision);
}
