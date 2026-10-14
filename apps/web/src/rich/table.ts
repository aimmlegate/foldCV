import type { TableContent as WireTable } from "../contracts/generated/rich_document_v1";
import { fromInline, toInline, wireColor, type EditorInline, type FragmentId } from "./inline";
import type { TableRowIdentity } from "./table-identity";

export type EditorTable = { type: "tableContent"; columnWidths: (number | undefined)[]; headerRows?: number; headerCols?: number;
  rows: { cells: EditorInline[][] | { type: "tableCell"; props: { backgroundColor: string; textColor: string;
    textAlignment: "left" | "center" | "right" | "justify"; colspan?: number; rowspan?: number }; content: EditorInline[] }[] }[] };

export function toTable(content: WireTable): EditorTable {
  return { type: "tableContent", headerRows: content.headerRows, headerCols: content.headerCols ?? 0, columnWidths: content.columnWidths.map(value => value ?? undefined),
    rows: content.rows.map(row => ({ cells: row.cells.map(cell => ({ type: "tableCell" as const, props: {
      backgroundColor: cell.backgroundColor ?? "default", textColor: "default", textAlignment: cell.alignment ?? "left",
      colspan: cell.colspan ?? 1, rowspan: cell.rowspan ?? 1 }, content: toInline(cell.content) })) })) };
}
export function fromTable(content: EditorTable, identities: readonly TableRowIdentity[], old: WireTable | undefined, fragment: FragmentId): WireTable {
  const previous = new Map(old?.rows.flatMap(row => row.cells.map(cell => [cell.id, cell])) ?? []);
  const columnWidths = content.columnWidths.map(value => value ?? null), firstWidth = columnWidths[0];
  if (firstWidth === undefined) throw new Error("RICH_TABLE_EMPTY");
  const rows = content.rows.map((row, index) => {
      const identity = identities[index];
      if (!identity || identity.cells.length !== row.cells.length) throw new Error("RICH_TABLE_IDENTITY_MISSING");
      return { id: identity.id, cells: row.cells.map((cell, cellIndex) => {
        const id = identity.cells[cellIndex];
        if (!id) throw new Error("RICH_TABLE_IDENTITY_MISSING");
        const inline: readonly EditorInline[] = Array.isArray(cell) ? cell : cell.content;
        const textColor = wireColor(Array.isArray(cell) ? "default" : cell.props.textColor, "text");
        const color = (span: EditorInline): EditorInline => span.type === "text" ? { ...span, styles: { ...span.styles,
          textColor: span.styles.textColor && span.styles.textColor !== "default" ? span.styles.textColor : textColor } }
          : { ...span, content: span.content.map(child => ({ ...child, styles: { ...child.styles,
            textColor: child.styles.textColor && child.styles.textColor !== "default" ? child.styles.textColor : textColor } })) };
        return { id, revision: previous.get(id)?.revision ?? 1, content: fromInline(inline.map(color), fragment),
          alignment: Array.isArray(cell) ? "left" : cell.props.textAlignment,
          backgroundColor: wireColor(Array.isArray(cell) ? "default" : cell.props.backgroundColor, "background"),
          colspan: Array.isArray(cell) ? 1 : cell.props.colspan ?? 1, rowspan: Array.isArray(cell) ? 1 : cell.props.rowspan ?? 1 };
      }) };
    });
  const firstRow = rows[0]; if (!firstRow) throw new Error("RICH_TABLE_EMPTY");
  return { headerRows: content.headerRows ?? 0, headerCols: content.headerCols ?? 0, columnWidths: [firstWidth, ...columnWidths.slice(1)], rows: [firstRow, ...rows.slice(1)] };
}
