export type Embedding = "allowed" | "not_applicable";
export type Id = string;
export type MimeType = string;
export type Path = string;
export type Role = "font" | "logo" | "icon" | "catalog";
export type Assets = AssetDeclaration[];
export type Field = string;
export type ItemPointer = string | null;
export type Pointer = string;
export type Kind = "owned_by" | "extension_of" | "related_to";
export type SubjectPointer = string;
export type SemanticType = string;
export type Bindings = Binding[];
export type Id1 = string;
export type Kind1 =
  | "content_schema"
  | "evidence_identity"
  | "protected_values"
  | "claim_ownership"
  | "complete_assignment"
  | "semantic_support"
  | "task_result_separation"
  | "attribution";
export type Fields = string[];
export type Instructions = string[];
export type Version = 1;
export type Checks = Check[];
export type JsonValue = unknown;
export type DependsOn = string[];
export type Extract = string[];
export type Id2 = string;
export type Mode = "model" | "derived" | "source_copy";
export type Operation = string | null;
export type Order = number;
export type Region = "header" | "sidebar" | "main";
export type Fields1 = string[];
export type Instructions1 = string[];
export type Id3 = string;
export type Kind2 = "source" | "fact_type" | "block" | "operation";
export type Selectors = InputRef[];
export type FallbackStyle = string | null;
export type Heading = "none" | "plain" | "band";
export type Inset = number;
export type ItemGap = number;
export type Mode1 = "object" | "items";
export type Background = string | null;
export type DetailStyle = string | null;
export type ExperienceField = string | null;
export type Field1 = string | null;
export type Fields2 = string[];
export type HeaderSlot = ("name" | "profession") | null;
export type ItemField = string | null;
export type NameField = string | null;
export type Separator = string;
export type Style = string;
export type Type = "text" | "join_fields" | "join_items" | "bullets" | "tags" | "period" | "link" | "focus_entry";
export type UrlField = string | null;
export type Nodes = ViewNode[];
export type Equals = string;
export type Operation1 = string;
export type Blocks = Block[];
export type Field2 = string;
export type Period = string | null;
export type BuiltinKind =
  | (
      | "candidate"
      | "detail"
      | "employment"
      | "subproject"
      | "technology"
      | "education"
      | "language"
      | "certification"
      | "claim"
      | "metric"
      | "leadership"
      | "unresolved"
    )
  | null;
