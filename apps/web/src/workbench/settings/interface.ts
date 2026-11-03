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

export type TextSize = "normal" | "large" | "x-large";
export type Contrast = "normal" | "high";
/** Settings → Интерфейс → Читаемость (D127): larger interface text and black text on request. The resume page keeps
 * its own scale; the whole window still zooms with the browser or the desktop View menu. */
export type Appearance = { textSize: TextSize; contrast: Contrast };
const textSizeKey = "foldcv.interface.text-size", contrastKey = "foldcv.interface.contrast";
export const textSizes: readonly TextSize[] = ["normal", "large", "x-large"];

export function readAppearance(): Appearance {
  try {
    const size = localStorage.getItem(textSizeKey), contrast = localStorage.getItem(contrastKey);
    return { textSize: size === "large" || size === "x-large" ? size : "normal", contrast: contrast === "high" ? "high" : "normal" };
  } catch { return { textSize: "normal", contrast: "normal" }; }
}

/** The root carries the choice; the stylesheet reads it, so every screen follows at once. */
export function applyAppearance(value: Appearance): void {
  const root = document.documentElement;
  if (value.textSize === "normal") delete root.dataset["uiText"]; else root.dataset["uiText"] = value.textSize;
  if (value.contrast === "normal") delete root.dataset["uiContrast"]; else root.dataset["uiContrast"] = value.contrast;
}

export function saveAppearance(value: Appearance): void {
  applyAppearance(value);
  try { localStorage.setItem(textSizeKey, value.textSize); localStorage.setItem(contrastKey, value.contrast); }
  catch { /* Keep the choice for this opening when storage is unavailable. */ }
}
