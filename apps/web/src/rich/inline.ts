import { COLORS_DEFAULT } from "@blocknote/core";
import type { InlineStyles } from "../contracts/generated/rich_document_v1";

export type EditorMarks = { bold?: boolean; italic?: boolean; underline?: boolean; strike?: boolean; code?: boolean;
  textColor?: string; backgroundColor?: string };

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
export function wireMarks(value: EditorMarks): InlineStyles { return { bold: value.bold ?? false, italic: value.italic ?? false,
  underline: value.underline ?? false, strike: value.strike ?? false, code: value.code ?? false,
  textColor: wireColor(value.textColor, "text"), backgroundColor: wireColor(value.backgroundColor, "background") }; }
