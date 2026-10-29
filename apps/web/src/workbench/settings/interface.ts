export type PaneOrder = "layout-first" | "original-first";
const orderKey = "foldcv.workspace.order";

export function readPaneOrder(): PaneOrder {
  try { return localStorage.getItem(orderKey) === "original-first" ? "original-first" : "layout-first"; }
  catch { return "layout-first"; }
}

export function savePaneOrder(order: PaneOrder): void {
  try { localStorage.setItem(orderKey, order); } catch { /* Keep the choice for this opening when storage is unavailable. */ }
}

const remarksKey = "foldcv.editor.remark-marks";

/** Whether the editor marks remarks in the resume text; on until turned off. */
export function readRemarkMarks(): boolean {
  try { return localStorage.getItem(remarksKey) !== "off"; }
  catch { return true; }
}

export function saveRemarkMarks(on: boolean): void {
  try { localStorage.setItem(remarksKey, on ? "on" : "off"); } catch { /* Keep the choice for this opening when storage is unavailable. */ }
}