export type Id4 = string;
export type Kind3 = "owned_by" | "extension_of" | "related_to";
export type TargetTypes = string[];
export type Relations = RelationDeclaration[];
export type SchemaVersion = string;
export type FactTypes = FactType[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id5 = "header" | "sidebar" | "main";
export type Width = number;
export type X = number;
export type Regions = Region1[];
export type Extract1 = string[];
export type Permission = "allowTextRewrite";
export type Rewrite1 = string[];
export type DependsOn1 = string[];
export type Id6 = string;
export type Inputs = InputRef[];
export type Kind4 = "partition_employment";
export type Compact = string;
export type Detailed = string;
export type Years = number;
export type Version1 = 1;
export type DependsOn2 = string[];
export type Id7 = string;
export type Inputs1 = InputRef[];
export type Kind5 = "select_role_branch";
export type Matched = string;
export type Otherwise = string;
export type RoleFamilies = string[];
export type Version2 = 1;
export type DependsOn3 = string[];
export type Id8 = string;
export type Inputs2 = InputRef[];
export type Kind6 = "assign_skills";
export type Groups = string[];
export type UncertainGroup = string;
export type Version3 = 1;
export type DependsOn4 = string[];
export type Id9 = string;
export type Inputs3 = InputRef[];
export type Kind7 = "format_period";
export type Separator1 = string;
export type Version4 = 1;
export type DependsOn5 = string[];
export type Id10 = string;
export type Inputs4 = InputRef[];
export type Kind8 = "preserve_stated_text";
export type Version5 = 1;
export type Operations = (PartitionOperation | RoleOperation | SkillsOperation | PeriodOperation | PreserveOperation)[];
export type SchemaVersion1 = 3;
export type RetainOriginal = true;
export type RetainUnmappedFacts = true;
export type Marker = string;
export type MarkerOffset = number;
export type MarkerSize = number;
export type TextOffset = number;
export type IconCatalog = string | null;
export type IconFit = "contain";
export type IconHeight = number;
export type IconWidth = number;
export type IconX = number;
export type MinimumRowHeight = number;
export type MissingIcon = "text_only";
export type TextX = number;
export type BaselineY = number;
export type CenterX = number;
export type Repeat = "every_page";
export type Style2 = string;
export type Text = string;
export type Color = string;
export type FollowHeader = true;
export type Width1 = number;
export type X1 = number;
export type X2 = number;
export type Y = number;
export type Asset = string;
export type Fit = "contain";
export type Height = number;
export type Top = number;
export type Width2 = number;
export type X3 = number;
export type NameTop = number;
export type Overflow = "grow_header_and_move_body";
export type ProfessionTop = number;
export type BodyBottom = number;
export type ContinuationBodyTop = number;
export type FirstBodyTop = number;
export type Height1 = number;
export type Width3 = number;
export type Background1 = string;
export type HeadingStyle = string;
export type Height2 = number;
export type TextInset = number;
export type Color1 = string;
export type Font = string;
export type LineHeight = number;
export type Size = number;
export type DefaultLocale = string;
export type Id11 = string;
export type Name = string;
export type Revision = string;

export interface TemplateDefinition {
  assets: Assets;
  blocks: Blocks;
  content_definitions: ContentDefinitions;
  fact_types: FactTypes;
  layout: Layout;
  model: ModelInstructions;
  operations: Operations;
  provenance: Provenance;
  schema_version: SchemaVersion1;
  source: SourcePolicy;
  style: Style1;
  template: TemplateIdentity;
}
export interface AssetDeclaration {
  embedding: Embedding;
  id: Id;
  mime_type: MimeType;
  path: Path;
  role: Role;
}
export interface Block {
  bindings: Bindings;
  checks: Checks;
  content_schema: ContentSchema;
  depends_on: DependsOn;
  extract: Extract;
  id: Id2;
  mode: Mode;
  operation: Operation;
  placement: Placement;
  rewrite: Rewrite;
  selectors: Selectors;
  view: View;
  when: Condition | null;
}
export interface Binding {
  field: Field;
  item_pointer?: ItemPointer;
  pointer: Pointer;
  relation: BindingRelation | null;
  semantic_type: SemanticType;
}
export interface BindingRelation {
  kind: Kind;
  subject_pointer: SubjectPointer;
}
export interface Check {
  id: Id1;
  kind: Kind1;
  parameters: CheckParameters;
  version: Version;
}
export interface CheckParameters {
  fields: Fields;
  instructions: Instructions;
}
export interface ContentSchema {
  [k: string]: JsonValue;
}
export interface Placement {
  order: Order;
  region: Region;
}
export interface Rewrite {
  fields: Fields1;
  instructions: Instructions1;
}
export interface InputRef {
  id: Id3;
  kind: Kind2;
}
export interface View {
  fallback_style?: FallbackStyle;
  heading: Heading;
  inset: Inset;
  item_gap: ItemGap;
  mode: Mode1;
  nodes: Nodes;
  title: Title;
}
export interface ViewNode {
  background?: Background;
  detail_style?: DetailStyle;
  experience_field?: ExperienceField;
  field?: Field1;
  fields?: Fields2;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label;
  name_field?: NameField;
  prefix?: Prefix;
  separator?: Separator;
  style: Style;
  type: Type;
  url_field?: UrlField;
}
export interface Label {
  [k: string]: string;
}
export interface Prefix {
  [k: string]: string;
}
export interface Title {
  [k: string]: string;
}
export interface Condition {
  equals: Equals;
  operation: Operation1;
}
export interface ContentDefinitions {
  [k: string]: {
    [k: string]: JsonValue;
  };
}
export interface FactType {
  builtin_fields?: BuiltinFields;
  builtin_kind: BuiltinKind;
  id: Id4;
  relations: Relations;
  schema: Schema;
  schema_version: SchemaVersion;
}
export interface BuiltinFields {
  [k: string]: BuiltinFieldBinding;
}
export interface BuiltinFieldBinding {
  field: Field2;
  period: Period;
}
export interface RelationDeclaration {
  kind: Kind3;
  target_types: TargetTypes;
}
export interface Schema {
  [k: string]: JsonValue;
}
export interface Layout {
  pagination: Pagination;
  reading_order: ReadingOrder;
  regions: Regions;
}
export interface Pagination {
  allow_more_pages: AllowMorePages;
  allow_project_split: AllowProjectSplit;
  keep_heading_with_next: KeepHeadingWithNext;
  truncate_content: TruncateContent;
}
export interface Region1 {
  flow: Flow;
  id: Id5;
  width: Width;
  x: X;
}
export interface ModelInstructions {
  extract: Extract1;
  permission: Permission;
  rewrite: Rewrite1;
}
export interface PartitionOperation {
  depends_on: DependsOn1;
  id: Id6;
  inputs: Inputs;
  kind: Kind4;
  parameters: PartitionParameters;
  version: Version1;
}
export interface PartitionParameters {
  compact: Compact;
  detailed: Detailed;
  years: Years;
}
export interface RoleOperation {
  depends_on: DependsOn2;
  id: Id7;
  inputs: Inputs1;
  kind: Kind5;
  parameters: RoleParameters;
  version: Version2;
}
export interface RoleParameters {
  matched: Matched;
  otherwise: Otherwise;
  role_families: RoleFamilies;
}
export interface SkillsOperation {
  depends_on: DependsOn3;
  id: Id8;
  inputs: Inputs2;
  kind: Kind6;
  parameters: SkillsParameters;
  version: Version3;
}
export interface SkillsParameters {
  groups: Groups;
  uncertain_group: UncertainGroup;
}
export interface PeriodOperation {
  depends_on: DependsOn4;
  id: Id9;
  inputs: Inputs3;
  kind: Kind7;
  parameters: PeriodParameters;
  version: Version4;
}
export interface PeriodParameters {
  ongoing_label: OngoingLabel;
  separator: Separator1;
}
export interface OngoingLabel {
  [k: string]: string;
}
export interface PreserveOperation {
  depends_on: DependsOn5;
  id: Id10;
  inputs: Inputs4;
  kind: Kind8;
  parameters: EmptyParameters;
  version: Version5;
}
export interface EmptyParameters {}
export interface Provenance {
  [k: string]: JsonValue;
}
export interface SourcePolicy {
  retain_original: RetainOriginal;
  retain_unmapped_facts: RetainUnmappedFacts;
}
export interface Style1 {
  bullets: Bullets;
  colors: Colors;
  focus: Focus;
  fonts: Fonts;
  footer: Footer;
  header: Header;
  page: Page;
  section_band: Band;
  text: Text1;
}
export interface Bullets {
  marker: Marker;
  marker_offset: MarkerOffset;
  marker_size: MarkerSize;
  text_offset: TextOffset;
}
export interface Colors {
  [k: string]: string;
}
export interface Focus {
  icon_catalog: IconCatalog;
  icon_fit: IconFit;
  icon_height: IconHeight;
  icon_width: IconWidth;
  icon_x: IconX;
  minimum_row_height: MinimumRowHeight;
  missing_icon: MissingIcon;
  text_x: TextX;
}
export interface Fonts {
  [k: string]: string;
}
export interface Footer {
  baseline_y: BaselineY;
  center_x: CenterX;
  repeat: Repeat;
  style: Style2;
  text: Text;
}
export interface Header {
  divider: Divider | null;
  logo: Logo | null;
  name_top: NameTop;
  overflow: Overflow;
  profession_top: ProfessionTop;
}
export interface Divider {
  color: Color;
  follow_header: FollowHeader;
  width: Width1;
  x1: X1;
  x2: X2;
  y: Y;
}
export interface Logo {
  asset: Asset;
  fit: Fit;
  height: Height;
  top: Top;
  width: Width2;
  x: X3;
}
export interface Page {
  body_bottom: BodyBottom;
  continuation_body_top: ContinuationBodyTop;
  first_body_top: FirstBodyTop;
  height: Height1;
  width: Width3;
}
export interface Band {
  background: Background1;
  heading_style: HeadingStyle;
  height: Height2;
  text_inset: TextInset;
}
export interface Text1 {
  [k: string]: TextStyle;
}
export interface TextStyle {
  color: Color1;
  font: Font;
  line_height: LineHeight;
  size: Size;
}
export interface TemplateIdentity {
  default_locale: DefaultLocale;
  id: Id11;
  name: Name;
  revision: Revision;
}
