export type Baserevision = number;
export type Editortoken = string;
export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Clientmutationid = string;
/**
 * @minItems 1
 * @maxItems 1
 */
export type Operations = [
  | ReplaceText
  | SetMarks
  | SplitBlock
  | MergeBlocks
  | InsertParagraph
  | CopyBlocks
  | CopyFragment
  | PasteInline
  | PasteBlocks
  | MoveBlock
  | RemoveOccurrences
  | DeleteEntity
  | BuiltinPanel
  | FormatBlocks
  | ResolveTemplateSync
  | SetLinkTarget
];
export type Kind1 = "replace_text";
export type Opid = string;
export type Beforerevision = number;
export type Blockid = string;
export type Cellid = string | null;
export type End = number;
export type Field = "content" | "caption";
export type Insertiontarget = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
export type Bindingid = string;
export type Kind2 = "field";
export type Kind3 = "literal";
export type Fragmentid = string;
export type Kind4 = "manual_scope";
export type Start = number;
export type Backgroundcolor = string;
export type Bold = boolean;
export type Code = boolean;
export type Italic = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text = string;
export type Kind5 = "set_marks";
export type Opid1 = string;
export type Beforerevision1 = number;
export type Blockid1 = string;
export type Kind6 = "split_block";
export type Offset = number;
export type Opid2 = string;
export type Kind7 = "merge_blocks";
export type Leadingid = string;
export type Leadingrevision = number;
export type Opid3 = string;
export type Trailingid = string;
export type Trailingrevision = number;
export type Contextblockid = string;
export type Contextrevision = number;
export type Kind8 = "insert_paragraph";
export type Opid4 = string;
export type Afterid = string | null;
export type Parentid = string;
export type Text1 = string;
export type Kind9 = "copy_blocks";
export type Opid5 = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Sources = [BlockTarget, ...BlockTarget[]];
export type Beforerevision2 = number;
export type Blockid2 = string;
export type Kind10 = "copy_fragment";
export type Opid6 = string;
export type Kind11 = "paste_inline";
export type Opid7 = string;
export type Source = SameProjectClipboard | LiteralPaste;
export type Clipboardcaptureid = string;
export type Kind12 = "same_project";
export type Text2 = string;
export type Type = "text";
export type Content1 = StyledText[];
export type Href = string;
export type Type1 = "link";
export type Content = (StyledText | Hyperlink)[];
export type Kind13 = "literal";
export type Kind14 = "paste_blocks";
export type Opid8 = string;
export type Beforerevision3 = number;
export type Blockid3 = string;
export type Kind15 = "move_block";
export type Opid9 = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Blocks = [BlockTarget, ...BlockTarget[]];
export type Kind16 = "remove_occurrences";
export type Opid10 = string;
export type Beforerevision4 = number;
export type Kind17 = "delete_entity";
export type Opid11 = string;
export type Recordid = string;
export type Beforerecordid = string | null;
export type Documentrevision = number;
export type Factsrevision = number;
export type Jobid = string | null;
export type Operation =
  | "add"
  | "edit"
  | "remove"
  | "add_period"
  | "remove_period"
  | "clear_technologies"
  | "add_to_focus"
  | "remove_from_focus"
  | "move_technology"
  | "move_focus";
export type Periodid = string | null;
export type Recordid1 = string | null;
export type Recordkind = ("candidate" | "employment" | "technology" | "education" | "language" | "claim") | null;
export type Kind18 = "builtin_panel";
export type Opid12 = string;
export type Contextblockid1 = string;
export type Kind19 = "format_blocks";
export type Opid13 = string;
export type BlockFormatPatch =
  | {
      [k: string]: unknown;
    }
  | {
      [k: string]: unknown;
    }
  | {
      [k: string]: unknown;
    }
  | {
      [k: string]: unknown;
    };
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Targets = [BlockTarget, ...BlockTarget[]];
export type Beforelifecycleid = string;
export type Beforerecordhash = string;
export type Kind20 = "resolve_template_sync";
export type Opid14 = string;
export type Syncid = string;
export type Beforerevision5 = number;
export type Blockid4 = string;
export type Href1 = string;
export type Kind21 = "set_link_target";
export type Occurrenceid = string;
export type Opid15 = string;
export type Schemaversion = 1;
export type Documenthash = string;
export type Documentrevision1 = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;

