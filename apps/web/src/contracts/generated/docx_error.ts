export type Anchor = FieldAnchor | SectionAnchor | DocumentAnchor;
export type Fieldid = string;
export type Kind = "field";
export type End = number;
export type Start = number;
export type Kind1 = "section";
export type Sectionid = string;
export type Kind2 = "document";
export type Code =
  | "DOCX_NAME_LINE_LIMIT"
  | "DOCX_TITLE_LINE_LIMIT"
  | "DOCX_UNBREAKABLE_TEXT"
  | "DOCX_BLOCK_PAGE_BUDGET"
  | "DOCX_BLOCK_PLANNED_PAGE"
  | "DOCX_UNKNOWN_FOCUS_ICON"
  | "DOCX_TEXT_LIMIT"
  | "DOCX_LIST_LIMIT"
  | "DOCX_TOTAL_TEXT_LIMIT"
  | "DOCX_INVALID_CHARACTER"
  | "DOCX_INVALID_RENDER_INPUT"
  | "DOCX_RENDER_FAILED";
export type Path = string | null;

export interface DocxError {
  anchor: Anchor;
  code: Code;
  path: Path;
}
export interface FieldAnchor {
  fieldId: Fieldid;
  kind: Kind;
  range: Range | null;
}
export interface Range {
  end: End;
  start: Start;
}
export interface SectionAnchor {
  kind: Kind1;
  sectionId: Sectionid;
}
export interface DocumentAnchor {
  kind: Kind2;
}
