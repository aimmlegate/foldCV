export type Regions = [TemplateRegion, TemplateRegion, TemplateRegion];
export type Children11 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type End = number;
export type Slicehash = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Start = number;
export type Unitid = string;
export type Unitrevision = number;
export type Citations = SourceSpan[];
export type Itemhandle = string | null;
export type Nodeindex = number | null;
export type Alignment = ("left" | "center" | "right" | "justify") | null;
export type Bold = boolean | null;
export type Color = string | null;
export type Font = string | null;
export type Italic = boolean | null;
export type Size = number | null;
export type Packagehash = string;
export type Styletoken = string;
export type Templateinstanceid = string | null;
export type Viewkey = string;
export type Backgroundcolor = string;
export type Bold1 = boolean;
export type Code = boolean;
export type Italic1 = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text = string;
export type Type = "text";
export type Content1 = PresentedText[];
export type Href = string;
export type Type1 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Cellid = string | null;
export type Citations1 = SourceSpan[];
export type Complete = boolean;
export type Fieldkey = string;
export type Occurrenceid = string;
export type Recordid = string;
export type Syncedfactrevision = number;
export type Text1 = string;
export type Type2 = "fact_field";
export type Content2 = (PresentedText | FieldOccurrence)[];
export type Href1 = string;
export type Cellid1 = string;
export type Fieldkey1 = string;
export type Occurrenceid1 = string;
export type Recordid1 = string;
export type Type3 = "bound_link";
export type Citations2 = SourceSpan[];
export type Fragmentid = string;
export type Occurrenceid2 = string;
export type Scopeid = string;
export type Text2 = string;
export type Type4 = "manual_scope";
export type Content = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id = string;
export type Alignment1 = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Manualorder = boolean;
export type Presentation = "standard" | "focus";
export type Recordid2 = string | null;
export type Textcolor1 = string;
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Text3 = string;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Evidence = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id1 = string;
export type Kind = "citation";
export type Recordid3 = string;
export type Fieldkey2 = string;
export type Id2 = string;
export type Kind1 = "field_binding";
export type Recordid4 = string;
export type Id3 = string;
export type Kind2 = "working_owner";
export type Recordid5 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id4 = string;
export type Kind3 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision = number;
export type Type5 = "section";
export type Children10 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content3 = null;
export type Id5 = string;
export type Alignment2 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Height = number;
export type Width = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision1 = number;
export type Type6 = "image";
export type Children9 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
/**
 * @minItems 1
 */
export type Columnwidths = [number | null, ...(number | null)[]];
export type Headercols = number;
export type Headerrows = number;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor2 = string;
export type Colspan = number;
export type Content4 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id6 = string;
export type Revision2 = number;
export type Rowspan = number;
export type Cells = TemplateTableCell[];
export type Id7 = string;
export type Rows = TemplateTableRow[];
export type Id8 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision3 = number;
export type Type7 = "table";
export type Children8 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content5 = null;
export type Id9 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision4 = number;
export type Type8 = "divider";
export type Children7 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content6 = string;
export type Id10 = string;
export type Backgroundcolor4 = string;
export type Language = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision5 = number;
export type Type9 = "code";
export type Children6 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content7 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id11 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision6 = number;
export type Type10 = "quote";
export type Children5 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content8 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id12 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision7 = number;
export type Type11 = "toggle_list";
export type Children4 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content9 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id13 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision8 = number;
export type Type12 = "check_list";
export type Children3 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content10 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id14 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start1 = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision9 = number;
export type Type13 = "numbered_list";
export type Children2 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content11 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id15 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision10 = number;
export type Type14 = "bullet_list";
export type Children1 = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content12 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id16 = string;
export type Alignment7 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision11 = number;
export type Type15 = "heading";
export type Children = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Content13 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id17 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision12 = number;
export type Type16 = "paragraph";
export type Blocks = (
  | TemplateParagraphBlock
  | TemplateHeadingBlock
  | TemplateBulletBlock
  | TemplateNumberedBlock
  | TemplateChecklistBlock
  | TemplateToggleBlock
  | TemplateQuoteBlock
  | TemplateCodeBlock
  | TemplateDividerBlock
  | TemplateTableBlock
  | TemplateImageBlock
  | TemplateSectionBlock
)[];
export type Id18 = string;
export type Revision13 = number;
export type Role = "header" | "sidebar" | "main";
export type Revision14 = number;
export type Schemaversion = 2;

