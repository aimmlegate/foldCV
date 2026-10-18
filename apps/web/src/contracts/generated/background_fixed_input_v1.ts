export type Actionid = string | null;
export type Connectionepoch = string;
export type Id = string;
export type Lineage = string;
export type Projectid = string;
export type Requestepoch = number;
export type Requestid = string;
export type Model = string;
export type Actionid1 = string;
export type Blockids = string[];
export type Fingerprint = string | null;
export type Id1 = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Errorcode = string | null;
export type Factids = string[];
export type Fieldkeys = string[];
export type Id2 = string;
export type Instruction = string | null;
export type Kind1 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Afterid = string | null;
export type Beforerevision = number | null;
export type Block =
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
  | SectionBlock;
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
export type Id3 = string;
export type Alignment = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Presentation = "standard" | "focus";
export type Recordid1 = string | null;
export type Textcolor1 = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text2 = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Fieldkeys1 = string[];
export type Id4 = string;
export type Kind2 = "citation";
export type Recordid2 = string;
export type Fieldkey1 = string;
export type Id5 = string;
export type Kind3 = "field_binding";
export type Recordid3 = string;
export type Id6 = string;
export type Kind4 = "working_owner";
export type Recordid4 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id7 = string;
export type Kind5 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision1 = number;
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
export type Id8 = string;
export type Alignment1 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height = number;
export type Width = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision2 = number;
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
export type Id9 = string;
export type Revision3 = number;
export type Rowspan = number;
export type Cells = TableCell[];
export type Id10 = string;
export type Id11 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision4 = number;
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
export type Id12 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision5 = number;
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
export type Id13 = string;
export type Backgroundcolor4 = string;
export type Language = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision6 = number;
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
export type Id14 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision7 = number;
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
export type Id15 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision8 = number;
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
export type Id16 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision9 = number;
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
export type Id17 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision10 = number;
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
export type Id18 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision11 = number;
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
export type Id19 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision12 = number;
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
export type Id20 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision13 = number;
export type Type14 = "paragraph";
export type Keepchildren = boolean;
export type Kind6 = "put_block";
export type Parentid = string;
export type Beforerevision1 = number;
export type Blockid = string;
export type Kind7 = "remove_block";
export type Afterid1 = string | null;
export type Beforerevision2 = number;
export type Blockid1 = string;
export type Kind8 = "move_block";
export type Parentid1 = string;
export type Beforerevision3 = number;
export type Blockid2 = string;
export type Cellid = string | null;
export type Content13 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End = number;
export type Field = "content" | "caption";
export type Kind9 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start1 = number;
export type Beforerevision4 = number | null;
export type Kind10 = "put_record";
export type Record =
  | CandidateRecord
  | DetailRecord
  | EmploymentRecord
  | SubprojectRecord
  | TechnologyRecord
  | EducationRecord
  | LanguageRecord
  | CertificationRecord
  | ClaimRecord
  | MetricRecord
  | LeadershipRecord
  | UnresolvedRecord;
