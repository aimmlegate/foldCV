import type { Content, StyledText } from "../contracts/generated/rich_document_v1";
import type { RichBlock } from "./save-queue";
import { stableJson } from "./json";

function textRuns(content: StyledText[]): StyledText[] {
  const result: StyledText[] = [];
  for (const span of content) {
    const last = result.at(-1);
    if (last && stableJson(last.styles) === stableJson(span.styles)) last.text += span.text;
    else result.push(structuredClone(span));
  }
  return result;
}
export function normalizeInline(content: Content): Content {
  const result: Content = [];
  for (const span of content) {
    const last = result.at(-1);
    if (span.type === "text" && last?.type === "text" && stableJson(last.styles) === stableJson(span.styles)) last.text += span.text;
    else if (span.type === "link" && last?.type === "link" && span.href === last.href) last.content = textRuns([...last.content, ...span.content]);
    else result.push(span.type === "link" ? { ...span, content: textRuns(span.content) } : structuredClone(span));
  }
  return result;
}
/** BlockNote merges adjacent equal text runs; these boundaries have no authored identity. */
export function normalizedBlock(block: RichBlock): RichBlock {
  const copy = structuredClone(block);
  if (Array.isArray(copy.content)) copy.content = normalizeInline(copy.content);
  else if (copy.type === "table") for (const row of copy.content.rows) for (const cell of row.cells) cell.content = normalizeInline(cell.content);
  else if (copy.type === "image") copy.props.caption = normalizeInline(copy.props.caption);
  return copy;
}
