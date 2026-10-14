import { COLORS_DEFAULT } from "@blocknote/core";
import type { Content, InlineStyles } from "../contracts/generated/rich_document_v1";

export type EditorMarks = { bold?: boolean; italic?: boolean; underline?: boolean; strike?: boolean; code?: boolean;
  textColor?: string; backgroundColor?: string };
export type EditorText = { type: "text"; text: string; styles: EditorMarks };
export type EditorInline = EditorText | { type: "link"; href: string; content: EditorText[] }
  | { type: "factField"; props: { bindingId: string; recordId: string; fieldKey: string; syncedFactRevision: number }; content: EditorText[] };
export type FragmentId = (bindingId: string, fragment: string) => string;

export function wireColor(value: string | undefined, kind: "text" | "background"): string {
  if (value === undefined || value === "default") return "default";
  const palette = COLORS_DEFAULT[value];
  if (palette) return palette[kind];
  if (/^#[a-fA-F0-9]{6}$/.test(value)) return value.toLowerCase();
  const short = /^#([a-fA-F0-9])([a-fA-F0-9])([a-fA-F0-9])$/.exec(value);
  if (short?.[1] && short[2] && short[3]) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`.toLowerCase();
  const rgb = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(value);
  if (rgb && rgb.slice(1).every(part => Number(part) <= 255)) return "#" + rgb.slice(1).map(part => Number(part).toString(16).padStart(2, "0")).join("");
  throw new Error("RICH_COLOR_UNSUPPORTED");
}
function marks(value: InlineStyles): EditorMarks { return { bold: value.bold ?? false, italic: value.italic ?? false,
  underline: value.underline ?? false, strike: value.strike ?? false, code: value.code ?? false,
  textColor: value.textColor ?? "default", backgroundColor: value.backgroundColor ?? "default" }; }
export function wireMarks(value: EditorMarks): InlineStyles { return { bold: value.bold ?? false, italic: value.italic ?? false,
  underline: value.underline ?? false, strike: value.strike ?? false, code: value.code ?? false,
  textColor: wireColor(value.textColor, "text"), backgroundColor: wireColor(value.backgroundColor, "background") }; }

export function toInline(content: Content): EditorInline[] {
  return content.map(span => span.type === "link" ? { type: "link", href: span.href,
    content: span.content.map(child => ({ type: "text", text: child.text, styles: marks(child.styles) })) }
    : span.type === "fact_field" ? { type: "factField", props: { bindingId: span.bindingId, recordId: span.recordId,
      fieldKey: span.fieldKey, syncedFactRevision: span.syncedFactRevision }, content: [{ type: "text", text: span.text, styles: marks(span.styles) }] }
      : { type: "text", text: span.text, styles: marks(span.styles) });
}
export function fromInline(content: readonly EditorInline[], fragmentId: FragmentId): Content {
  return content.flatMap((span): Content => {
    if (span.type === "link") return [{ type: "link", href: span.href,
      content: span.content.map(child => ({ type: "text", text: child.text, styles: wireMarks(child.styles) })) }];
    if (span.type === "text") return [{ type: "text", text: span.text, styles: wireMarks(span.styles) }];
    const chunks: { text: string; styles: InlineStyles }[] = [];
    for (const child of span.content) {
      const styles = wireMarks(child.styles), last = chunks.at(-1);
      if (last && JSON.stringify(last.styles) === JSON.stringify(styles)) last.text += child.text;
      else chunks.push({ text: child.text, styles });
    }
    if (!chunks.length) chunks.push({ text: "", styles: wireMarks({}) });
    let offset = 0;
    return chunks.map((chunk, index) => {
      const bindingId = index === 0 ? span.props.bindingId : fragmentId(span.props.bindingId, `${offset}:${JSON.stringify(chunk.styles)}`);
      offset += chunk.text.length;
      return { type: "fact_field", bindingId, recordId: span.props.recordId, fieldKey: span.props.fieldKey,
        syncedFactRevision: span.props.syncedFactRevision, text: chunk.text, styles: chunk.styles };
    });
  });
}
