import type { CSSProperties } from "react";
import type { Node } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";

type Presentation = NonNullable<TemplateProjectResponseV1["presentation"]>;
type Asset = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>["templatePackage"]["assets"][number];

export const presentationMeta = "foldcv-v7-presentation";

/** What the mounted editor draws: Python's plan, the captured recipe and blob URLs of verified captured bytes. */
export type TemplateSheet = { css: string; variables: CSSProperties; logo: { url: string; style: CSSProperties } | null;
  presentation: Presentation; styles: ReadonlyMap<string, string>; icons: ReadonlyMap<string, string> };

/** Captured fonts and icons load once by hash and stay cached; replies carry only their names (D104). */
export function assetUrl(asset: Pick<Asset, "sha256">): string {
  return `/v1/rich/template-assets/${asset.sha256}`;
}

const pt = (value: number): string => `${value}pt`;

/** The sheet's column geometry. A layout without a sidebar is one column: the regions stack in reading order and the
 * empty sidebar offers no "add text" button. */
export function sheetColumns(regions: readonly Presentation["recipe"]["layout"]["regions"][number][]): Readonly<Record<string, string>> | null {
  const byId = new Map(regions.map(region => [region.id, region]));
  const header = byId.get("header"), sidebar = byId.get("sidebar"), main = byId.get("main");
  if (!header || !main) return null;
  const left = sidebar?.x ?? main.x;
  return { "--fcv-left": pt(left), "--fcv-header-left": pt(header.x - left), "--fcv-header-width": pt(header.width),
    "--fcv-columns": sidebar ? `${pt(sidebar.width)} ${pt(main.width)}` : pt(main.width),
    "--fcv-gap": pt(sidebar ? main.x - sidebar.x - sidebar.width : 0),
    "--fcv-main-column": sidebar ? "2" : "1", "--fcv-main-row": sidebar ? "2" : "3", "--fcv-sidebar-empty": sidebar ? "block" : "none" };
}

