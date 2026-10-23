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
export type Band = true | null;
/**
 * @minItems 1
 */
export type Blocks2 = [string, ...string[]];
export type Icon = string | null;
export type Links = string[];
export type Style = string;
export type Fonts = string[];
export type Icons = string[];
export type Alignment1 = ("left" | "center" | "right" | "justify") | null;
export type Color1 = string;
export type Bold1 = string | null;
export type Bolditalic = string | null;
export type Italic1 = string | null;
export type Regular = string | null;
export type Lineheight = number;
export type Size1 = number;
export type Capabilities = string[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id = "header" | "sidebar" | "main";
export type Width = number;
export type X = number;
export type Regions = Region[];
export type Order = number;
export type Region1 = "header" | "sidebar" | "main";
export type Renderinputversion = 1;
export type Schemaversion = 1;
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
export type Color2 = string;
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
export type Background = string;
export type HeadingStyle = string;
export type Height2 = number;
export type TextInset = number;
export type Color3 = string;
export type Font1 = string;
export type LineHeight = number;
export type Size2 = number;
export type FallbackStyle = string | null;
export type Heading = "none" | "plain" | "band";
export type Inset = number;
export type ItemGap = number;
export type Mode = "object" | "items";
export type Background1 = string | null;
export type DetailStyle = string | null;
export type ExperienceField = string | null;
export type Field = string | null;
export type Fields = string[];
export type HeaderSlot = ("name" | "profession") | null;
export type ItemField = string | null;
export type NameField = string | null;
export type Separator = string;
export type Style3 = string;
export type Type = "text" | "join_fields" | "join_items" | "bullets" | "tags" | "period" | "link" | "focus_entry";
export type UrlField = string | null;
export type Nodes = ViewNode[];
export type Schemaversion1 = 1;
export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash1 = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;

export interface TemplatePresentationV1 {
  blocks: Blocks;
  editor?: EditorPlanV1 | null;
  recipe: CompiledRecipe;
  schemaVersion: Schemaversion1;
  snapshot: TemplateSnapshotIdentity;
}
export interface Blocks {
  [k: string]: AuthoredPresentation;
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
/**
 * Python's presentation decisions for the mounted editor; the editor only applies them.
 */
export interface EditorPlanV1 {
  blocks: Blocks1;
  fonts: Fonts;
  icons: Icons;
  styles: Styles;
}
export interface Blocks1 {
  [k: string]: EditorBlock;
}
export interface EditorBlock {
  band?: Band;
  focus?: EditorFocus | null;
  inline?: Inline;
  links?: Links;
  style: Style;
}
export interface EditorFocus {
  blocks: Blocks2;
  icon: Icon;
}
export interface Inline {
  [k: string]: string;
}
export interface Styles {
  [k: string]: EditorStyle;
}
export interface EditorStyle {
  alignment: Alignment1;
  color: Color1;
  faces: EditorFaces;
  lineHeight: Lineheight;
  size: Size1;
}
export interface EditorFaces {
  bold: Bold1;
  boldItalic: Bolditalic;
  italic: Italic1;
  regular: Regular;
}
export interface CompiledRecipe {
  capabilities: Capabilities;
  layout: Layout;
  placements: Placements;
  renderInputVersion: Renderinputversion;
  schemaVersion: Schemaversion;
  style: Style1;
  views: Views;
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
export interface Region {
  flow: Flow;
  id: Id;
  width: Width;
  x: X;
}
export interface Placements {
  [k: string]: Placement;
}
export interface Placement {
  order: Order;
  region: Region1;
}
export interface Style1 {
  bullets: Bullets;
  colors: Colors;
  focus: Focus;
  fonts: Fonts1;
  footer: Footer;
  header: Header;
  page: Page;
  section_band: Band1;
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
export interface Fonts1 {
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
  color: Color2;
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
export interface Band1 {
  background: Background;
  heading_style: HeadingStyle;
  height: Height2;
  text_inset: TextInset;
}
export interface Text1 {
  [k: string]: TextStyle;
}
export interface TextStyle {
  color: Color3;
  font: Font1;
  line_height: LineHeight;
  size: Size2;
}
export interface Views {
  [k: string]: View;
}
export interface View {
  fallback_style?: FallbackStyle;
  heading: Heading;
  inset: Inset;
  item_gap: ItemGap;
  mode: Mode;
  nodes: Nodes;
  title: Title;
}
export interface ViewNode {
  background?: Background1;
  detail_style?: DetailStyle;
  experience_field?: ExperienceField;
  field?: Field;
  fields?: Fields;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label;
  name_field?: NameField;
  prefix?: Prefix;
  separator?: Separator;
  style: Style3;
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
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision;
  factsHash: Factshash;
  packageHash: Packagehash1;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
