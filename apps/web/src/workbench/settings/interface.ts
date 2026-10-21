export type PaneOrder = "layout-first" | "original-first";
const orderKey = "foldcv.workspace.order";

export function readPaneOrder(): PaneOrder {
  try { return localStorage.getItem(orderKey) === "original-first" ? "original-first" : "layout-first"; }
  catch { return "layout-first"; }
}

export function savePaneOrder(order: PaneOrder): void {
  try { localStorage.setItem(orderKey, order); } catch { /* Keep the choice for this opening when storage is unavailable. */ }
}
