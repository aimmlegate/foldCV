export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Revision = number;
/**
 * @minItems 1
 * @maxItems 10
 */
export type Sources =
  | [Source]
  | [Source, Source]
  | [Source, Source, Source]
  | [Source, Source, Source, Source]
  | [Source, Source, Source, Source, Source]
  | [Source, Source, Source, Source, Source, Source]
  | [Source, Source, Source, Source, Source, Source, Source]
  | [Source, Source, Source, Source, Source, Source, Source, Source]
  | [Source, Source, Source, Source, Source, Source, Source, Source, Source]
  | [Source, Source, Source, Source, Source, Source, Source, Source, Source, Source];
export type Byteref = string;
export type Bytesha256 = string;
export type Id = string;
export type Mimetype = string;
export type Originalname = string;
export type Id1 = string;
export type Origin = "user";
export type Revision1 = number;
export type Text = string;
export type Unitid = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision2 = number;
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id2 = string;
export type Column = number | null;
export type Index = number;
export type Kind = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision3 = number;
export type Blankbefore = number | null;
export type Bold = boolean | null;
export type Bounds = [number, number, number, number] | null;
export type Column1 = number | null;
export type Columnspan = number | null;
export type Fontsize = number | null;
export type Gapbefore = number | null;
export type Group = number | null;
export type Headinglevel = number | null;
export type Indent = number | null;
export type Layoutuncertain = boolean;
export type Listlevel = number | null;
export type Part = string | null;
export type Rowmerge = ("start" | "continue") | null;
export type Style = string | null;
export type Text1 = string;
export type Units = SourceUnit[];
export type Code = string;
export type Page = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];

export interface GuiNormalizeRequest {
  formattingAsOf: PartialDate;
  revision: Revision;
  sources: Sources;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision2;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id1;
  origin: Origin;
  revision: Revision1;
  text: Text;
  unitId: Unitid;
}
export interface SourceUnit {
  disposition: Disposition;
  id: Id2;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision3;
  structure?: SourceStructure | null;
  text: Text1;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind;
  row: Row;
}
/**
 * Observed layout cues, never semantic resume fields.
 */
export interface SourceStructure {
  blankBefore?: Blankbefore;
  bold?: Bold;
  bounds?: Bounds;
  column?: Column1;
  columnSpan?: Columnspan;
  fontSize?: Fontsize;
  gapBefore?: Gapbefore;
  group?: Group;
  headingLevel?: Headinglevel;
  indent?: Indent;
  layoutUncertain?: Layoutuncertain;
  listLevel?: Listlevel;
  part?: Part;
  rowMerge?: Rowmerge;
  style?: Style;
}
export interface SourceWarning {
  code: Code;
  page?: Page;
}
