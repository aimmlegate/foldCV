import { contrastLimits, defaultTheme, palette, themeById, type Mode, type ThemeId } from "./themes";

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
export type Scheme = "system" | "light" | "dark";
/** Settings → Интерфейс (D127 text size, D140 themes): the scheme follows the system or is fixed, each side has its own
 * theme, contrast scales every color's distance from the paper, glass is the opacity of floating panels. The resume
 * page keeps its own look and scale. */
export type Appearance = { textSize: TextSize; scheme: Scheme; lightTheme: ThemeId; darkTheme: ThemeId; contrast: number; glass: number };
export const textSizes: readonly TextSize[] = ["normal", "large", "x-large"];
export const schemes: readonly Scheme[] = ["system", "light", "dark"];
export const contrastRange = { ...contrastLimits, step: 5, initial: 100 } as const;
export const glassRange = { minimum: 50, maximum: 100, step: 5, initial: 95 } as const;
export const initialAppearance: Appearance = { textSize: "normal", scheme: "system", lightTheme: defaultTheme, darkTheme: defaultTheme,
  contrast: contrastRange.initial, glass: glassRange.initial };
const keys = { textSize: "foldcv.interface.text-size", contrast: "foldcv.interface.contrast", glass: "foldcv.interface.glass",
  scheme: "foldcv.interface.scheme", lightTheme: "foldcv.interface.theme-light", darkTheme: "foldcv.interface.theme-dark" } as const;

function readPercent(raw: string | null, range: { minimum: number; maximum: number }): number | null {
  if (raw === null || !/^\d{1,3}$/.test(raw)) return null;
  const value = Number(raw);
  return value >= range.minimum && value <= range.maximum ? value : null;
}

export function readAppearance(): Appearance {
  try {
    const size = localStorage.getItem(keys.textSize), contrast = localStorage.getItem(keys.contrast), scheme = localStorage.getItem(keys.scheme);
    return { textSize: size === "large" || size === "x-large" ? size : "normal",
      scheme: scheme === "light" || scheme === "dark" ? scheme : "system",
      lightTheme: themeById(localStorage.getItem(keys.lightTheme))?.id ?? defaultTheme,
      darkTheme: themeById(localStorage.getItem(keys.darkTheme))?.id ?? defaultTheme,
      // D127 stored «high» for black text; the slider carries that strength on.
      contrast: contrast === "high" ? 130 : readPercent(contrast, contrastRange) ?? contrastRange.initial,
      glass: readPercent(localStorage.getItem(keys.glass), glassRange) ?? glassRange.initial };
  } catch { return initialAppearance; }
}

export function resolveMode(scheme: Scheme, systemDark: boolean): Mode { return scheme === "system" ? (systemDark ? "dark" : "light") : scheme; }
export function prefersDark(): boolean { return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches; }
/** What applyAppearance writes to: the document root, or a stand-in in tests. */
export type AppearanceRoot = { dataset: Partial<Record<string, string>>; style: { colorScheme: string; setProperty(name: string, value: string): void } };
/** Sent on the root after every application, with the resolved mode as detail; Monaco follows it. */
export const appearanceEvent = "foldcv:appearance";

/** The root carries the choices and the palette; the stylesheets read them, so every screen follows at once. */
export function applyAppearance(value: Appearance, root: AppearanceRoot = document.documentElement, systemDark = prefersDark()): Mode {
  const mode = resolveMode(value.scheme, systemDark), theme = mode === "dark" ? value.darkTheme : value.lightTheme;
  if (value.textSize === "normal") delete root.dataset["uiText"]; else root.dataset["uiText"] = value.textSize;
  // The D127 rules for firm controls and dark captions stay for a strong contrast.
  if (value.contrast >= 120) root.dataset["uiContrast"] = "high"; else delete root.dataset["uiContrast"];
  root.dataset["mode"] = mode; root.dataset["theme"] = theme;
  for (const [token, color] of Object.entries(palette(theme, mode, value.contrast))) root.style.setProperty(`--${token}`, color);
  root.style.setProperty("--glass", String(value.glass / 100));
  root.style.colorScheme = mode;
  if (root instanceof EventTarget) root.dispatchEvent(new CustomEvent(appearanceEvent, { detail: mode }));
  return mode;
}

export function saveAppearance(value: Appearance): void { applyAppearance(value); storeAppearance(value); }

export function storeAppearance(value: Appearance): void {
  try {
    localStorage.setItem(keys.textSize, value.textSize); localStorage.setItem(keys.scheme, value.scheme);
    localStorage.setItem(keys.lightTheme, value.lightTheme); localStorage.setItem(keys.darkTheme, value.darkTheme);
    localStorage.setItem(keys.contrast, String(value.contrast)); localStorage.setItem(keys.glass, String(value.glass));
  } catch { /* Keep the choice for this opening when storage is unavailable. */ }
}

/** Re-applies the saved appearance when the system scheme changes and the choice follows the system. */
export function watchSystemScheme(current: () => Appearance): () => void {
  if (typeof matchMedia !== "function") return () => {};
  const query = matchMedia("(prefers-color-scheme: dark)");
  const follow = () => { const value = current(); if (value.scheme === "system") applyAppearance(value, document.documentElement, query.matches); };
  query.addEventListener("change", follow);
  return () => query.removeEventListener("change", follow);
}
