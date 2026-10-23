import type { CSSProperties } from "react";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";

type Presentation = NonNullable<TemplateProjectResponseV1["presentation"]>;
type Asset = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>["templatePackage"]["assets"][number];

export const presentationMeta = "foldcv-v7-presentation";

/** What the mounted editor draws: Python's plan, the captured recipe and blob URLs of verified captured bytes. */
export type TemplateSheet = { css: string; variables: CSSProperties; logo: { url: string; style: CSSProperties } | null;
  presentation: Presentation; styles: ReadonlyMap<string, string>; icons: ReadonlyMap<string, string> };

const urls = new Map<string, string>();
function assetUrl(asset: Asset): string {
  let url = urls.get(asset.sha256);
  if (!url) {
    const binary = atob(asset.bytesBase64);
    url = URL.createObjectURL(new Blob([Uint8Array.from(binary, character => character.charCodeAt(0))], { type: asset.mimeType }));
    urls.set(asset.sha256, url);
  }
  return url;
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
  } as CSSProperties;
  const logoAsset = logoValue ? assets.get(logoValue.asset) : undefined;
  const logo = logoValue && logoAsset ? { url: assetUrl(logoAsset), style: { left: pt(logoValue.x), top: pt(logoValue.top),
    width: pt(logoValue.width), height: pt(logoValue.height) } } : null;
  return { css: rules.join("\n"), variables, logo, presentation, styles, icons };
}

/** Node decorations that apply the plan to canonical block IDs; a block without a plan entry keeps the sheet defaults. */
export function templatePresentationPlugin(current: () => TemplateSheet | null): Plugin {
  return new Plugin({ key: new PluginKey(presentationMeta), props: { decorations: state => {
    const sheet = current();
    if (!sheet) return DecorationSet.empty;
    const plan = sheet.presentation.editor, refs = sheet.presentation.blocks, views = sheet.presentation.recipe.views;
    if (!plan) return DecorationSet.empty;
    const rows = new Set(Object.values(plan.blocks).flatMap(entry => entry.focus?.blocks ?? []));
    const decorations: Decoration[] = [];
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
      // Inline spans that keep another style, and links that export as hyperlinks.
      content.descendants((child, offset) => {
        const at = position + 2 + offset, name = child.type.name;
        const identity: unknown = name === "templateField" ? child.attrs["bindingId"] : name === "manualScope" ? child.attrs["fragmentId"] : null;
        const key = typeof identity === "string" ? entry.inline?.[identity] : undefined;
        if (key) decorations.push(Decoration.node(at, at + child.nodeSize, { "data-fcv-style": sheet.styles.get(key) ?? "" }));
        if (name === "boundLink" && entry.links?.includes(String(child.attrs["occurrenceId"])))
          decorations.push(Decoration.node(at, at + child.nodeSize, { class: "fcv-link" }));
      });
    });
    return DecorationSet.create(state.doc, decorations);
  } } });
}