export interface RichDocumentV2 {
  regions: Regions;
  revision: Revision14;
  schemaVersion: Schemaversion;
}
export interface TemplateRegion {
  blocks: Blocks;
  id: Id18;
  revision: Revision13;
  role: Role;
}
export interface TemplateParagraphBlock {
  children: Children;
  content: Content13;
  id: Id17;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision12;
  type: Type16;
}
export interface TemplateHeadingBlock {
  children: Children1;
  content: Content12;
  id: Id16;
  presentation: AuthoredPresentation | null;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision11;
  type: Type15;
}
export interface TemplateBulletBlock {
  children: Children2;
  content: Content11;
  id: Id15;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision10;
  type: Type14;
}
export interface TemplateNumberedBlock {
  children: Children3;
  content: Content10;
  id: Id14;
  presentation: AuthoredPresentation | null;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision9;
  type: Type13;
}
export interface TemplateChecklistBlock {
  children: Children4;
  content: Content9;
  id: Id13;
  presentation: AuthoredPresentation | null;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision8;
  type: Type12;
}
export interface TemplateToggleBlock {
  children: Children5;
  content: Content8;
  id: Id12;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision7;
  type: Type11;
}
export interface TemplateQuoteBlock {
  children: Children6;
  content: Content7;
  id: Id11;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision6;
  type: Type10;
}
export interface TemplateCodeBlock {
  children: Children7;
  content: Content6;
  id: Id10;
  presentation: AuthoredPresentation | null;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision5;
  type: Type9;
}
export interface TemplateDividerBlock {
  children: Children8;
  content: Content5;
  id: Id9;
  presentation: AuthoredPresentation | null;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision4;
  type: Type8;
}
export interface TemplateTableBlock {
  children: Children9;
  content: TemplateTableContent;
  id: Id8;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision3;
  type: Type7;
}
export interface TemplateImageBlock {
  children: Children10;
  content: Content3;
  id: Id5;
  presentation: AuthoredPresentation | null;
  props: TemplateImageProps;
  provenance: Provenance1;
  revision: Revision1;
  type: Type6;
}
export interface TemplateSectionBlock {
  children: Children11;
  content: Content;
  id: Id;
  presentation: AuthoredPresentation | null;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision;
  type: Type5;
}
export interface PresentedText {
  citations?: Citations;
  presentation?: AuthoredPresentation | null;
  styles: InlineStyles;
  text: Text;
  type: Type;
}
export interface SourceSpan {
  end: End;
  sliceHash: Slicehash;
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  start: Start;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface AuthoredPresentation {
  itemHandle: Itemhandle;
  nodeIndex?: Nodeindex;
  overrides: StyleOverrides;
  packageHash: Packagehash;
  styleToken: Styletoken;
  templateInstanceId: Templateinstanceid;
  viewKey: Viewkey;
}
export interface StyleOverrides {
  alignment: Alignment;
  bold: Bold;
  color: Color;
  font: Font;
  italic: Italic;
  size: Size;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold1;
  code?: Code;
  italic?: Italic1;
  strike?: Strike;
  textColor?: Textcolor;
  underline?: Underline;
}
export interface PresentedHyperlink {
  content: Content1;
  href: Href;
  presentation?: AuthoredPresentation | null;
  type: Type1;
}
export interface FieldOccurrence {
  bindingId: Bindingid;
  bindingRootId?: Bindingrootid;
  cellId: Cellid;
  citations?: Citations1;
  complete: Complete;
  fieldKey: Fieldkey;
  occurrenceId: Occurrenceid;
  presentation: AuthoredPresentation | null;
  recordId: Recordid;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text1;
  type: Type2;
}
export interface BoundLink {
  content: Content2;
  href: Href1;
  labelBinding: FieldRef | null;
  presentation: AuthoredPresentation | null;
  type: Type3;
  urlBinding: FieldRef | null;
}
export interface FieldRef {
  cellId: Cellid1;
  fieldKey: Fieldkey1;
  occurrenceId: Occurrenceid1;
  recordId: Recordid1;
}
export interface ManualScopeSpan {
  citations?: Citations2;
  fragmentId: Fragmentid;
  occurrenceId: Occurrenceid2;
  presentation: AuthoredPresentation | null;
  scopeId: Scopeid;
  styles: InlineStyles;
  text: Text2;
  type: Type4;
}
export interface SectionProps {
  alignment?: Alignment1;
  backgroundColor?: Backgroundcolor1;
  manualOrder?: Manualorder;
  presentation?: Presentation;
  recordId: Recordid2;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence;
  fieldKeys: Fieldkeys;
  id: Id1;
  kind: Kind;
  recordId: Recordid3;
}
export interface EvidenceSpan {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision1;
  text: Text3;
  unitId: Unitid1;
  unitRevision: Unitrevision1;
}
export interface FieldBinding {
  fieldKey: Fieldkey2;
  id: Id2;
  kind: Kind1;
  recordId: Recordid4;
}
export interface WorkingOwnership {
  id: Id3;
  kind: Kind2;
  recordId: Recordid5;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id4;
  kind: Kind3;
}
export interface TemplateImageProps {
  alignment: Alignment2;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height;
  width: Width;
}
export interface TemplateTableContent {
  columnWidths: Columnwidths;
  headerCols?: Headercols;
  headerRows: Headerrows;
  rows: Rows;
}
export interface TemplateTableRow {
  cells: Cells;
  id: Id7;
}
export interface TemplateTableCell {
  alignment?: Alignment3;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content4;
  id: Id6;
  revision: Revision2;
  rowspan?: Rowspan;
}
export interface ParagraphProps {
  alignment?: Alignment4;
  backgroundColor?: Backgroundcolor3;
  textColor?: Textcolor2;
}
export interface EmptyProps {}
export interface CodeProps {
  backgroundColor?: Backgroundcolor4;
  language: Language;
}
export interface ChecklistProps {
  alignment?: Alignment5;
  backgroundColor?: Backgroundcolor5;
  checked: Checked;
  textColor?: Textcolor3;
}
export interface NumberedProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor6;
  start?: Start1;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment7;
  backgroundColor?: Backgroundcolor7;
  level: Level;
  textColor?: Textcolor5;
}
