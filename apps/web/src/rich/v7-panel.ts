import type { PanelCommand } from "./synchronization";
import type { PanelCommandV7 } from "./v7-translation";

/** The shared facts panel speaks the V1 command. Python's V7 panel path accepts employment commands only, and refuses
 * values on period creation/removal, so changed values the dialog attaches there become a preceding edit. */
export function employmentPanelCommands(command: PanelCommand, kinds: ReadonlyMap<string, string>): PanelCommandV7[] | null {
  const kind = command.recordId ? kinds.get(command.recordId) : command.recordKind;
  if (kind !== "employment" || command.jobId) return null;
  const values = command.values && Object.keys(command.values).length ? structuredClone(command.values) : null;
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
