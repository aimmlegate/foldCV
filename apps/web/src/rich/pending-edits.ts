import type { RichCompletionRequest } from "../contracts/generated/rich_completion_request";

export type PendingEdit = {
  blocks: Set<string>; moved: Set<string>; removedRecords: Set<string>;
  removedFields: Map<string, RichCompletionRequest["removedFields"][number]>;
};

export class PendingEdits {
  private readonly actions = new Map<string, PendingEdit>();
  get empty(): boolean { return this.actions.size === 0; }
  forAction(actionId: string): PendingEdit {
    let edit = this.actions.get(actionId);
    if (!edit) {
      edit = { blocks: new Set(), moved: new Set(), removedRecords: new Set(), removedFields: new Map() };
      this.actions.set(actionId, edit);
    }
    return edit;
  }
  take(): [string, PendingEdit][] {
    const edits = [...this.actions];
    this.actions.clear();
    return edits;
  }
}
