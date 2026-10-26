import type { CSSProperties } from "react";
import type { Node } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { BlockNotice } from "./import-notices";

type Presentation = NonNullable<TemplateProjectResponseV1["presentation"]>;
type Asset = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>["templatePackage"]["assets"][number];

export const presentationMeta = "foldcv-v7-presentation";

/** What the mounted editor draws: Python's plan, the captured recipe and blob URLs of verified captured bytes. */
export type TemplateSheet = { css: string; variables: CSSProperties; logo: { url: string; style: CSSProperties } | null;
  presentation: Presentation; styles: ReadonlyMap<string, string>; icons: ReadonlyMap<string, string> };

/** Captured fonts and icons load once by hash and stay cached; replies carry only their names (D104). */
function assetUrl(asset: Asset): string {
  return `/v1/rich/template-assets/${asset.sha256}`;
}

const pt = (value: number): string => `${value}pt`;

/** Faces, sizes and colors come from the plan; geometry from the compiled recipe. Nothing is read from wording or IDs. */
export function templateSheet(response: TemplateProjectResponseV1): TemplateSheet | null {
  const presentation = response.presentation, project = response.workspace.project, plan = presentation?.editor;
  if (!presentation || !project || !plan) return null;
  const assets = new Map(project.templatePackage.assets.map(asset => [asset.id, asset]));
  const family = (id: string | null): string | null => {
    const asset = id === null ? undefined : assets.get(id);
    return asset ? `"fcv-${asset.sha256.slice(0, 24)}"` : null;
  };
  const rules = plan.fonts.flatMap(id => {
    const asset = assets.get(id);
    return asset ? [`@font-face { font-family: ${family(id) ?? ""}; src: url("${assetUrl(asset)}") format("truetype"); font-display: block; }`] : [];
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
  const icons = new Map(plan.icons.flatMap(id => { const asset = assets.get(id); return asset ? [[id, assetUrl(asset)] as const] : []; }));
  const recipe = presentation.recipe, style = recipe.style, [header, sidebar, main] = recipe.layout.regions;
  if (!header || !sidebar || !main) return null;
  const band = style.section_band, focus = style.focus, divider = style.header.divider, logoValue = style.header.logo;
  const variables = {
    "--fcv-page-width": pt(style.page.width), "--fcv-left": pt(sidebar.x), "--fcv-top": pt(style.header.name_top),
    "--fcv-sidebar": pt(sidebar.width), "--fcv-main": pt(main.width), "--fcv-gap": pt(main.x - sidebar.x - sidebar.width),
    "--fcv-header-left": pt(header.x - sidebar.x), "--fcv-header-width": pt(header.width),
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

function noteWidget(at: number, notice: BlockNotice): Decoration {
  return Decoration.widget(at, () => {
    const note = document.createElement("p");
    note.className = "fcv-import-note";
    note.dataset["issueId"] = notice.id;
    note.textContent = notice.message;
    return note;
  }, { side: -1, ignoreSelection: true, key: `import-note-${notice.id}` });
}

/** Node decorations that apply the plan to canonical block IDs; a block without a plan entry keeps the sheet defaults. */
export function templatePresentationPlugin(current: () => TemplateSheet | null, notices: () => readonly BlockNotice[] = () => []): Plugin {
  return new Plugin({ key: new PluginKey(presentationMeta), props: { decorations: state => {
    const sheet = current();
    if (!sheet) return DecorationSet.empty;
    const plan = sheet.presentation.editor, refs = sheet.presentation.blocks, views = sheet.presentation.recipe.views;
    const notes = new Map<string, BlockNotice>();
    for (const notice of notices()) if (!notes.has(notice.blockId)) notes.set(notice.blockId, notice);
    const decorations: Decoration[] = [];
    if (!plan) {
      state.doc.descendants((node, position) => {
        if (node.type.name !== "blockContainer") return;
        const id: unknown = node.attrs["id"], notice = typeof id === "string" ? notes.get(id) : undefined;
        if (notice) decorations.push(noteWidget(position + node.nodeSize - 1, notice));
      });
      return DecorationSet.create(state.doc, decorations);
    }
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
      const notice = typeof id === "string" ? notes.get(id) : undefined;
      if (!entry || !ref) {
        if (notice) decorations.push(noteWidget(position + node.nodeSize - 1, notice));
        return;
      }
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
      if (notice) decorations.push(noteWidget(position + node.nodeSize - 1, notice));
      // Inline spans that keep another style, and links. A technical link is a BlockNote link, not a bound link.
      const runs = literalRuns(entry.inline);
      content.descendants((child, offset) => {
        const at = position + 2 + offset, name = child.type.name;
        const identity: unknown = name === "templateField" ? child.attrs["bindingId"] : name === "manualScope" ? child.attrs["fragmentId"] : null;
        const key = typeof identity === "string" ? entry.inline?.[identity] : undefined;
        if (key) decorations.push(Decoration.node(at, at + child.nodeSize, { "data-fcv-style": sheet.styles.get(key) ?? "" }));
        if (name === "link" || (name === "boundLink" && entry.links?.includes(String(child.attrs["occurrenceId"]))))
          decorations.push(Decoration.node(at, at + child.nodeSize, { class: "fcv-link" }));
      });
      paintLiterals(content, position + 2, runs, key => sheet.styles.get(key) ?? "", decorations);
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
