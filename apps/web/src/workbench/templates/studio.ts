import type { TemplateCatalog, TemplateEntry } from "../../projects/api";
import type { TemplateConfigState } from "./config";

/** What the editor shows: a saved template, or a new one that exists only here until «Сохранить». */
export type ShownTemplate = { kind: "saved"; state: TemplateConfigState } | { kind: "draft"; name: string; assetsFrom: string | null };

export function templateKind(entry: Pick<TemplateEntry, "bundled" | "edited">): string {
  return !entry.bundled ? "свой" : entry.edited ? "изменён" : "встроенный";
}
export function draftLabel(name: string): string { return `${name} (не сохранён)`; }

/** The list's two groups, each in the catalog's order; a new unsaved template shows at the end of the own ones. */
export function groupedCatalog(catalog: TemplateCatalog): { bundled: TemplateEntry[]; own: TemplateEntry[] } {
  return { bundled: catalog.templates.filter(entry => entry.bundled), own: catalog.templates.filter(entry => !entry.bundled) };
}
/** A row's second line: the version, then an edited shipped template, then the default. The group says the rest. */
export function rowNote(entry: Pick<TemplateEntry, "id" | "revision" | "bundled" | "edited">, defaultId: string): string {
  return [entry.revision, entry.bundled && entry.edited ? "изменён" : null, entry.id === defaultId ? "основной" : null].filter(Boolean).join(" · ");
}

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

export type MenuAction = "copy" | "branding" | "default" | "download" | "reset" | "delete";
export type MenuChoice = "hidden" | "disabled" | "enabled";
/** The «⋯» menu of the shown template: a new one can only be downloaded until it is saved; shipped templates keep
 * their file, so they offer the reset once edited instead of the delete. */
export function menuActions(shown: ShownTemplate | null, defaultId: string | null): Record<MenuAction, MenuChoice> {
  const none: Record<MenuAction, MenuChoice> = { copy: "hidden", branding: "hidden", default: "hidden", download: "hidden", reset: "hidden", delete: "hidden" };
  if (!shown) return none;
  if (shown.kind === "draft") return { ...none, download: "enabled" };
  const { package: { id }, bundled, edited } = shown.state;
  return { copy: "enabled", branding: "enabled", default: id === defaultId ? "hidden" : "enabled", download: "enabled",
    reset: bundled && edited ? "enabled" : "hidden", delete: deleteControl({ id, bundled }, defaultId ?? "") };
}