export type Evidence2 = EvidenceSpan[];
export type Id21 = string;
export type Kind11 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision14 = number;
export type Status = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected = boolean;
export type Value = string | null;
export type Origin = "source" | "user";
export type Revision15 = number;
export type Usercorrected1 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence3 = EvidenceSpan[];
export type Id22 = string;
export type Kind12 = "detail";
export type Label = string;
export type Origin1 = "source" | "user";
export type Revision16 = number;
export type Usercorrected2 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id23 = string;
export type Kind13 = "employment";
export type Origin2 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision17 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected3 = boolean;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence5 = EvidenceSpan[];
export type Id24 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision18 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Value1 = boolean | null;
export type Revision19 = number;
export type Periods = WorkingPeriod[];
export type Revision20 = number;
export type Usercorrected5 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id25 = string;
export type Jobid = string;
export type Kind14 = "subproject";
export type Origin3 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision21 = number;
export type Usercorrected6 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id26 = string;
export type Jobid1 = string | null;
export type Kind15 = "technology";
export type Origin4 = "source" | "user";
export type Revision22 = number;
export type Subprojectid = string | null;
export type Usercorrected7 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id27 = string;
export type Kind16 = "education";
export type Origin5 = "source" | "user";
export type Revision23 = number;
export type Usercorrected8 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id28 = string;
export type Kind17 = "language";
export type Origin6 = "source" | "user";
export type Revision24 = number;
export type Usercorrected9 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id29 = string;
export type Kind18 = "certification";
export type Origin7 = "source" | "user";
export type Revision25 = number;
export type Usercorrected10 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id30 = string;
export type Jobid2 = string | null;
export type Kind19 = "claim";
export type Origin8 = "source" | "user";
export type Revision26 = number;
export type Subprojectid1 = string | null;
export type Usercorrected11 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id31 = string;
export type Jobid3 = string | null;
export type Kind20 = "metric";
export type Origin9 = "source" | "user";
export type Revision27 = number;
export type Subprojectid2 = string | null;
export type Usercorrected12 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision28 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected13 = boolean;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence13 = EvidenceSpan[];
export type Id32 = string;
export type Jobid4 = string | null;
export type Kind21 = "leadership";
export type Origin10 = "source" | "user";
export type Revision29 = number;
export type Subprojectid3 = string | null;
export type Usercorrected14 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision30 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected15 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence14 = EvidenceSpan[];
export type Id33 = string;
export type Kind22 = "unresolved";
export type Origin11 = "source" | "user";
export type Revision31 = number;
export type Status5 = "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Beforerevision5 = number;
export type Kind23 = "remove_record";
export type Recordid5 = string;
/**
 * @maxItems 1000
 */
export type Proposedsteps = (PutBlock | RemoveBlock | MoveBlock | ReplaceInlineRange | PutRecord | RemoveRecord)[];
export type Ready = boolean;
export type Blockid3 = string;
export type Cellid1 = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids1 = [string, ...string[]];
export type Actionid2 = string;
export type Actiontoken = number;
export type Dependencies1 = DependencyStamp[];
export type Sessionid = string;
export type Kind24 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Status6 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Clientrequestid = string;
export type Command =
  FixedProcessingCommand | FixedCompletionCommand | FixedRewriteCommand | FixedPanelCommand | FixedRetryCommand;
export type Kind25 = "processing";
export type Kind26 = "completion";
/**
 * @maxItems 100
 */
export type Blockids2 = string[];
export type Interpret = boolean;
/**
 * @maxItems 100
 */
export type Movedids = string[];
export type Fieldkey2 = string;
export type Recordid6 = string;
export type Rootid = string;
/**
 * @maxItems 100
 */
export type Removedfields = FieldReference[];
/**
 * @maxItems 100
 */
export type Removedrecordids = string[];
export type Kind27 = "rewrite";
export type Instruction1 = string;
export type Kind28 = "panel";
/**
 * @minItems 1
 * @maxItems 100
 */