/** Faces, sizes and colors come from the plan; geometry from the compiled recipe. Nothing is read from wording or IDs. */
export function templateSheet(response: TemplateProjectResponseV1): TemplateSheet | null {
  const presentation = response.presentation, project = response.workspace.project, plan = presentation?.editor;
  if (!presentation || !project || !plan) return null;
  const assets = new Map(project.templatePackage.assets.map(asset => [asset.id, asset]));
  const family = (id: string | null): string | null => {
    const asset = id === null ? undefined : assets.get(id);
    return asset ? `"fcv-${asset.sha256.slice(0, 24)}"` : null;
  };
  // An italic face is declared as one: the browser then slants only the upright face that stands in for letters it lacks.
  const italics = new Set(Object.values(plan.styles).flatMap(style => [style.faces.italic, style.faces.boldItalic]));
  const rules = plan.fonts.flatMap(id => {
    const asset = assets.get(id), slant = italics.has(id) ? " font-style: italic;" : "";
    return asset ? [`@font-face { font-family: ${family(id) ?? ""};${slant} src: url("${assetUrl(asset)}") format("truetype"); font-display: block; }`] : [];
  });
  const styles = new Map<string, string>();
  Object.entries(plan.styles).forEach(([key, style], index) => {
    const name = `s${String(index)}`, regular = family(style.faces.regular) ?? "inherit";
    styles.set(key, name);
    // Each styled element sets its own faces; marks inside it read the nearest ones. A missing face keeps the regular one.
    const face = (id: string | null) => family(id) ?? regular;
    rules.push(`.fcv-sheet [data-fcv-style="${name}"] { --fcv-regular: ${regular}; --fcv-bold: ${face(style.faces.bold)};`
      + ` --fcv-italic: ${face(style.faces.italic)}; --fcv-bold-italic: ${face(style.faces.boldItalic)};`
      + ` font-family: var(--fcv-regular), sans-serif; font-size: ${pt(style.size)}; line-height: ${pt(style.lineHeight)};`
      + ` color: ${style.color};${style.alignment ? ` text-align: ${style.alignment};` : ""} }`);
  });
  // A packed icon has no asset entry; the plan names its PNG by hash.
  const icons = new Map(plan.icons.flatMap(id => {
    const sha256 = plan.iconFiles?.[id] ?? assets.get(id)?.sha256;
    return sha256 ? [[id, assetUrl({ sha256 })] as const] : [];
  }));
  const recipe = presentation.recipe, style = recipe.style, columns = sheetColumns(recipe.layout.regions);
  const header = recipe.layout.regions.find(region => region.id === "header");
  if (!header || !columns) return null;
  const band = style.section_band, focus = style.focus, divider = style.header.divider, logoValue = style.header.logo;
  const variables = {
    "--fcv-page-width": pt(style.page.width), "--fcv-top": pt(style.header.name_top), ...columns,
    "--fcv-header-height": pt((divider?.y ?? style.page.first_body_top) - style.header.name_top),
    "--fcv-body-gap": pt(style.page.first_body_top - (divider?.y ?? style.page.first_body_top)),
    "--fcv-divider-left": pt((divider?.x1 ?? header.x) - header.x), "--fcv-divider-width": pt(divider ? divider.x2 - divider.x1 : 0),
    "--fcv-divider": divider ? `${pt(divider.width)} solid ${style.colors[divider.color] ?? "transparent"}` : "0",
    "--fcv-band-height": pt(band.height), "--fcv-band-inset": pt(band.text_inset), "--fcv-band-color": style.colors[band.background] ?? "transparent",
    "--fcv-focus-text": pt(focus.text_x), "--fcv-focus-icon-x": pt(focus.icon_x), "--fcv-focus-icon-width": pt(focus.icon_width),
    "--fcv-focus-icon-height": pt(focus.icon_height), "--fcv-focus-row": pt(focus.minimum_row_height),
    // The template's bullet glyph, as the DOCX numbering uses it (CT08: a second template draws "–").
    "--fcv-bullet": JSON.stringify(style.bullets.marker),
  } as CSSProperties;
  const logoAsset = logoValue ? assets.get(logoValue.asset) : undefined;
  const logo = logoValue && logoAsset ? { url: assetUrl(logoAsset), style: { left: pt(logoValue.x), top: pt(logoValue.top),
    width: pt(logoValue.width), height: pt(logoValue.height) } } : null;
  return { css: rules.join("\n"), variables, logo, presentation, styles, icons };
}

/** Literal spans have no binding id. The plan stores them as `literal@start@end` in UTF-16 units. */
export function literalRuns(inline: Readonly<Record<string, string>> | undefined): { start: number; end: number; style: string }[] {
  const runs: { start: number; end: number; style: string }[] = [];
  for (const [key, style] of Object.entries(inline ?? {})) {
    const match = /^literal@(\d+)@(\d+)$/.exec(key);
    if (!match || !style) continue;
    const start = Number(match[1]), end = Number(match[2]);
    if (!Number.isInteger(start) || !Number.isInteger(end) || end <= start) continue;
    runs.push({ start, end, style });
  }
  return runs.sort((left, right) => left.start - right.start || left.end - right.end);
}

function paintLiterals(content: Node, origin: number, runs: readonly { start: number; end: number; style: string }[],
  styleName: (key: string) => string, decorations: Decoration[]): void {
  if (!runs.length) return;
  let offset = 0;
  content.descendants((child, pos) => {
    const length = child.isText ? (child.text?.length ?? 0) : child.type.name === "hardBreak" ? 1 : 0;
    if (!length) return true;
    const from = offset, to = offset + length;
    for (const run of runs) {
      const start = Math.max(run.start, from), end = Math.min(run.end, to);
      if (start >= end) continue;
      const name = styleName(run.style);
      if (!name) continue;
      decorations.push(Decoration.inline(origin + pos + (start - from), origin + pos + (end - from), { "data-fcv-style": name }));
    }
    offset = to;
    return false;
  });
}

