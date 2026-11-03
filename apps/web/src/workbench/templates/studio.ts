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
