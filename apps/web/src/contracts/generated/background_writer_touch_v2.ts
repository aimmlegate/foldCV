export type Cursor = number;
export type Actionid = string;
export type Actionid1 = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Clientmutationid = string;
export type Kind1 = "edit" | "undo" | "redo";
export type Originactionid = string | null;
export type Kind2 =
  "typing" | "composition" | "structure" | "panel" | "rewrite" | "reconciliation" | "cascade" | "undo" | "redo";
export type Projectid = string;
export type Schemaversion = 1;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Steps = [
  (
    | TemplatePutBlock
    | RemoveBlock
    | MoveBlock
    | TemplateReplaceInlineRange
    | PutRecord
    | RemoveRecord
    | PutExtension
    | RemoveExtension
    | PutRelation
    | RemoveRelation
    | PutManualScope
    | SetBuiltinManualScope
    | SetIssueState
    | SetAuthoredAnchors
    | RestoreAuthoredBlockPatch
    | SetManualScopeDisplays
    | PutTemplateSync
    | RemoveTemplateSync
  ),
  ...(
    | TemplatePutBlock
    | RemoveBlock
    | MoveBlock
    | TemplateReplaceInlineRange
    | PutRecord
    | RemoveRecord
    | PutExtension
    | RemoveExtension
    | PutRelation
    | RemoveRelation
    | PutManualScope
    | SetBuiltinManualScope
    | SetIssueState
    | SetAuthoredAnchors
    | RestoreAuthoredBlockPatch
    | SetManualScopeDisplays
    | PutTemplateSync
    | RemoveTemplateSync
  )[]
];
export type Afterid = string | null;
export type Beforerevision = number | null;
export type Block =
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
  | TemplateSectionBlock;
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
export type Id1 = string;
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
export type Id2 = string;
export type Kind3 = "citation";
export type Recordid3 = string;
export type Fieldkey2 = string;
export type Id3 = string;
export type Kind4 = "field_binding";
export type Recordid4 = string;
export type Id4 = string;
export type Kind5 = "working_owner";
export type Recordid5 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id5 = string;
export type Kind6 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision1 = number;
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
export type Id6 = string;
export type Alignment2 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Height = number;
export type Width = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision2 = number;
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
export type Id7 = string;
export type Revision3 = number;
export type Rowspan = number;
export type Cells = TemplateTableCell[];
export type Id8 = string;
export type Rows = TemplateTableRow[];
export type Id9 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision4 = number;
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
export type Id10 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision5 = number;
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
export type Id11 = string;
export type Backgroundcolor4 = string;
export type Language = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision6 = number;
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
export type Id12 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision7 = number;
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
export type Id13 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision8 = number;
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
export type Id14 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision9 = number;
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
export type Id15 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start1 = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision10 = number;
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
export type Id16 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision11 = number;
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
export type Id17 = string;
export type Alignment7 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision12 = number;
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
export type Id18 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision13 = number;
export type Type16 = "paragraph";
export type Keepchildren = boolean;
export type Kind7 = "put_block";
export type Parentid = string;
export type Beforerevision1 = number;
export type Blockid = string;
export type Kind8 = "remove_block";
export type Afterid1 = string | null;
export type Beforerevision2 = number;
export type Blockid1 = string;
export type Kind9 = "move_block";
export type Parentid1 = string;
export type Beforerevision3 = number;
export type Blockid2 = string;
export type Cellid2 = string | null;
export type Content14 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End1 = number;
export type Field = "content" | "caption";
export type Flankbindings = FlankBinding[] | null;
export type Fragmentid1 = string;
export type Role = "prefix" | "suffix";
export type Source = FieldFlankSource | ManualScopeFlankSource;
export type Bindingid1 = string;
export type Kind10 = "field";
export type Fragmentid2 = string;
export type Kind11 = "manual_scope";
export type Sourceend = number;
export type Sourcestart = number;
export type Kind12 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start2 = number;
export type Beforerevision4 = number | null;
export type Kind13 = "put_record";
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
export type Id19 = string;
export type Kind14 = "candidate";
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
export type Id20 = string;
export type Kind15 = "detail";
export type Label = string;
export type Origin1 = "source" | "user";
export type Revision16 = number;
export type Usercorrected2 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id21 = string;
export type Kind16 = "employment";
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
export type Id22 = string;
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
export type Id23 = string;
export type Jobid = string;
export type Kind17 = "subproject";
export type Origin3 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision21 = number;
export type Usercorrected6 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id24 = string;
export type Jobid1 = string | null;
export type Kind18 = "technology";
export type Origin4 = "source" | "user";
export type Revision22 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected7 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id25 = string;
export type Kind19 = "education";
export type Origin5 = "source" | "user";
export type Revision23 = number;
export type Usercorrected8 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id26 = string;
export type Kind20 = "language";
export type Origin6 = "source" | "user";
export type Revision24 = number;
export type Usercorrected9 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id27 = string;
export type Kind21 = "certification";
export type Origin7 = "source" | "user";
export type Revision25 = number;
export type Usercorrected10 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id28 = string;
export type Jobid2 = string | null;
export type Kind22 = "claim";
export type Origin8 = "source" | "user";
export type Revision26 = number;
export type Subprojectid1 = string | null;
export type Usercorrected11 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id29 = string;
export type Jobid3 = string | null;
export type Kind23 = "metric";
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
export type Id30 = string;
export type Jobid4 = string | null;
export type Kind24 = "leadership";
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
export type Id31 = string;
export type Kind25 = "unresolved";
export type Origin11 = "source" | "user";
export type Revision31 = number;
export type Status5 = "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Beforerevision5 = number;
export type Kind26 = "remove_record";
export type Recordid6 = string;
export type Beforerevision6 = number | null;
export type Kind27 = "put_extension";
export type Active = boolean;
export type Admissionreceiptids = string[];
export type Evidence15 = SourceSpan[];
export type Fieldkey3 = string;
export type Id32 = string;
export type Manualscopeid = string | null;
export type Observationids = string[];
export type Origin12 = "model" | "source" | "human";
export type Rawinput = string;
export type Revision32 = number;
export type State = "admitted" | "human_raw" | "pending_manual" | "uncertain";
export type JsonValue = unknown;
export type Usercorrected17 = boolean;
export type Cells1 = ExtensionCell[];
export type Copyofrecordid = string | null;
export type Id33 = string;
export type Itemhandle1 = string;
export type Observationids1 = string[];
export type Active1 = boolean;
export type Id34 = string;
export type Kind28 = "owned_by" | "extension_of" | "related_to";
export type Revision33 = number;
export type Subjectid = string;
export type Targetid = string;
export type Relations = Relation[];
export type Revision34 = number;
export type Schemaversion1 = 1;
export type Semanticschemahash = string;
export type Semantictype = string;
export type Beforerevision7 = number;
export type Kind29 = "remove_extension";
export type Recordid7 = string;
export type Beforerevision8 = number | null;
export type Kind30 = "put_relation";
export type Beforerevision9 = number;
export type Kind31 = "remove_relation";
export type Relationid = string;
export type Kind32 = "put_manual_scope";
export type Actionid2 = string;
export type Blockids = string[];
export type Cellids = string[];
export type Id35 = string;
export type Rawinput1 = string;
export type Afterscopeid = string | null;
export type Beforescopeid = string | null;
export type Cellid3 = string;
export type Kind33 = "set_builtin_manual_scope";
export type Actionid3 = string;
export type Afterlifecycleid = string;
export type Afterstate = "active" | "retired";
export type Beforelifecycleid = string;
export type Beforestate = "active" | "retired";
export type Importedfingerprint = string;
export type Issueid = string;
export type Kind34 = "set_issue_state";
export type Afterblockids = string[];
export type Beforeblockids = string[];
export type Kind35 = "set_authored_anchors";
export type Target = IssueAnchorTarget | CoverageAnchorTarget;
export type Beforelifecycleid1 = string;
export type Beforestate1 = "active" | "retired";
export type Importedfingerprint1 = string;
export type Issueid1 = string;
export type Kind36 = "issue";
export type Coverageidentityhash = string;
export type Coverageindex = number;
export type Coveragesequencehash = string;
export type Kind37 = "coverage";
export type Aftersemantichash = string;
export type Beforerevision10 = number;
export type Beforesemantichash = string;
export type Blockid3 = string;
export type Kind38 = "restore_authored_block_patch";
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Patch = [
  PatchSet | PatchInsert | PatchRemove | PatchSpliceText,
  ...(PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[]
];
export type Kind39 = "set";
export type Pointer = string;
export type Valuewire = string;
export type Kind40 = "insert";
export type Pointer1 = string;
export type Valuewire1 = string;
export type Kind41 = "remove";
export type Pointer2 = string;
export type Beforetexthash = string;
export type End2 = number;
export type Kind42 = "splice_text";
export type Pointer3 = string;
export type Start3 = number;
export type Text4 = string;
export type Blockid4 = string;
export type Cellid4 = string | null;
export type Field1 = "content" | "caption";
export type Inlineindex = number;
export type After = ScopeDisplayBinding | LiteralDisplayBinding;
export type Fragmentid3 = string;
export type Kind43 = "manual_scope";
export type Occurrenceid3 = string;
export type Scopeid1 = string;
export type Kind44 = "literal";
export type Beforehash = string;
/**
 * @maxItems 1000
 */
export type Assignments = ScopeDisplayAssignment[];
export type Kind45 = "set_manual_scope_displays";
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Activecellids = [string, ...string[]];
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Fragments = [ScopeDisplayFragment, ...ScopeDisplayFragment[]];
export type Blockid5 = string;
export type Cellid5 = string | null;
export type Field2 = "content" | "caption";
export type Fragmenthash = string;
export type Fragmentid4 = string;
export type Occurrenceid4 = string;
export type Scopehash = string;
export type Scopeid2 = string;
/**
 * @maxItems 1000
 */
export type Sources = ScopeDisplaySource[];
export type Beforehash1 = string | null;
export type Aftersyncid = string | null;
export type Beforeaftersyncid = string | null;
export type Kind46 = "put_template_sync";
export type Aftersyncid1 = string | null;
export type Actionid4 = string;
export type Blockids1 = string[];
export type Dependencies1 = DependencyStamp[];
export type Errorcode = string | null;
export type Factids = string[];
export type Fieldkeys1 = string[];
export type Id36 = string;
export type Instruction = string | null;
export type Kind47 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Lifecycleid = string | null;
export type Beforeownerid = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Movedoccurrenceids = [string, ...string[]];
export type Proposedownerid = string;
export type Recordid8 = string;
export type Relationid1 = string | null;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Remainingoccurrenceids = [string, ...string[]];
/**
 * @maxItems 1000
 */
export type Proposedsteps = (
  | TemplatePutBlock
  | RemoveBlock
  | MoveBlock
  | TemplateReplaceInlineRange
  | PutRecord
  | RemoveRecord
  | PutExtension
  | RemoveExtension
  | PutRelation
  | RemoveRelation
  | PutManualScope
  | SetBuiltinManualScope
  | SetIssueState
  | SetAuthoredAnchors
  | RestoreAuthoredBlockPatch
  | SetManualScopeDisplays
)[];
export type Ready = boolean;
export type Beforelifecycleid2 = string;
export type Beforerecordhash = string;
export type Syncid = string;
export type Rewriteresult = string | null;
export type Rewritesource = string | null;
export type Schemaversion2 = 2;
export type Blockid6 = string;
export type Cellid6 = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids2 = [string, ...string[]];
export type Kind48 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Status6 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Beforehash2 = string;
export type Kind49 = "remove_template_sync";
export type Syncid1 = string;

export interface WriterTouchV2 {
  cursor: Cursor;
  mutation: TemplateMutationV1 | null;
}
export interface TemplateMutationV1 {
  actionId: Actionid;
  capture: ActionCapture;
  clientMutationId: Clientmutationid;
  history: HistoryCapture;
  kind: Kind2;
  projectId: Projectid;
  schemaVersion: Schemaversion;
  steps: Steps;
}
export interface ActionCapture {
  actionId: Actionid1;
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
export interface HistoryCapture {
  kind: Kind1;
  originActionId: Originactionid;
}
export interface TemplatePutBlock {
  afterId: Afterid;
  beforeRevision: Beforerevision;
  block: Block;
  keepChildren?: Keepchildren;
  kind: Kind7;
  parentId: Parentid;
}
export interface TemplateParagraphBlock {
  children: Children;
  content: Content13;
  id: Id18;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision13;
  type: Type16;
}
export interface TemplateHeadingBlock {
  children: Children1;
  content: Content12;
  id: Id17;
  presentation: AuthoredPresentation | null;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision12;
  type: Type15;
}
export interface TemplateBulletBlock {
  children: Children2;
  content: Content11;
  id: Id16;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision11;
  type: Type14;
}
export interface TemplateNumberedBlock {
  children: Children3;
  content: Content10;
  id: Id15;
  presentation: AuthoredPresentation | null;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision10;
  type: Type13;
}
export interface TemplateChecklistBlock {
  children: Children4;
  content: Content9;
  id: Id14;
  presentation: AuthoredPresentation | null;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision9;
  type: Type12;
}
export interface TemplateToggleBlock {
  children: Children5;
  content: Content8;
  id: Id13;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision8;
  type: Type11;
}
export interface TemplateQuoteBlock {
  children: Children6;
  content: Content7;
  id: Id12;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision7;
  type: Type10;
}
export interface TemplateCodeBlock {
  children: Children7;
  content: Content6;
  id: Id11;
  presentation: AuthoredPresentation | null;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision6;
  type: Type9;
}
export interface TemplateDividerBlock {
  children: Children8;
  content: Content5;
  id: Id10;
  presentation: AuthoredPresentation | null;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision5;
  type: Type8;
}
export interface TemplateTableBlock {
  children: Children9;
  content: TemplateTableContent;
  id: Id9;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision4;
  type: Type7;
}
export interface TemplateImageBlock {
  children: Children10;
  content: Content3;
  id: Id6;
  presentation: AuthoredPresentation | null;
  props: TemplateImageProps;
  provenance: Provenance1;
  revision: Revision2;
  type: Type6;
}
export interface TemplateSectionBlock {
  children: Children11;
  content: Content;
  id: Id1;
  presentation: AuthoredPresentation | null;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision1;
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
  id: Id2;
  kind: Kind3;
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
  id: Id3;
  kind: Kind4;
  recordId: Recordid4;
}
export interface WorkingOwnership {
  id: Id4;
  kind: Kind5;
  recordId: Recordid5;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id5;
  kind: Kind6;
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
  id: Id8;
}
export interface TemplateTableCell {
  alignment?: Alignment3;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content4;
  id: Id7;
  revision: Revision3;
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
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid;
  kind: Kind8;
}
export interface MoveBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision2;
  blockId: Blockid1;
  kind: Kind9;
  parentId: Parentid1;
}
export interface TemplateReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid2;
  cellId: Cellid2;
  content: Content14;
  end: End1;
  field: Field;
  flankBindings?: Flankbindings;
  kind: Kind12;
  start: Start2;
}
export interface FlankBinding {
  fragmentId: Fragmentid1;
  role: Role;
  source: Source;
  sourceEnd: Sourceend;
  sourceStart: Sourcestart;
}
export interface FieldFlankSource {
  bindingId: Bindingid1;
  kind: Kind10;
}
export interface ManualScopeFlankSource {
  fragmentId: Fragmentid2;
  kind: Kind11;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind13;
  record: Record;
}
export interface CandidateRecord {
  evidence: Evidence2;
  id: Id19;
  kind: Kind14;
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
  id: Id20;
  kind: Kind15;
  label: Label;
  origin: Origin1;
  revision: Revision16;
  userCorrected?: Usercorrected2;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence4;
  id: Id21;
  kind: Kind16;
  origin: Origin2;
  periods: Periods;
  revision: Revision20;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected5;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence5;
  id: Id22;
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
  id: Id23;
  jobId: Jobid;
  kind: Kind17;
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
  experience?: WorkingFieldStr;
  id: Id24;
  jobId: Jobid1;
  kind: Kind18;
  origin: Origin4;
  revision: Revision22;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected7;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id25;
  institution: WorkingFieldStr;
  kind: Kind19;
  origin: Origin5;
  qualification: WorkingFieldStr;
  revision: Revision23;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected8;
}
export interface LanguageRecord {
  evidence: Evidence9;
  id: Id26;
  kind: Kind20;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin6;
  revision: Revision24;
  userCorrected?: Usercorrected9;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence10;
  id: Id27;
  issuer: WorkingFieldStr;
  kind: Kind21;
  name: WorkingFieldStr;
  origin: Origin7;
  revision: Revision25;
  userCorrected?: Usercorrected10;
}
export interface ClaimRecord {
  evidence: Evidence11;
  id: Id28;
  jobId: Jobid2;
  kind: Kind22;
  origin: Origin8;
  revision: Revision26;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected11;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence12;
  id: Id29;
  jobId: Jobid3;
  kind: Kind23;
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
  id: Id30;
  jobId: Jobid4;
  kind: Kind24;
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
  id: Id31;
  kind: Kind25;
  origin: Origin11;
  revision: Revision31;
  status: Status5;
  userCorrected?: Usercorrected16;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind26;
  recordId: Recordid6;
}
export interface PutExtension {
  beforeRevision: Beforerevision6;
  kind: Kind27;
  record: ExtensionRecord;
}
export interface ExtensionRecord {
  active: Active;
  cells: Cells1;
  copyOfRecordId?: Copyofrecordid;
  id: Id33;
  itemHandle: Itemhandle1;
  observationIds: Observationids1;
  relations: Relations;
  revision: Revision34;
  schemaVersion: Schemaversion1;
  semanticSchemaHash: Semanticschemahash;
  semanticType: Semantictype;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence15;
  fieldKey: Fieldkey3;
  id: Id32;
  manualScopeId: Manualscopeid;
  observationIds: Observationids;
  origin: Origin12;
  rawInput: Rawinput;
  revision: Revision32;
  state: State;
  typedValue: JsonValue;
  userCorrected: Usercorrected17;
}
export interface Relation {
  active: Active1;
  id: Id34;
  kind: Kind28;
  revision: Revision33;
  subjectId: Subjectid;
  targetId: Targetid;
}
export interface RemoveExtension {
  beforeRevision: Beforerevision7;
  kind: Kind29;
  recordId: Recordid7;
}
export interface PutRelation {
  beforeRevision: Beforerevision8;
  kind: Kind30;
  relation: Relation;
}
export interface RemoveRelation {
  beforeRevision: Beforerevision9;
  kind: Kind31;
  relationId: Relationid;
}
export interface PutManualScope {
  kind: Kind32;
  scope: ManualEditScope;
}
export interface ManualEditScope {
  actionId: Actionid2;
  blockIds: Blockids;
  cellIds: Cellids;
  id: Id35;
  rawInput: Rawinput1;
}
export interface SetBuiltinManualScope {
  afterScopeId: Afterscopeid;
  beforeScopeId: Beforescopeid;
  cellId: Cellid3;
  kind: Kind33;
}
export interface SetIssueState {
  actionId: Actionid3;
  afterLifecycleId: Afterlifecycleid;
  afterState: Afterstate;
  beforeLifecycleId: Beforelifecycleid;
  beforeState: Beforestate;
  importedFingerprint: Importedfingerprint;
  issueId: Issueid;
  kind: Kind34;
}
export interface SetAuthoredAnchors {
  afterBlockIds: Afterblockids;
  beforeBlockIds: Beforeblockids;
  kind: Kind35;
  target: Target;
}
export interface IssueAnchorTarget {
  beforeLifecycleId: Beforelifecycleid1;
  beforeState: Beforestate1;
  importedFingerprint: Importedfingerprint1;
  issueId: Issueid1;
  kind: Kind36;
}
export interface CoverageAnchorTarget {
  coverageIdentityHash: Coverageidentityhash;
  coverageIndex: Coverageindex;
  coverageSequenceHash: Coveragesequencehash;
  kind: Kind37;
}
export interface RestoreAuthoredBlockPatch {
  afterSemanticHash: Aftersemantichash;
  beforeRevision: Beforerevision10;
  beforeSemanticHash: Beforesemantichash;
  blockId: Blockid3;
  kind: Kind38;
  patch: Patch;
}
export interface PatchSet {
  kind: Kind39;
  pointer: Pointer;
  valueWire: Valuewire;
}
export interface PatchInsert {
  kind: Kind40;
  pointer: Pointer1;
  valueWire: Valuewire1;
}
export interface PatchRemove {
  kind: Kind41;
  pointer: Pointer2;
}
export interface PatchSpliceText {
  beforeTextHash: Beforetexthash;
  end: End2;
  kind: Kind42;
  pointer: Pointer3;
  start: Start3;
  text: Text4;
}
export interface SetManualScopeDisplays {
  assignments: Assignments;
  kind: Kind45;
  sources: Sources;
}
export interface ScopeDisplayAssignment {
  address: ScopeDisplayAddress;
  after: After;
  beforeHash: Beforehash;
}
export interface ScopeDisplayAddress {
  blockId: Blockid4;
  cellId: Cellid4;
  field: Field1;
  inlineIndex: Inlineindex;
}
export interface ScopeDisplayBinding {
  fragmentId: Fragmentid3;
  kind: Kind43;
  occurrenceId: Occurrenceid3;
  scopeId: Scopeid1;
}
export interface LiteralDisplayBinding {
  kind: Kind44;
}
export interface ScopeDisplaySource {
  activeCellIds: Activecellids;
  fragments: Fragments;
  occurrenceId: Occurrenceid4;
  scopeHash: Scopehash;
  scopeId: Scopeid2;
}
export interface ScopeDisplayFragment {
  blockId: Blockid5;
  cellId: Cellid5;
  field: Field2;
  fragmentHash: Fragmenthash;
  fragmentId: Fragmentid4;
}
export interface PutTemplateSync {
  beforeHash: Beforehash1;
  historyPlacement?: TemplateSyncHistoryPlacement | null;
  kind: Kind46;
  placement?: TemplateSyncPlacement | null;
  record: TemplateSyncWrite;
}
export interface TemplateSyncHistoryPlacement {
  afterSyncId: Aftersyncid;
  beforeAfterSyncId: Beforeaftersyncid;
}
export interface TemplateSyncPlacement {
  afterSyncId: Aftersyncid1;
}
export interface TemplateSyncWrite {
  actionId: Actionid4;
  blockIds: Blockids1;
  capture: ActionCapture | null;
  dependencies: Dependencies1;
  errorCode: Errorcode;
  factIds: Factids;
  fieldKeys: Fieldkeys1;
  id: Id36;
  instruction?: Instruction;
  kind?: Kind47;
  lifecycleId?: Lifecycleid;
  ownershipConflict: TemplateOwnershipConflict | null;
  proposedSteps?: Proposedsteps;
  ready?: Ready;
  resolutionOf?: TemplateSyncResolution | null;
  rewriteResult?: Rewriteresult;
  rewriteSource?: Rewritesource;
  schemaVersion: Schemaversion2;
  selection?: RichSelection | null;
  status: Status6;
}
export interface TemplateOwnershipConflict {
  beforeOwnerId: Beforeownerid;
  movedOccurrenceIds: Movedoccurrenceids;
  proposedOwnerId: Proposedownerid;
  recordId: Recordid8;
  relationId: Relationid1;
  remainingOccurrenceIds: Remainingoccurrenceids;
}
export interface TemplateSyncResolution {
  beforeLifecycleId: Beforelifecycleid2;
  beforeRecordHash: Beforerecordhash;
  syncId: Syncid;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids2;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind48;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid6;
  cellId: Cellid6;
  offset: Offset;
}
export interface RemoveTemplateSync {
  beforeHash: Beforehash2;
  kind: Kind49;
  syncId: Syncid1;
}