export interface EditRequestV1 {
  baseRevision: Baserevision;
  editorToken: Editortoken;
  preparation: TemplateEditPreparationV1;
}
export interface TemplateEditPreparationV1 {
  capture: ActionCapture;
  clientMutationId: Clientmutationid;
  operations: Operations;
  schemaVersion: Schemaversion;
  snapshot: TemplateSnapshotIdentity;
}
export interface ActionCapture {
  actionId: Actionid;
  actionToken: Actiontoken;
  dependencies: Dependencies;
  sessionId: Sessionid;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind;
  revision: Revision;
}
export interface ReplaceText {
  kind: Kind1;
  opId: Opid;
  range: AuthoredRange;
  styles: InlineStyles;
  text: Text;
}
export interface AuthoredRange {
  beforeRevision: Beforerevision;
  blockId: Blockid;
  cellId: Cellid;
  end: End;
  field: Field;
  insertionTarget?: Insertiontarget;
  start: Start;
}
export interface FieldInsertionTarget {
  bindingId: Bindingid;
  kind: Kind2;
}
export interface LiteralInsertionTarget {
  kind: Kind3;
}
export interface ManualScopeInsertionTarget {
  fragmentId: Fragmentid;
  kind: Kind4;
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
export interface SetMarks {
  kind: Kind5;
  opId: Opid1;
  range: AuthoredRange;
  styles: InlineStyles;
}
export interface SplitBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid1;
  kind: Kind6;
  offset: Offset;
  opId: Opid2;
}
export interface MergeBlocks {
  kind: Kind7;
  leadingId: Leadingid;
  leadingRevision: Leadingrevision;
  opId: Opid3;
  trailingId: Trailingid;
  trailingRevision: Trailingrevision;
}
export interface InsertParagraph {
  contextBlockId: Contextblockid;
  contextRevision: Contextrevision;
  kind: Kind8;
  opId: Opid4;
  placement: AuthoredPlacement;
  text: Text1;
}
export interface AuthoredPlacement {
  afterId: Afterid;
  parentId: Parentid;
}
export interface CopyBlocks {
  kind: Kind9;
  opId: Opid5;
  placement: AuthoredPlacement;
  sources: Sources;
}
export interface BlockTarget {
  beforeRevision: Beforerevision2;
  blockId: Blockid2;
}
export interface CopyFragment {
  kind: Kind10;
  opId: Opid6;
  placement: AuthoredPlacement;
  source: AuthoredRange;
}
export interface PasteInline {
  destination: AuthoredRange;
  kind: Kind11;
  opId: Opid7;
  source: Source;
}
export interface SameProjectClipboard {
  clipboardCaptureId: Clipboardcaptureid;
  kind: Kind12;
}
export interface LiteralPaste {
  content: Content;
  kind: Kind13;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text2;
  type: Type;
}
export interface Hyperlink {
  content: Content1;
  href: Href;
  type: Type1;
}
export interface PasteBlocks {
  kind: Kind14;
  opId: Opid8;
  placement: AuthoredPlacement;
  source: SameProjectClipboard;
}
export interface MoveBlock {
  beforeRevision: Beforerevision3;
  blockId: Blockid3;
  kind: Kind15;
  opId: Opid9;
  placement: AuthoredPlacement;
}
export interface RemoveOccurrences {
  blocks: Blocks;
  kind: Kind16;
  opId: Opid10;
}
export interface DeleteEntity {
  beforeRevision: Beforerevision4;
  kind: Kind17;
  opId: Opid11;
  recordId: Recordid;
}
export interface BuiltinPanel {
  command: RichPanelRequest;
  kind: Kind18;
  opId: Opid12;
  placementContext?: PanelPlacementContext | null;
}
export interface RichPanelRequest {
  beforeRecordId?: Beforerecordid;
  capture: ActionCapture;
  documentRevision: Documentrevision;
  factsRevision: Factsrevision;
  jobId?: Jobid;
  operation: Operation;
  periodId?: Periodid;
  recordId?: Recordid1;
  recordKind?: Recordkind;
  values?: Values;
}
export interface Values {
  [k: string]: string;
}
export interface PanelPlacementContext {
  contextBlockId: Contextblockid1;
  placement: AuthoredPlacement;
}
export interface FormatBlocks {
  kind: Kind19;
  opId: Opid13;
  patch: BlockFormatPatch;
  targets: Targets;
}
export interface ResolveTemplateSync {
  beforeLifecycleId: Beforelifecycleid;
  beforeRecordHash: Beforerecordhash;
  kind: Kind20;
  opId: Opid14;
  syncId: Syncid;
}
/**
 * A bound link's URL: its URL cell and target change together; the label stays its own cell.
 */
export interface SetLinkTarget {
  beforeRevision: Beforerevision5;
  blockId: Blockid4;
  href: Href1;
  kind: Kind21;
  occurrenceId: Occurrenceid;
  opId: Opid15;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision1;
  factsHash: Factshash;
  packageHash: Packagehash;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
