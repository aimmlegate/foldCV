import type { RichPanelRequest } from "../contracts/generated/rich_panel_request";
import type { EditorPlanV1, EditorTechnologyTarget } from "../contracts/generated/template_project_response_v1";
import type { PanelCommandV7 } from "./v7-translation";

/** The facts panel's command; the V7 session translates it below. A technology add names the line Python offered. */
export type PanelCommand = Omit<RichPanelRequest, "capture" | "factsRevision" | "documentRevision"> & { lineBlockId?: string };

/** A place Python's editor plan offers for a new technology, with the placement Python checks. */
export type TechnologyTarget = EditorTechnologyTarget;

/** What Python's plan says the panel shows and offers (D113): each job's periods as the document writes them and whether it
 * can take another, the fields with no place in the document, and the technologies that share a line. */
export type PanelPlan = Pick<EditorPlanV1, "jobs" | "unshownFields" | "technologyLines">;

/** What Python's V7 panel path saves (D113); the panel offers nothing else. Adding a technology also needs a target. */
export const panelSupport: { add: ReadonlySet<string>; remove: ReadonlySet<string> } = {
  add: new Set(["employment"]),
  remove: new Set(["employment", "technology", "education", "language"]),
};

const focusOperations: ReadonlySet<PanelCommand["operation"]> = new Set(["add_to_focus", "remove_from_focus", "move_focus"]);
// Records whose fields Python edits outside the employment form.
const editedKinds: ReadonlySet<string> = new Set(["candidate", "technology", "education", "language", "claim"]);

/** The generic panel command as Python's V7 panel path takes it, or null for what it does not save. Changed values the
 * dialog attaches to a period's creation or removal become a preceding edit. */
export function panelCommandsV7(command: PanelCommand, kinds: ReadonlyMap<string, string>): PanelCommandV7[] | null {
  const kind = command.recordId ? kinds.get(command.recordId) : command.recordKind;
  const values = command.values && Object.keys(command.values).length ? structuredClone(command.values) : null;
  if (focusOperations.has(command.operation)) {
    if (kind !== "technology" || !command.recordId || command.jobId || command.periodId || values) return null;
    const focus: PanelCommandV7 = { operation: command.operation, recordId: command.recordId };
    if (command.operation === "move_focus" && command.beforeRecordId) focus.beforeRecordId = command.beforeRecordId;
    return [focus];
  }
  if (command.operation === "set_focus_icon") {
    // One of the template's icons, or "" for the template's own choice (D122).
    const icon = values?.["icon"];
    if (kind !== "technology" || !command.recordId || command.jobId || command.periodId || icon === undefined
      || Object.keys(values ?? {}).length !== 1) return null;
    return [{ operation: "set_focus_icon", recordId: command.recordId, values: { icon } }];
  }
  if (command.operation === "move_technology") {
    if (kind !== "technology" || !command.recordId || command.jobId || command.periodId || values) return null;
    const move: PanelCommandV7 = { operation: "move_technology", recordId: command.recordId };
    if (command.beforeRecordId) move.beforeRecordId = command.beforeRecordId;
    return [move];
  }
  if (kind === "technology" && !command.recordId && command.operation === "add") {
    const display = values?.["display"];
    if (display === undefined || Object.keys(values ?? {}).length !== 1 || command.periodId) return null;
    return [{ operation: "add", recordKind: "technology", jobId: command.jobId ?? null, values: { display } }];
  }
  if (kind === "technology" && !command.recordId && command.operation === "clear_technologies") {
    if (command.periodId || values) return null;
    return [{ operation: "clear_technologies", recordKind: "technology", jobId: command.jobId ?? null, recordId: null, periodId: null,
      values: {} }];
  }
  if (kind !== undefined && kind !== null && editedKinds.has(kind)) {
    if (!command.recordId || command.jobId || command.periodId) return null;
    if (command.operation === "edit") return values ? [{ operation: "edit", recordId: command.recordId, values }] : null;
    return command.operation === "remove" && panelSupport.remove.has(kind) && !values ? [{ operation: "remove", recordId: command.recordId }] : null;
  }
  if (kind !== "employment" || command.jobId) return null;
  const recordId = command.recordId;
  const edit: PanelCommandV7[] = recordId && values ? [{ operation: "edit", recordId, values }] : [];
  switch (command.operation) {
    case "add": return recordId ? null : [{ operation: "add", recordKind: "employment", ...(values ? { values } : {}) }];
    case "edit": return edit.length ? edit : null;
    case "remove": return recordId && !command.periodId ? [{ operation: "remove", recordId }] : null;
    case "remove_period": return recordId && command.periodId ? [...edit, { operation: "remove_period", recordId, periodId: command.periodId }] : null;
    case "add_period": return recordId ? [...edit, { operation: "add_period", recordId, values: {} }] : null;
    default: return null;
  }
}