/** Node decorations that apply the plan to canonical block IDs; a block without a plan entry keeps the sheet defaults. */
export function templatePresentationPlugin(current: () => TemplateSheet | null): Plugin {
  return new Plugin({ key: new PluginKey(presentationMeta), props: { decorations: state => {
    const sheet = current();
    if (!sheet) return DecorationSet.empty;
    const plan = sheet.presentation.editor, refs = sheet.presentation.blocks, views = sheet.presentation.recipe.views;
    if (!plan) return DecorationSet.empty;
    const decorations: Decoration[] = [];
    const rows = new Set(Object.values(plan.blocks).flatMap(entry => entry.focus?.blocks ?? []));
    state.doc.descendants((node, position) => {
      if (node.type.name === "blockGroup" && position === 0) {
        decorations.push(Decoration.node(position, position + node.nodeSize, { class: "fcv-regions" }));
        return;
      }
      if (node.type.name !== "blockContainer" || !node.firstChild) return;
      const content = node.firstChild, id: unknown = node.attrs["id"];
      if (content.type.name === "region") {
        const role: unknown = content.attrs["role"];
        decorations.push(Decoration.node(position, position + node.nodeSize, { class: `fcv-region fcv-region-${String(role)}` }));
        return;
      }
      const entry = typeof id === "string" ? plan.blocks[id] : undefined, ref = typeof id === "string" ? refs[id] : undefined;
      if (!entry || !ref) return;
      const view = views[ref.viewKey], attributes: Record<string, string> = { "data-fcv-style": sheet.styles.get(entry.style) ?? "" };
      const properties: string[] = [];
      if (entry.band) attributes["data-fcv-band"] = "true";
      else if (view && content.type.name !== "section") {
        attributes["data-fcv-inset"] = "true";
        properties.push(`--fcv-inset: ${pt(view.inset + (rows.has(String(id)) ? sheet.presentation.recipe.style.focus.text_x : 0))}`);
      }
      if (content.type.name === "section" && content.childCount === 0) attributes["data-fcv-item"] = "true";
      if (content.type.name === "section" && view && node.childCount > 1) {
        attributes["data-fcv-gap"] = "true";
        properties.push(`--fcv-item-gap: ${pt(view.item_gap)}`);
      }
      if (entry.focus) {
        attributes["data-fcv-focus"] = "true";
        const icon = entry.focus.icon ? sheet.icons.get(entry.focus.icon) : undefined;
        if (icon) properties.push(`--fcv-icon: url("${icon}")`);
      }
      if (properties.length) attributes["style"] = properties.join("; ");
      decorations.push(Decoration.node(position, position + node.nodeSize, attributes));
      // Inline spans that keep another style, technology chips, and links. A technical link is a BlockNote link, not a bound link.
      const runs = literalRuns(entry.inline);
      content.descendants((child, offset) => {
        const at = position + 2 + offset, name = child.type.name;
        const identity: unknown = name === "templateField" ? child.attrs["bindingId"] : name === "manualScope" ? child.attrs["fragmentId"] : null;
        const key = typeof identity === "string" ? entry.inline?.[identity] : undefined;
        const chip = typeof identity === "string" ? entry.chips?.[identity] : undefined;
        const inline: Record<string, string> = {};
        if (key) inline["data-fcv-style"] = sheet.styles.get(key) ?? "";
        if (chip) Object.assign(inline, { "data-fcv-chip": "true", style: `--fcv-chip: ${chip}` });
        if (key || chip) decorations.push(Decoration.node(at, at + child.nodeSize, inline));
        if (name === "link" || (name === "boundLink" && entry.links?.includes(String(child.attrs["occurrenceId"]))))
          decorations.push(Decoration.node(at, at + child.nodeSize, { class: "fcv-link" }));
      });
      paintLiterals(content, position + 2, runs, key => sheet.styles.get(key) ?? "", decorations);
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