export type Recordids = [string, ...string[]];
export type Kind29 = "retry" | "resolve";
export type Syncid = string;
export type Lineage1 = string;
export type Requestepoch1 = number;
export type Schemaversion = 1;
export type Markdown = string;
export type Revision32 = number;
export type Sha256 = string;
export type Schemaversion1 = 1;
export type Sourcesha256 = string;
export type Syncid1 = string | null;
export type Createdat = string;
export type Documentrevision = number;
export type Clientmutationid = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
export type Mutationreplay = RichMutationReplay[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status7 = "complete" | "partial";
export type Code1 = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page = number | null;
export type Section = string;
export type Sourceid1 = string;
export type Unitid1 = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Records = (
  | CandidateRecord
  | DetailRecord
  | EmploymentRecord
  | SubprojectRecord
  | TechnologyRecord
  | EducationRecord
  | LanguageRecord
  | CertificationRecord
  | ClaimRecord
  | MetricRecord
  | LeadershipRecord
  | UnresolvedRecord
)[];
export type Revision33 = number;
export type Actionid3 = string;
export type Orderindex = number;
export type Recordid7 = string;
export type Revision34 = number;
export type Tombstones = RecordTombstone[];
export type Actionid4 = string | null;
export type Dependencies2 = DependencyStamp[];
export type Errorcode1 = string | null;
export type Id34 = string;
export type Kind30 =
  | "extract"
  | "assess_resume"
  | "normalize_semantics"
  | "draft_prose"
  | "render"
  | "project_save"
  | "rewrite_prose"
  | "reconcile_edits";
export type Status8 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Operations = RichOperation[];
export type Selectedinput = "text" | "file";
export type Selectedsourceid = string | null;
export type Byteref = string;
export type Bytesha256 = string;
export type Id35 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id36 = string;
export type Origin12 = "user";
export type Revision35 = number;
export type Text3 = string;
export type Unitid2 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision36 = number;
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id37 = string;
export type Column = number | null;
export type Index = number;
export type Kind31 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision37 = number;
export type Text4 = string;
export type Units = SourceUnit[];
export type Code2 = string;
export type Page1 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources = Source[];
export type Warnings1 = string[];
export type Height1 = number;
export type Id38 = string;
export type Mimetype1 = "image/png" | "image/jpeg";
export type Path = string;
export type Sha2561 = string;
export type Size = number;
export type Width1 = number;
export type Assets = LocalImageAsset[];
export type Createdat1 = string;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Regions = [RichRegion, RichRegion, RichRegion];
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
export type Id39 = string;
export type Revision38 = number;
export type Role = "header" | "sidebar" | "main";
export type Revision39 = number;
export type Schemaversion2 = 1;
export type Evidence15 = EvidenceSpan[];
export type Id40 = string;
export type Rawtext5 = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Blockids3 = string[];
export type Disposition1 = "placed" | "excluded";
export type Reason = string | null;
export type Sourceid2 = string;
export type Unitid3 = string;
export type Importcoverage = ImportCoverage[];
export type Operations1 = RichOperation[];
export type Projectid1 = string;
export type Documentrevision1 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id41 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision40 = number;
export type Schemaversion3 = 5;
export type Sources1 = Source[];
export type Path1 = string;
export type Sha2562 = string;
export type Size1 = number;
export type Assets1 = AssetRef[];
export type Contentpolicyversion = string;
export type Id42 = string;
export type Packagesha256 = string;
export type Version = string;
export type Projectid2 = string;
export type Projectrevision = number;
export type Schemaversion4 = 6;
export type Syncrecords = RichSyncRecord[];
export type Title = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;
export type Blockids4 = string[];
export type Code3 = string;
export type Count = number;
export type Sourceid3 = string;
export type Sourcerevision1 = number;
export type Unitid4 = string;
export type Unitrevision1 = number;
export type Evidence16 = Evidence17[];
export type Id43 = string;
export type Page2 = number | null;
export type Sourceid4 = string;
export type Locations = WarningLocation[];
export type Recordids1 = string[];
export type Warnings2 = RichWarning[];

export interface FixedInputV1 {
  actionId: Actionid;
  connectionEpoch: Connectionepoch;
  id: Id;
  identity: JobIdentity;
  model: Model;
  originalSync?: RichSyncRecord | null;
  request: JobFixedRequestV1;
  rules: Rules | null;
  schemaVersion: Schemaversion1;
  sourceSha256: Sourcesha256;
  syncId: Syncid1;
  workspace: WorkspaceV6;
}
export interface JobIdentity {
  lineage: Lineage;
  projectId: Projectid;
  requestEpoch: Requestepoch;
  requestId: Requestid;
}
export interface RichSyncRecord {
  actionId: Actionid1;
  blockIds: Blockids;
  dependencies: Dependencies;
  errorCode: Errorcode;
  factIds: Factids;
  fieldKeys: Fieldkeys;
  id: Id2;
  instruction?: Instruction;
  kind?: Kind1;
  proposedSteps?: Proposedsteps;
  ready?: Ready;
  selection?: RichSelection | null;
  status: Status6;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id1;
  kind: Kind;
  revision: Revision;
}
export interface PutBlock {
  afterId: Afterid;
  beforeRevision: Beforerevision;
  block: Block;
  keepChildren?: Keepchildren;
  kind: Kind6;
  parentId: Parentid;
}
export interface ParagraphBlock {
  children: Children;
  content: Content12;
  id: Id20;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision13;
  type: Type14;
}
export interface HeadingBlock {
  children: Children1;
  content: Content11;
  id: Id19;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision12;
  type: Type13;
}
export interface BulletBlock {
  children: Children2;
  content: Content10;
  id: Id18;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision11;
  type: Type12;
}
export interface NumberedBlock {
  children: Children3;
  content: Content9;
  id: Id17;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision10;
  type: Type11;
}
export interface ChecklistBlock {
  children: Children4;
  content: Content8;
  id: Id16;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision9;
  type: Type10;
}
export interface ToggleBlock {
  children: Children5;
  content: Content7;
  id: Id15;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision8;
  type: Type9;
}
export interface QuoteBlock {
  children: Children6;
  content: Content6;
  id: Id14;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision7;
  type: Type8;
}
export interface CodeBlock {
  children: Children7;
  content: Content5;
  id: Id13;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision6;
  type: Type7;
}
export interface DividerBlock {
  children: Children8;
  content: Content4;
  id: Id12;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision5;
  type: Type6;
}
export interface TableBlock {
  children: Children9;
  content: TableContent;
  id: Id11;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision4;
  type: Type5;
}
export interface ImageBlock {
  children: Children10;
  content: Content2;
  id: Id8;
  props: ImageProps;
  provenance: Provenance1;
  revision: Revision2;
  type: Type4;
}
export interface SectionBlock {
  children: Children11;
  content: Content;
  id: Id3;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision1;
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
  presentation?: Presentation;
  recordId: Recordid1;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence;
  fieldKeys: Fieldkeys1;
  id: Id4;
  kind: Kind2;
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
  id: Id5;
  kind: Kind3;
  recordId: Recordid3;
}
export interface WorkingOwnership {
  id: Id6;
  kind: Kind4;
  recordId: Recordid4;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id7;
  kind: Kind5;
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
  id: Id10;
}
export interface TableCell {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content3;
  id: Id9;
  revision: Revision3;
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
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid;
  kind: Kind7;
}
export interface MoveBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision2;
  blockId: Blockid1;
  kind: Kind8;
  parentId: Parentid1;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid2;
  cellId: Cellid;
  content: Content13;
  end: End;
  field: Field;
  kind: Kind9;
  start: Start1;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind10;
  record: Record;
}
export interface CandidateRecord {
  evidence: Evidence2;
  id: Id21;
  kind: Kind11;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin;
  revision: Revision15;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected1;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision14;
  status: Status;
  userCorrected?: Usercorrected;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence3;
  id: Id22;
  kind: Kind12;
  label: Label;
  origin: Origin1;
  revision: Revision16;
  userCorrected?: Usercorrected2;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence4;
  id: Id23;
  kind: Kind13;
  origin: Origin2;
  periods: Periods;
  revision: Revision20;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected5;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence5;
  id: Id24;
  present: WorkingFieldBool;
  revision: Revision19;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision17;
  status: Status1;
  userCorrected?: Usercorrected3;
  value: PartialDate | null;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision18;
  status: Status2;
  userCorrected?: Usercorrected4;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence6;
  id: Id25;
  jobId: Jobid;
  kind: Kind14;
  name: WorkingFieldStr;
  origin: Origin3;
  periods: Periods1;
  revision: Revision21;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence7;
  id: Id26;
  jobId: Jobid1;
  kind: Kind15;
  origin: Origin4;
  revision: Revision22;
  subprojectId: Subprojectid;
  userCorrected?: Usercorrected7;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id27;
  institution: WorkingFieldStr;
  kind: Kind16;
  origin: Origin5;
  qualification: WorkingFieldStr;
  revision: Revision23;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected8;
}
export interface LanguageRecord {
  evidence: Evidence9;
  id: Id28;
  kind: Kind17;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin6;
  revision: Revision24;
  userCorrected?: Usercorrected9;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence10;
  id: Id29;
  issuer: WorkingFieldStr;
  kind: Kind18;
  name: WorkingFieldStr;
  origin: Origin7;
  revision: Revision25;
  userCorrected?: Usercorrected10;
}
export interface ClaimRecord {
  evidence: Evidence11;
  id: Id30;
  jobId: Jobid2;
  kind: Kind19;
  origin: Origin8;
  revision: Revision26;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected11;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence12;
  id: Id31;
  jobId: Jobid3;
  kind: Kind20;
  origin: Origin9;
  revision: Revision27;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected12;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision28;
  status: Status3;
  userCorrected?: Usercorrected13;
  value: MetricValue | null;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipRecord {
  evidence: Evidence13;
  id: Id32;
  jobId: Jobid4;
  kind: Kind21;
  origin: Origin10;
  revision: Revision29;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected14;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision30;
  status: Status4;
  userCorrected?: Usercorrected15;
  value: LeadershipValue | null;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface UnresolvedRecord {
  category: Category;
  evidence: Evidence14;
  id: Id33;
  kind: Kind22;
  origin: Origin11;
  revision: Revision31;
  status: Status5;
  userCorrected?: Usercorrected16;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind23;
  recordId: Recordid5;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids1;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind24;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid3;
  cellId: Cellid1;
  offset: Offset;
}
export interface ActionCapture {
  actionId: Actionid2;
  actionToken: Actiontoken;
  dependencies: Dependencies1;
  sessionId: Sessionid;
}
export interface JobFixedRequestV1 {
  clientRequestId: Clientrequestid;
  command: Command;
  lineage: Lineage1;
  requestEpoch: Requestepoch1;
  schemaVersion: Schemaversion;
}
export interface FixedProcessingCommand {
  kind: Kind25;
}
export interface FixedCompletionCommand {
  kind: Kind26;
  request: RichCompletionRequest;
}
export interface RichCompletionRequest {
  blockIds: Blockids2;
  capture: ActionCapture;
  interpret?: Interpret;
  movedIds: Movedids;
  removedFields: Removedfields;
  removedRecordIds?: Removedrecordids;
}
export interface FieldReference {
  fieldKey: Fieldkey2;
  recordId: Recordid6;
  rootId: Rootid;
}
export interface FixedRewriteCommand {
  kind: Kind27;
  request: RichRewriteRequest;
}
export interface RichRewriteRequest {
  instruction: Instruction1;
  selection: RichSelection;
}
export interface FixedPanelCommand {
  kind: Kind28;
  request: RichPanelSyncRequest;
}
export interface RichPanelSyncRequest {
  capture: ActionCapture;
  recordIds: Recordids;
}
export interface FixedRetryCommand {
  capture: ActionCapture;
  kind: Kind29;
  syncId: Syncid;
}
export interface Rules {
  markdown: Markdown;
  revision: Revision32;
  sha256: Sha256;
}
export interface WorkspaceV6 {
  createdAt: Createdat;
  documentRevision: Documentrevision;
  formattingAsOf: PartialDate;
  mutationReplay: Mutationreplay;
  preDraft: RichPreDraft | null;
  project: ProjectV5 | null;
  projectId: Projectid2;
  projectRevision: Projectrevision;
  rulesUsed: Rules | null;
  schemaVersion: Schemaversion4;
  sourceObservedAt: PartialDate | null;
  syncRecords: Syncrecords;
  title: Title;
  titleManuallySet: Titlemanuallyset;
  updatedAt: Updatedat;
  warnings: Warnings2;
}
export interface RichMutationReplay {
  clientMutationId: Clientmutationid;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface RichPreDraft {
  facts: WorkingFacts;
  operations: Operations;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources;
  warnings: Warnings1;
}
export interface WorkingFacts {
  extraction?: ExtractionReport | null;
  records: Records;
  revision: Revision33;
  tombstones: Tombstones;
}
export interface ExtractionReport {
  counts: Counts;
  factCount: Factcount;
  recoveredRows: Recoveredrows;
  requestBytes: Requestbytes;
  status: Status7;
  unresolved: Unresolved;
}
export interface Counts {
  [k: string]: number;
}
export interface ExtractionIssue {
  code: Code1;
  page?: Page;
  section: Section;
  sourceId: Sourceid1;
  unitId: Unitid1;
}
export interface RecordTombstone {
  actionId: Actionid3;
  orderIndex: Orderindex;
  recordId: Recordid7;
  revision: Revision34;
}
export interface RichOperation {
  actionId: Actionid4;
  dependencies: Dependencies2;
  errorCode: Errorcode1;
  id: Id34;
  kind: Kind30;
  status: Status8;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id35;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision36;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id36;
  origin: Origin12;
  revision: Revision35;
  text: Text3;
  unitId: Unitid2;
}
export interface SourceUnit {
  disposition: Disposition;
  id: Id37;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision37;
  text: Text4;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind31;
  row: Row;
}
export interface SourceWarning {
  code: Code2;
  page?: Page1;
}
export interface ProjectV5 {
  assets: Assets;
  createdAt: Createdat1;
  document: RichDocumentV1;
  evidenceRecords: Evidencerecords;
  facts: WorkingFacts;
  importCoverage?: Importcoverage;
  operations: Operations1;
  projectId: Projectid1;
  renders: Renders;
  revision: Revision40;
  schemaVersion: Schemaversion3;
  sources: Sources1;
  template: TemplateManifest;
}
export interface LocalImageAsset {
  height: Height1;
  id: Id38;
  mimeType: Mimetype1;
  path: Path;
  sha256: Sha2561;
  size: Size;
  width: Width1;
}
export interface RichDocumentV1 {
  regions: Regions;
  revision: Revision39;
  schemaVersion: Schemaversion2;
}
export interface RichRegion {
  blocks: Blocks;
  id: Id39;
  revision: Revision38;
  role: Role;
}
export interface ImmutableFactEvidence {
  evidence: Evidence15;
  id: Id40;
  rawText: Rawtext5;
}
export interface ImportCoverage {
  blockIds: Blockids3;
  disposition: Disposition1;
  reason: Reason;
  sourceId: Sourceid2;
  unitId: Unitid3;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision1;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id41;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface TemplateManifest {
  assets: Assets1;
  contentPolicyVersion: Contentpolicyversion;
  id: Id42;
  packageSha256: Packagesha256;
  version: Version;
}
export interface AssetRef {
  path: Path1;
  sha256: Sha2562;
  size: Size1;
}
export interface RichWarning {
  blockIds: Blockids4;
  code: Code3;
  count?: Count;
  evidence: Evidence16;
  id: Id43;
  locations?: Locations;
  recordIds: Recordids1;
}
export interface Evidence17 {
  sourceId: Sourceid3;
  sourceRevision: Sourcerevision1;
  unitId: Unitid4;
  unitRevision: Unitrevision1;
}
export interface WarningLocation {
  page?: Page2;
  sourceId: Sourceid4;
}
