import type { TemplateEntry } from "../../projects/api";
import type { TemplateConfigState } from "./config";

/** What the editor shows: a saved template, or a new one that exists only here until «Сохранить». */
export type ShownTemplate = { kind: "saved"; state: TemplateConfigState } | { kind: "draft"; name: string; assetsFrom: string | null };

export function templateKind(entry: Pick<TemplateEntry, "bundled" | "edited">): string {
  return !entry.bundled ? "свой" : entry.edited ? "изменён" : "встроенный";
}
export function draftLabel(name: string): string { return `${name} (не сохранён)`; }

/** The saved id the editor shows; null for a new template. */
export function shownId(shown: ShownTemplate | null): string | null {
  return shown?.kind === "saved" ? shown.state.package.id : null;
}
/** A new template is unsaved by definition; a saved one once its text differs. */
export function unsaved(shown: ShownTemplate | null, text: string): boolean {
  return shown !== null && (shown.kind === "draft" || text !== shown.state.text);
}

/** Shipped templates cannot be deleted, so the button is hidden; the default one must be replaced as default first. */
export function deleteControl(entry: Pick<TemplateEntry, "id" | "bundled">, defaultId: string): "hidden" | "disabled" | "enabled" {
  return entry.bundled ? "hidden" : entry.id === defaultId ? "disabled" : "enabled";
}
/** The download name of the editor text; a new template has no id until it is saved. */
export function downloadName(shown: ShownTemplate | null): string {
  return `${shownId(shown) ?? "template"}.yaml`;
}
