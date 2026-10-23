import type { PartialBlock } from "@blocknote/core";
import type { RichDocumentV2, TemplateSectionBlock } from "../contracts/generated/rich_document_v2";
import type { TableRowIdentity } from "./table-identity";
import type { EditorMarks } from "./inline";
import type { templateSchema } from "./template-schema";

type Schema = typeof templateSchema;
export type TemplateEditorBlock = PartialBlock<Schema["blockSchema"], Schema["inlineContentSchema"], Schema["styleSchema"]>;
type V2Block = RichDocumentV2["regions"][number]["blocks"][number];
type V2Inline = TemplateSectionBlock["content"][number];
type Styles = Extract<V2Inline, { type: "text" }>["styles"];
type Text = { type: "text"; text: string; styles: EditorMarks };
type Alignment = "left" | "center" | "right" | "justify";

function marks(value: Styles): EditorMarks {
  return { bold: value.bold ?? false, italic: value.italic ?? false, underline: value.underline ?? false, strike: value.strike ?? false,
    code: value.code ?? false, textColor: value.textColor ?? "default", backgroundColor: value.backgroundColor ?? "default" };
}
// ProseMirror has no empty text nodes; an empty field or scope keeps its node as an explicit anchor.
function text(value: string, styles: Styles): Text[] { return value ? [{ type: "text", text: value, styles: marks(styles) }] : []; }

/** Display projection only: identities ride on node attributes; canonical V7 content stays the server's lossless wire. */
export function projectTemplateInline(content: readonly V2Inline[]) {
  return content.map(span => {
    if (span.type === "text") return { type: "text" as const, text: span.text, styles: marks(span.styles) };
    if (span.type === "link") return { type: "link" as const, href: span.href,
      content: span.content.map(child => ({ type: "text" as const, text: child.text, styles: marks(child.styles) })) };
    if (span.type === "fact_field") return { type: "templateField" as const, props: { bindingId: span.bindingId,
      occurrenceId: span.occurrenceId, recordId: span.recordId, fieldKey: span.fieldKey, cellId: span.cellId ?? "",
      complete: span.complete }, content: text(span.text, span.styles) };
    if (span.type === "manual_scope") return { type: "manualScope" as const, props: { scopeId: span.scopeId,
      occurrenceId: span.occurrenceId, fragmentId: span.fragmentId }, content: text(span.text, span.styles) };
    const binding = span.labelBinding ?? span.urlBinding;
    return { type: "boundLink" as const, props: { href: span.href, binding: span.labelBinding ? "label" as const : "url" as const,
      cellId: binding?.cellId ?? "", occurrenceId: binding?.occurrenceId ?? "" },
      content: span.content.flatMap(child => text(child.text, child.styles)) };
  });
}

function alignment(value: string | null | undefined): Alignment {
  return value === "center" || value === "right" || value === "justify" ? value : "left";
}
function textProps(props: { alignment?: string | null; textColor?: string | null; backgroundColor?: string | null }) {
  return { textAlignment: alignment(props.alignment), textColor: props.textColor ?? "default", backgroundColor: props.backgroundColor ?? "default" };
}

export function projectTemplateBlock(block: V2Block): TemplateEditorBlock {
  const children = block.children.map(projectTemplateBlock);
  switch (block.type) {
    case "heading": return { id: block.id, type: "heading", props: { ...textProps(block.props), level: block.props.level },
      content: projectTemplateInline(block.content), children };
    case "section": return { id: block.id, type: "section", props: { ...textProps(block.props), recordId: block.props.recordId ?? "",
      presentation: block.props.presentation ?? "standard", manualOrder: block.props.manualOrder ?? false },
      content: projectTemplateInline(block.content), children };
    case "bullet_list": return { id: block.id, type: "bulletListItem", props: textProps(block.props), content: projectTemplateInline(block.content), children };
    case "numbered_list": return { id: block.id, type: "numberedListItem", props: block.props.start === null || block.props.start === undefined
      ? textProps(block.props) : { ...textProps(block.props), start: block.props.start }, content: projectTemplateInline(block.content), children };
    case "check_list": return { id: block.id, type: "checkListItem", props: { ...textProps(block.props), checked: block.props.checked },
      content: projectTemplateInline(block.content), children };
    case "toggle_list": return { id: block.id, type: "toggleListItem", props: textProps(block.props), content: projectTemplateInline(block.content), children };
    case "quote": return { id: block.id, type: "quote", props: textProps(block.props), content: projectTemplateInline(block.content), children };
    case "code": return { id: block.id, type: "codeBlock", props: { language: block.props.language,
      backgroundColor: block.props.backgroundColor ?? "default" }, content: block.content, children };
    case "divider": return { id: block.id, type: "divider", children };
    case "table": return { id: block.id, type: "table", props: { textColor: block.props.textColor ?? "default" }, content: {
      type: "tableContent", headerRows: block.content.headerRows, headerCols: block.content.headerCols ?? 0,
      columnWidths: block.content.columnWidths.map(value => value ?? undefined),
      rows: block.content.rows.map(row => ({ cells: row.cells.map(cell => ({ type: "tableCell" as const, props: {
        backgroundColor: cell.backgroundColor ?? "default", textColor: "default", textAlignment: alignment(cell.alignment),
        colspan: cell.colspan ?? 1, rowspan: cell.rowspan ?? 1 }, content: projectTemplateInline(cell.content) })) })) }, children };
    case "image": return { id: block.id, type: "image", props: { assetId: block.props.assetId, alt: block.props.alt,
      width: block.props.width, height: block.props.height, textAlignment: block.props.alignment },
      content: projectTemplateInline(block.props.caption), children };
    case "paragraph": return { id: block.id, type: "paragraph", props: textProps(block.props), content: projectTemplateInline(block.content), children };
  }
}

/** Regions keep the existing region-marker structure used by the editor. */
export function projectTemplateDocument(document: RichDocumentV2): TemplateEditorBlock[] {
  return document.regions.map(region => ({ id: region.id, type: "region", props: { role: region.role },
    children: region.blocks.map(projectTemplateBlock) }));
}

/** Canonical row and cell IDs for the editor table nodes; cell input is addressed by them. */
export function templateTableIdentities(document: RichDocumentV2): Map<string, TableRowIdentity[]> {
  const result = new Map<string, TableRowIdentity[]>();
  const visit = (block: V2Block): void => {
    if (block.type === "table") result.set(block.id, block.content.rows.map(row => ({ id: row.id, cells: row.cells.map(cell => cell.id) })));
    block.children.forEach(visit);
  };
  document.regions.forEach(region => region.blocks.forEach(visit));
  return result;
}
