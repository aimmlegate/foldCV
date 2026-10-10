export type Bytelength = number;
export type Byteref = string;
export type Bytesha256 = string;
export type Code = "NO_TEXT" | "IMAGE" | "SHAPE" | "TEXT_BOX" | "UNSUPPORTED_CONTENT";
export type Column = number | null;
export type Kind = "page" | "paragraph" | "table_cell" | "header" | "footer" | "image" | "pasted";
export type Page = number | null;
export type Paragraph = number | null;
export type Part = string | null;
export type Row = number | null;
export type Table = number | null;
/**
 * @maxItems 5000
 */
export type Gaps = ExtractGap[];
export type Part1 = string;
export type Relationshipid = string;
export type Target = string;
/**
 * @maxItems 100
 */
export type Links = ExtractLink[];
export type Mimetype = string;
export type Originalname = string;
export type Pagecount = number | null;
export type Parser = string;
export type Parserversion = string;
export type Sourceid = string;
export type Sourcekind = "pdf" | "docx" | "txt" | "markdown" | "paste";
export type Id = string;
export type Order = number;
export type Text = string;
/**
 * @maxItems 5000
 */
export type Units = ExtractUnit[];

export interface ExtractResult {
  byteLength: Bytelength;
  byteRef: Byteref;
  byteSha256: Bytesha256;
  gaps: Gaps;
  links: Links;
  mimeType: Mimetype;
  originalName: Originalname;
  pageCount?: Pagecount;
  parser: Parser;
  parserVersion: Parserversion;
  sourceId: Sourceid;
  sourceKind: Sourcekind;
  units: Units;
}
export interface ExtractGap {
  code: Code;
  location: ExtractLocation;
}
export interface ExtractLocation {
  column?: Column;
  kind: Kind;
  page?: Page;
  paragraph?: Paragraph;
  part?: Part;
  row?: Row;
  table?: Table;
}
export interface ExtractLink {
  part: Part1;
  relationshipId: Relationshipid;
  target: Target;
}
export interface ExtractUnit {
  id: Id;
  location: ExtractLocation;
  order: Order;
  text: Text;
}
