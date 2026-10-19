export type Regions = [RichRegion, RichRegion, RichRegion];
export type Children11 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Backgroundcolor = string;
export type Bold = boolean;
export type Code = boolean;
export type Italic = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text = string;
export type Type = "text";
export type Content1 = StyledText[];
export type Href = string;
export type Type1 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Fieldkey = string;
export type Recordid = string;
export type Syncedfactrevision = number;
export type Text1 = string;
export type Type2 = "fact_field";
export type Content = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id = string;
export type Alignment = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Manualorder = boolean;
export type Presentation = "standard" | "focus";
export type Recordid1 = string | null;
export type Textcolor1 = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text2 = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id1 = string;
export type Kind = "citation";
export type Recordid2 = string;
export type Fieldkey1 = string;
export type Id2 = string;
export type Kind1 = "field_binding";
export type Recordid3 = string;
export type Id3 = string;
export type Kind2 = "working_owner";
export type Recordid4 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id4 = string;
export type Kind3 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision = number;
export type Type3 = "section";
export type Children10 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content2 = null;
export type Id5 = string;
export type Alignment1 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height = number;
export type Width = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision1 = number;
export type Type4 = "image";
export type Children9 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
/**
 * @minItems 1
 */
export type Columnwidths = [number | null, ...(number | null)[]];
export type Headercols = number;
export type Headerrows = number;
/**
 * @minItems 1
 */
export type Rows = [TableRow, ...TableRow[]];
export type Alignment2 = "left" | "center" | "right" | "justify";
export type Backgroundcolor2 = string;
export type Colspan = number;
export type Content3 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id6 = string;
export type Revision2 = number;
export type Rowspan = number;
export type Cells = TableCell[];
export type Id7 = string;
export type Id8 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision3 = number;
export type Type5 = "table";
export type Children8 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content4 = null;
export type Id9 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision4 = number;
export type Type6 = "divider";
export type Children7 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content5 = string;
export type Id10 = string;
export type Backgroundcolor4 = string;
export type Language = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision5 = number;
export type Type7 = "code";
export type Children6 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content6 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id11 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision6 = number;
export type Type8 = "quote";
export type Children5 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content7 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id12 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision7 = number;
export type Type9 = "toggle_list";
export type Children4 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content8 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id13 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision8 = number;
export type Type10 = "check_list";
export type Children3 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content9 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id14 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision9 = number;
export type Type11 = "numbered_list";
export type Children2 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content10 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id15 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision10 = number;
export type Type12 = "bullet_list";
export type Children1 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content11 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id16 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision11 = number;
export type Type13 = "heading";
export type Children = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content12 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id17 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision12 = number;
export type Type14 = "paragraph";
export type Blocks = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Id18 = string;
export type Revision13 = number;
export type Role = "header" | "sidebar" | "main";
export type Revision14 = number;
export type Schemaversion = 1;

export interface RichDocumentV1 {
  regions: Regions;
  revision: Revision14;
  schemaVersion: Schemaversion;
}
export interface RichRegion {
  blocks: Blocks;
  id: Id18;
  revision: Revision13;
  role: Role;
}
export interface ParagraphBlock {
  children: Children;
  content: Content12;
  id: Id17;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision12;
  type: Type14;
}
export interface HeadingBlock {
  children: Children1;
  content: Content11;
  id: Id16;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision11;
  type: Type13;
}
export interface BulletBlock {
  children: Children2;
  content: Content10;
  id: Id15;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision10;
  type: Type12;
}
export interface NumberedBlock {
  children: Children3;
  content: Content9;
  id: Id14;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision9;
  type: Type11;
}
export interface ChecklistBlock {
  children: Children4;
  content: Content8;
  id: Id13;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision8;
  type: Type10;
}
export interface ToggleBlock {
  children: Children5;
  content: Content7;
  id: Id12;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision7;
  type: Type9;
}
export interface QuoteBlock {
  children: Children6;
  content: Content6;
  id: Id11;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision6;
  type: Type8;
}
export interface CodeBlock {
  children: Children7;
  content: Content5;
  id: Id10;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision5;
  type: Type7;
}
export interface DividerBlock {
  children: Children8;
  content: Content4;
  id: Id9;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision4;
  type: Type6;
}
export interface TableBlock {
  children: Children9;
  content: TableContent;
  id: Id8;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision3;
  type: Type5;
}
export interface ImageBlock {
  children: Children10;
  content: Content2;
  id: Id5;
  props: ImageProps;
  provenance: Provenance1;
  revision: Revision1;
  type: Type4;
}
export interface SectionBlock {
  children: Children11;
  content: Content;
  id: Id;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision;
  type: Type3;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text;
  type: Type;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold;
  code?: Code;
  italic?: Italic;
  strike?: Strike;
  textColor?: Textcolor;
  underline?: Underline;
}
export interface Hyperlink {
  content: Content1;
  href: Href;
  type: Type1;
}
export interface FactFieldSpan {
  bindingId: Bindingid;
  bindingRootId?: Bindingrootid;
  fieldKey: Fieldkey;
  recordId: Recordid;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text1;
  type: Type2;
}
export interface SectionProps {
  alignment?: Alignment;
  backgroundColor?: Backgroundcolor1;
  manualOrder?: Manualorder;
  presentation?: Presentation;
  recordId: Recordid1;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence;
  fieldKeys: Fieldkeys;
  id: Id1;
  kind: Kind;
  recordId: Recordid2;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text2;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface FieldBinding {
  fieldKey: Fieldkey1;
  id: Id2;
  kind: Kind1;
  recordId: Recordid3;
}
export interface WorkingOwnership {
  id: Id3;
  kind: Kind2;
  recordId: Recordid4;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id4;
  kind: Kind3;
}
export interface ImageProps {
  alignment: Alignment1;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height;
  width: Width;
}
export interface TableContent {
  columnWidths: Columnwidths;
  headerCols?: Headercols;
  headerRows: Headerrows;
  rows: Rows;
}
export interface TableRow {
  cells: Cells;
  id: Id7;
}
export interface TableCell {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content3;
  id: Id6;
  revision: Revision2;
  rowspan?: Rowspan;
}
export interface ParagraphProps {
  alignment?: Alignment3;
  backgroundColor?: Backgroundcolor3;
  textColor?: Textcolor2;
}
export interface EmptyProps {}
export interface CodeProps {
  backgroundColor?: Backgroundcolor4;
  language: Language;
}
export interface ChecklistProps {
  alignment?: Alignment4;
  backgroundColor?: Backgroundcolor5;
  checked: Checked;
  textColor?: Textcolor3;
}
export interface NumberedProps {
  alignment?: Alignment5;
  backgroundColor?: Backgroundcolor6;
  start?: Start;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor7;
  level: Level;
  textColor?: Textcolor5;
}
