export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;
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
export type Actionid1 = string;
export type Clientmutationid1 = string;
export type Kind1 = "edit" | "undo" | "redo";
export type Originactionid = string | null;
export type Kind2 =
  "typing" | "composition" | "structure" | "panel" | "rewrite" | "reconciliation" | "cascade" | "undo" | "redo";
export type Projectid1 = string;
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
export type Packagehash1 = string;
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
export type Durability = "pending" | "durable" | "failed";
export type Errorcode1 = string | null;
export type Id37 = string;
export type Stage = "assess_resume" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Startedat = string | null;
export type Status7 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Subtitle = string;
export type Title = string;
export type Capabilities = string[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id38 = "header" | "sidebar" | "main";
export type Width1 = number;
export type X = number;
export type Regions = Region[];
export type Order = number;
export type Region1 = "header" | "sidebar" | "main";
export type Renderinputversion = 1;
export type Schemaversion3 = 1;
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
export type Style1 = string;
export type Text5 = string;
export type Color1 = string;
export type FollowHeader = true;
export type Width2 = number;
export type X1 = number;
export type X2 = number;
export type Y = number;
export type Asset = string;
export type Fit = "contain";
export type Height1 = number;
export type Top = number;
export type Width3 = number;
export type X3 = number;
export type NameTop = number;
export type Overflow = "grow_header_and_move_body";
export type ProfessionTop = number;
export type BodyBottom = number;
export type ContinuationBodyTop = number;
export type FirstBodyTop = number;
export type Height2 = number;
export type Width4 = number;
export type Background = string;
export type HeadingStyle = string;
export type Height3 = number;
export type TextInset = number;
export type Color2 = string;
export type Font1 = string;
export type LineHeight = number;
export type Size1 = number;
export type FallbackStyle = string | null;
export type Heading = "none" | "plain" | "band";
export type Inset = number;
export type ItemGap = number;
export type Mode = "object" | "items";
export type Background1 = string | null;
export type DetailStyle = string | null;
export type ExperienceField = string | null;
export type Field3 = string | null;
export type Fields = string[];
export type HeaderSlot = ("name" | "profession") | null;
export type ItemField = string | null;
export type NameField = string | null;
export type Separator = string;
export type Style2 = string;
export type Type17 = "text" | "join_fields" | "join_items" | "bullets" | "tags" | "period" | "link" | "focus_entry";
export type UrlField = string | null;
export type Nodes = ViewNode[];
export type Schemaversion4 = 1;
export type Saveerror = string | null;
export type Saveddocumentrevision = number | null;
export type Savedprojectrevision = number | null;
export type Schemaversion5 = 1;
export type Createdat = string;
export type Documentrevision1 = number;
export type Clientmutationid2 = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
export type Mutationreplay = RichMutationReplay[];
export type Cellid7 = string;
export type Fieldkey4 = string;
export type Periodid = string | null;
export type Itemhandle2 = string;
export type Recordid9 = string;
export type Semanticschemahash1 = string;
export type Semantictype1 = string;
export type Builtinidentities = BuiltinItemIdentity[];
export type Extensions = ExtensionRecord[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status8 = "complete" | "partial";
export type Code1 = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page1 = number | null;
export type Section = string;
export type Sourceid2 = string;
export type Unitid2 = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Manualscopes = ManualEditScope[];
export type Mode1 = "structured" | "digest" | "imported";
export type Admission = "provisional" | "accepted" | "rejected" | "uncertain";
export type Evidence16 = SourceSpan[];
export type Fieldkey5 = string;
export type Id39 = string;
export type Itemhandle3 = string;
export type Ownerrelations = Relation[];
export type Proposalhash = string;
export type Rawinput2 = string;
export type Receiptids = string[];
export type Observations = Observation[];
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
export type Relations1 = Relation[];
export type Revision35 = number;
export type Schemaversion6 = 2;
export type Actionid5 = string;
export type Orderindex = number;
export type Recordid10 = string;
export type Revision36 = number;
export type Tombstones = RecordTombstone[];
export type Allowtextrewrite = boolean;
export type Category1 =
  ("identity" | "contacts" | "summary" | "experience" | "education" | "skills" | "languages" | "other") | null;
/**
 * @maxItems 1000
 */
export type Duplicateof = string[];
export type Id40 = string;
export type Kind50 = "paragraph" | "heading" | "section" | "bullet_list" | "duplicate" | "source_only";
export type Listitem = boolean;
export type Modelblock = boolean;
export type Reason = string | null;
export type Region2 = "header" | "sidebar" | "main";
/**
 * @maxItems 1000
 */
export type Sourcekeys = string[];
export type Text7 = string | null;
export type Title2 = string | null;
/**
 * @maxItems 5000
 */
export type Blocks1 = ImportBlock[];
export type Id41 = string;
export type Record1 = (ImportEmployment | ImportEducation | ImportTechnology | ImportLanguage) | null;
export type Employer = string;
export type Kind51 = "employment";
export type End3 = string;
export type Present = boolean;
export type Start4 = string;
/**
 * @maxItems 40
 */
export type Periods2 = ImportPeriod[];
export type Role1 = string;
export type Display = string;
export type Experience = string;
export type Technical1 = boolean | null;
/**
 * @maxItems 100
 */
export type Technologies = (string | ImportSkill)[];
export type Completion = string;
export type Institution = string;
export type Kind52 = "education";
export type Qualification = string;
export type Specialty = string;
export type Display1 = string;
export type Experience1 = string;
export type Kind53 = "technology";
export type Technical2 = boolean | null;
export type Kind54 = "language";
export type Language1 = string;
export type Level1 = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys1 = string[];
export type Text8 = string;
/**
 * @maxItems 1000
 */
export type Facts = ImportFact[];
export type Finished = boolean;
/**
 * @maxItems 100
 */
export type Issues = string[];
export type Location = string;
export type Name = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys2 = string[];
export type Title3 = string;
export type Batchid = string;
export type Requestsha2561 = string;
export type Sequence = number;
/**
 * @maxItems 128
 */
export type Receipts = ImportReceipt[];
export type Runid = string;
export type Sequence1 = number;
export type Skillsha256 = string;
export type Sourcesha256 = string;
export type Heading1 = string;
export type Region3 = "sidebar" | "main";
/**
 * @maxItems 1000
 */
export type Sourcekeys3 = string[];
/**
 * @minItems 1
 * @maxItems 100
 */
export type Technologies1 = [string, ...string[]];
/**
 * @maxItems 40
 */
export type Technologygroups = ImportTechnologyGroup[];
export type Version = 1;
export type Actionid6 = string | null;
export type Dependencies2 = DependencyStamp[];
export type Errorcode2 = string | null;
export type Id42 = string;
export type Kind55 =
  | "extract"
  | "assess_resume"
  | "normalize_semantics"
  | "draft_prose"
  | "render"
  | "project_save"
  | "rewrite_prose"
  | "reconcile_edits";
export type Status9 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Operations = RichOperation[];
export type Selectedinput = "text" | "file";
export type Selectedsourceid = string | null;
export type Byteref = string;
export type Bytesha256 = string;
export type Id43 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id44 = string;
export type Origin13 = "user";
export type Revision37 = number;
export type Text9 = string;
export type Unitid3 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision38 = number;
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id45 = string;
export type Column = number | null;
export type Index = number;
export type Kind56 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order1 = number;
export type Representedfactids = string[];
export type Revision39 = number;
export type Blankbefore = number | null;
export type Bold2 = boolean | null;
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
export type Style3 = string | null;
export type Text10 = string;
export type Units = SourceUnit[];
export type Code2 = string;
export type Page2 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources1 = Source1[];
export type Admittedat = string | null;
export type Discoveryattemptid = string;
export type Discoveryhash = string;
export type Itemhandle4 = string;
export type Key = string;
export type Operationid = string;
export type Recordid11 = string;
export type Semantictype2 = string;
export type Taskid = string;
export type Allocations = HandleAllocation[];
export type Authorizationid = string | null;
export type Evidencehash = string | null;
export type State1 = "pending" | "verified" | "unknown";
export type Witness = string | null;
export type Dispatchedat = string | null;
export type Errorcode3 = string | null;
export type Id46 = string;
export type Inputhash = string;
export type Adapter = string;
export type Capabilityprofile = string;
export type Capabilityversion = string;
export type Configurationhash = string;
export type Effort = string;
export type Model = string;
export type Operationid1 = string;
export type Outcome =
  | (
      | "completed"
      | "invalid_payload"
      | "refused"
      | "incomplete"
      | "timed_out"
      | "cancelled"
      | "transport_failure"
      | "cleanup_failure"
    )
  | null;
export type Generation = number;
export type Incarnationid = string;
export type Leaseid = string;
export type Pid = number | null;
export type Processstartwitness = string | null;
export type Reservationid = string;
export type Transportsessionid = string | null;
export type Transportturnid = string | null;
export type Proposalrecordid = string | null;
export type Rawreturn = string | null;
export type Rawreturnhash = string | null;
export type Requestvalue = {
  [k: string]: JsonValue;
} | null;
export type Reservedat = string;
export type Returnhash = string | null;
export type Returnedat = string | null;
export type Reviewinputrecordid = string | null;
export type Reviewreceiptid = string | null;
export type Slot = "initial" | "review" | "primary_repair" | "fallback_repair" | "replacement_review";
export type State2 = "reserved" | "dispatch_started" | "returned" | "outcome_unknown" | "reconciled" | "released";
export type Taskid1 = string;
export type Cachedinputtokens = number | null;
export type Complete1 = boolean;
export type Inputtokens = number | null;
export type Outputtokens = number | null;
export type Attempts = ImportAttempt[];
export type Authorityhash = string;
export type Authorizedat = string;
export type Dependencyhash = string;
export type Id47 = string;
export type Kind57 = "start" | "resume";
export type State3 = "active" | "cancelled";
export type Authorizations = ImportAuthorization[];
export type Allowtextrewrite1 = boolean;
export type Authorityhash1 = string;
export type Dependencyhash1 = string;
export type Packagehash2 = string;
export type Callcap = number;
export type Cleanupseconds = 5;
export type Concurrency = 1;
export type Fallbackrepairs = 1;
export type Finalizationseconds = 30;
export type Primaryrepairs = 1;
export type Processingseconds = 300;
export type Itemhandle5 = string;
export type Recordid12 = string;
export type Recordrevision = number;
export type Semanticschemahash2 = string;
export type Semantictype3 = string;
export type Captureditems = CapturedItemIdentity[];
export type Attemptid = string;
export type Evidencehash1 = string;
export type Neverdispatched = boolean;
export type Ownerhash = string;
export type Verifiedat = string;
export type Witness1 = string;
export type Cleanuprecords = AttemptCleanupRecord[];
export type Clientrequestid = string | null;
export type Expiresat = string | null;
export type Artifacthash = string | null;
export type Assetshash = string;
export type Documenthash1 = string;
export type Errorcode4 = string | null;
export type Factshash1 = string;
export type Id48 = string;
export type Packagehash3 = string;
export type Presentationhash1 = string;
export type Publicationintentid = string | null;
export type Rendererhash = string;
export type State4 = "pending" | "running" | "completed" | "failed";
export type Exportattempts = ExportAttempt[];
export type Authorityhash2 = string;
export type Authorizationid1 = string;
export type Candidatehash = string;
export type Coveragehash = string;
export type Dependencyhash2 = string;
export type Documenthash2 = string;
export type Expiresat1 = string;
export type Factshash2 = string;
export type Id49 = string;
export type Issueshash = string;
export type Operationid2 = string;
export type Packagehash4 = string;
export type Sourcehash = string;
export type Startedat1 = string;
export type Finalizationhistory = FinalizationCandidate[];
export type Id50 = string;
export type Inferenceclosed = boolean;
export type Blockids3 = string[];
export type Category2 = "content_violation" | "uncertain_interpretation" | "check_not_completed";
export type Code3 = string;
export type Id51 = string;
export type Importedfingerprint2 = string;
export type Lifecycleid1 = string;
export type Message = string;
export type Retiredbyaction = string | null;
export type Reviewinputhash = string | null;
export type Ruleid = string | null;
export type State5 = "active" | "retired";
export type Targetids = string[];
export type Taskid2 = string;
export type Issues1 = ImportIssue[];
export type Lastobservedat = string | null;
export type Projectid2 = string;
export type Admittedcellids = string[];
export type Admittedrelationids = string[];
export type Appliedreceiptid = string | null;
export type Attemptid1 = string;
export type Errors = string[];
export type Id52 = string;
export type Inputhash1 = string;
export type Attemptid2 = string;
export type Children12 = string[];
export type Kind58 = "add" | "split" | "merge";
export type Parents = string[];
export type Lineage = Lineage1[];
export type Proposalhash1 = string;
export type Rawreturn1 = string;
export type Rawreturnhash1 = string;
export type Key1 = string;
export type Pointer4 = string;
export type Semantictype4 = string;
export type Discoveries = Discovery[];
export type Effectivecellids = string[];
export type Evidence17 = SourceSpan[];
export type Fieldkey6 = string;
export type Item = DiscoverySelector | HandleSelector;
export type Key2 = string;
export type Kind59 = "discovery_key";
export type Itemhandle6 = string;
export type Kind60 = "handle";
export type Pointer5 = string;
export type Fields1 = ProposalField[];
export type Children13 = string[];
export type Kind61 = "add" | "split" | "merge";
export type Parents1 = string[];
export type Lineage2 = ProposalLineage[];
export type Evidence18 = SourceSpan[];
export type Kind62 = "owned_by" | "extension_of" | "related_to";
export type Relation1 = RelationDiscoverySelector | ExistingRelationSelector;
export type Key3 = string;
export type Kind63 = "discovery_key";
export type Kind64 = "relation_id";
export type Relationid2 = string;
export type Subject = DiscoverySelector | HandleSelector;
export type Target1 = DiscoverySelector | HandleSelector;
export type Relations2 = ProposalRelation[];
export type Schemaversion7 = 1;
export type Effectivecellids1 = string[];
export type Evidence19 = SourceSpan[];
export type Fieldkey7 = string;
export type Itemhandle7 = string;
export type Pointer6 = string;
export type Resolvedfields = FieldSidecar[];
export type Resolvedrelations = Relation[];
export type State6 = "invalid" | "provisional" | "accepted" | "rejected";
export type Proposals = ProposalRecord[];
export type Errorcode5 = string | null;
export type Intentid = string | null;
export type State7 = "pending" | "saved" | "failed_before_replacement" | "outcome_unknown" | "cancelled";
export type Workspacehash = string | null;
export type Attemptid3 = string;
export type Completedat = string;
export type Ruleid1 = string;
export type Targetid1 = string;
export type Expectedchecks = CheckTarget[];
export type Id53 = string;
export type Actionable = boolean;
export type Disposition1 = "satisfied" | "violation" | "uncertain";
export type Evidence20 = SourceSpan[];
export type Reason1 = string;
export type Ruleid2 = string;
export type Targetid2 = string;
export type Results = ReviewDisposition[];
export type Reviewinputhash1 = string;
export type Receipts1 = ReviewReceipt[];
export type Discoveryattemptid1 = string;
export type Key4 = string;
export type Kind65 = "owned_by" | "extension_of" | "related_to";
export type Operationid3 = string;
export type Relationid3 = string;
export type Subjectid1 = string;
export type Targetid3 = string;
export type Taskid3 = string;
export type Relationallocations = RelationAllocation[];
export type Attemptid4 = string;
export type Id54 = string;
export type Inputhash2 = string;
export type Allowtextrewrite2 = boolean;
export type Effectivecells = ExtensionCell[];
export type Handlemap = (HandleAllocation | CapturedItemIdentity)[];
export type Occurrenceindependent = boolean;
export type Packagehash5 = string;
export type Proposalhash2 = string;
export type Protocol = "template_import_v1";
export type Relations3 = Relation[];
export type Id55 = string;
export type Kind66 =
  | "content_schema"
  | "evidence_identity"
  | "protected_values"
  | "claim_ownership"
  | "complete_assignment"
  | "semantic_support"
  | "task_result_separation"
  | "attribution";
export type Fields2 = string[];
export type Instructions = string[];
export type Version1 = 1;
export type Rules = Check[];
export type Schemaversion8 = 1;
export type Sourcespans = SourceSpan[];
export type Targets = CheckTarget[];
export type Reviewinputs = ReviewInputRecord[];
export type Schemaversion9 = 1;
export type State8 =
  "captured" | "processing" | "cleanup_pending" | "finalizing" | "published" | "cancelled" | "failed" | "fenced";
export type Capturedat = string;
export type Id56 = string;
export type Inputhash3 = string;
export type Taskid4 = string;
export type Taskinputs = TaskInputRecord[];
export type Disposition2 = "admitted" | "derived" | "source_fallback" | "empty";
export type Id57 = string;
export type Inputhash4 = string;
export type Issueids = string[];
export type Itemhandles = string[];
export type Sourcespans1 = SourceSpan[];
export type Taskid5 = string;
export type Taskresults = TaskResultRecord[];
export type Allowedhandles = string[];
export type Attemptids = string[];
export type Blockid7 = string;
export type Dependencies3 = string[];
export type Expectedchecks1 = CheckTarget[];
export type Id58 = string;
export type Inputhash5 = string;
export type Issueids1 = string[];
export type Kind67 = "extract" | "rewrite" | "derive" | "source_copy";
export type Operationid4 = string;
export type Proposalhash3 = string | null;
export type Receiptids1 = string[];
export type State9 =
  | "pending"
  | "running"
  | "proposed"
  | "checking"
  | "repairing"
  | "accepted"
  | "empty"
  | "source_fallback"
  | "cancelled"
  | "technical_failure";
export type Tasks = ImportTask[];
export type Templateoperations = ImportOperation[];
export type Bytesbase64 = string;
export type Id59 = string;
export type Mimetype1 = string;
export type Path = string;
export type Role2 = "font" | "logo" | "icon" | "catalog";
export type Sha256 = string;
export type Size2 = number;
export type Assets = CapturedAsset[];
export type Dependencyorder = number;
export type Id60 = string;
export type Serveronly = string[];
export type Blocks2 = CompiledBlock[];
export type Compilerversion = string;
export type Confighash = string;
export type Embedding = "allowed" | "not_applicable";
export type Id61 = string;
export type MimeType = string;
export type Path1 = string;
export type Role3 = "font" | "logo" | "icon" | "catalog";
export type Assets1 = AssetDeclaration[];
export type Field4 = string;
export type ItemPointer = string | null;
export type Pointer7 = string;
export type Kind68 = "owned_by" | "extension_of" | "related_to";
export type SubjectPointer = string;
export type SemanticType = string;
export type Bindings = Binding[];
export type Checks = Check[];
export type DependsOn = string[];
export type Extract = string[];
export type Id62 = string;
export type Mode2 = "model" | "derived" | "source_copy";
export type Operation = string | null;
export type Fields3 = string[];
export type Instructions1 = string[];
export type Id63 = string;
export type Kind69 = "source" | "fact_type" | "block" | "operation";
export type Selectors = InputRef[];
export type Equals = string;
export type Operation1 = string;
export type Blocks3 = Block1[];
export type Field5 = string;
export type Period1 = string | null;
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
export type Id64 = string;
export type Kind70 = "owned_by" | "extension_of" | "related_to";
export type TargetTypes = string[];
export type Relations4 = RelationDeclaration[];
export type SchemaVersion = string;
export type FactTypes = FactType[];
export type Extract1 = string[];
export type Permission = "allowTextRewrite";
export type Rewrite1 = string[];
export type DependsOn1 = string[];
export type Id65 = string;
export type Inputs = InputRef[];
export type Kind71 = "partition_employment";
export type Compact = string;
export type Detailed = string;
export type Years = number;
export type Version2 = 1;
export type DependsOn2 = string[];
export type Id66 = string;
export type Inputs1 = InputRef[];
export type Kind72 = "select_role_branch";
export type Matched = string;
export type Otherwise = string;
export type RoleFamilies = string[];
export type Version3 = 1;
export type DependsOn3 = string[];
export type Id67 = string;
export type Inputs2 = InputRef[];
export type Kind73 = "assign_skills";
export type Groups = string[];
export type UncertainGroup = string;
export type Version4 = 1;
export type DependsOn4 = string[];
export type Id68 = string;
export type Inputs3 = InputRef[];
export type Kind74 = "format_period";
export type Separator1 = string;
export type Version5 = 1;
export type DependsOn5 = string[];
export type Id69 = string;
export type Inputs4 = InputRef[];
export type Kind75 = "preserve_stated_text";
export type Version6 = 1;
export type Operations1 = (
  PartitionOperation | RoleOperation | SkillsOperation | PeriodOperation | PreserveOperation
)[];
export type SchemaVersion1 = 3;
export type RetainOriginal = true;
export type RetainUnmappedFacts = true;
export type DefaultLocale = string;
export type Id70 = string;
export type Name1 = string;
export type Revision40 = string;
export type Id71 = string;
export type Capabilities1 = string[];
export type Profileid = string;
export type Profileversion = string;
export type Supportedformats = string[];
export type Operationversion = string;
export type Originalbase64 = string;
export type Originalformat = "yaml" | "json";
export type Originalhash = string;
export type Packagehash6 = string;
export type Projectionversion = string;
export type Revision41 = string;
export type Schemaversion10 = 1;
export type Warnings1 = string[];
export type Height4 = number;
export type Id72 = string;
export type Mimetype2 = "image/png" | "image/jpeg";
export type Path2 = string;
export type Sha2561 = string;
export type Size3 = number;
export type Width5 = number;
export type Assets2 = LocalImageAsset[];
export type Createdat1 = string;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Regions1 = [TemplateRegion, TemplateRegion, TemplateRegion];
export type Blocks4 = (
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
export type Id73 = string;
export type Revision42 = number;
export type Role4 = "header" | "sidebar" | "main";
export type Revision43 = number;
export type Schemaversion11 = 2;
export type Evidence21 = EvidenceSpan[];
export type Id74 = string;
export type Rawtext5 = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Attemptid5 = string;
export type Id75 = string;
export type Path3 = string;
export type Sha2562 = string;
export type Size4 = number;
export type Assets3 = TemplateRenderAsset[];
export type Documenthash3 = string;
export type Factshash3 = string;
export type Packagehash7 = string;
export type Presentationhash2 = string;
export type Renderinputversion1 = 1;
export type Id76 = string;
export type Sha2563 = string;
export type Version7 = string;
export type Schemaversion12 = 1;
export type Exportinputs = TemplateExportCapture[];
export type Exports = ExportAttempt[];
export type Blockids4 = string[];
export type Disposition3 = "accepted" | "fallback" | "source_only" | "multiple_views";
export type Itemhandle8 = string | null;
export type Reason2 = string | null;
export type Importcoverage = SpanCoverage[];
export type Importissues = ImportIssue[];
export type Operations2 = RichOperation[];
export type Projectid3 = string;
export type Documentrevision2 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id77 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision44 = number;
export type Schemaversion13 = 6;
export type Sources2 = Source1[];
export type Templateoperations1 = ImportOperation[];
export type Projectid4 = string;
export type Projectrevision1 = number;
export type Markdown = string;
export type Revision45 = number;
export type Sha2564 = string;
export type Schemaversion14 = 7;
export type Actionid7 = string;
export type Blockids5 = string[];
export type Dependencies4 = DependencyStamp[];
export type Errorcode6 = string | null;
export type Factids1 = string[];
export type Fieldkeys2 = string[];
export type Id78 = string;
export type Instruction1 = string | null;
export type Kind76 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Lifecycleid2 = string;
/**
 * @maxItems 1000
 */
export type Proposedsteps1 = (
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
export type Ready1 = boolean;
export type Rewriteresult1 = string | null;
export type Rewritesource1 = string | null;
export type Schemaversion15 = 2;
export type Status10 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Actionid8 = string;
export type Blockids6 = string[];
export type Dependencies5 = DependencyStamp[];
export type Errorcode7 = string | null;
export type Factids2 = string[];
export type Fieldkeys3 = string[];
export type Id79 = string;
export type Instruction2 = string | null;
export type Kind77 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Afterid2 = string | null;
export type Beforerevision11 = number | null;
export type Block2 =
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
export type Children25 = (
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
export type Text11 = string;
export type Type18 = "text";
export type Content16 = StyledText[];
export type Href2 = string;
export type Type19 = "link";
export type Bindingid2 = string;
export type Bindingrootid1 = string | null;
export type Fieldkey8 = string;
export type Recordid13 = string;
export type Syncedfactrevision1 = number;
export type Text12 = string;
export type Type20 = "fact_field";
export type Content15 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id80 = string;
export type Provenance13 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision46 = number;
export type Type21 = "section";
export type Children24 = (
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
export type Content17 = null;
export type Id81 = string;
export type Alignment8 = "left" | "center" | "right";
export type Alt1 = string;
export type Assetid1 = string;
export type Caption1 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height5 = number;
export type Width6 = number;
export type Provenance14 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision47 = number;
export type Type22 = "image";
export type Children23 = (
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
export type Columnwidths1 = [number | null, ...(number | null)[]];
export type Headercols1 = number;
export type Headerrows1 = number;
/**
 * @minItems 1
 */
export type Rows1 = [TableRow, ...TableRow[]];
export type Alignment9 = "left" | "center" | "right" | "justify";
export type Backgroundcolor8 = string;
export type Colspan1 = number;
export type Content18 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id82 = string;
export type Revision48 = number;
export type Rowspan1 = number;
export type Cells2 = TableCell[];
export type Id83 = string;
export type Id84 = string;
export type Provenance15 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision49 = number;
export type Type23 = "table";
export type Children22 = (
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
export type Content19 = null;
export type Id85 = string;
export type Provenance16 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision50 = number;
export type Type24 = "divider";
export type Children21 = (
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
export type Content20 = string;
export type Id86 = string;
export type Provenance17 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision51 = number;
export type Type25 = "code";
export type Children20 = (
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
export type Content21 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id87 = string;
export type Provenance18 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision52 = number;
export type Type26 = "quote";
export type Children19 = (
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
export type Content22 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id88 = string;
export type Provenance19 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision53 = number;
export type Type27 = "toggle_list";
export type Children18 = (
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
export type Content23 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id89 = string;
export type Provenance20 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision54 = number;
export type Type28 = "check_list";
export type Children17 = (
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
export type Content24 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id90 = string;
export type Provenance21 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision55 = number;
export type Type29 = "numbered_list";
export type Children16 = (
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
export type Content25 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id91 = string;
export type Provenance22 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision56 = number;
export type Type30 = "bullet_list";
export type Children15 = (
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
export type Content26 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id92 = string;
export type Provenance23 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision57 = number;
export type Type31 = "heading";
export type Children14 = (
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
export type Content27 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id93 = string;
export type Provenance24 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision58 = number;
export type Type32 = "paragraph";
export type Keepchildren1 = boolean;
export type Kind78 = "put_block";
export type Parentid2 = string;
export type Beforerevision12 = number;
export type Blockid8 = string;
export type Cellid8 = string | null;
export type Content28 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End4 = number;
export type Field6 = "content" | "caption";
export type Kind79 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start5 = number;
/**
 * @maxItems 1000
 */
export type Proposedsteps2 = (PutBlock | RemoveBlock | MoveBlock | ReplaceInlineRange | PutRecord | RemoveRecord)[];
export type Ready2 = boolean;
export type Rewriteresult2 = string | null;
export type Rewritesource2 = string | null;
export type Status11 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Syncrecords = (TemplateSyncRecord | RichSyncRecord)[];
export type Title4 = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;
export type Blockids7 = string[];
export type Code4 = string;
export type Count = number;
export type Sourceid3 = string;
export type Sourcerevision2 = number;
export type Unitid4 = string;
export type Unitrevision2 = number;
export type Evidence22 = Evidence23[];
export type Id94 = string;
export type Page3 = number | null;
export type Sourceid4 = string;
export type Locations = WarningLocation[];
export type Recordids = string[];
export type Warnings2 = RichWarning[];
export type Requesthash = string;
export type Schemaversion16 = 1;

export interface TemplatePreparedEditV1 {
  baseSnapshot: TemplateSnapshotIdentity;
  capture: ActionCapture;
  clientMutationId: Clientmutationid;
  createdIds: Createdids;
  mutation: TemplateMutationV1 | null;
  preview: TemplateProjectResponseV1;
  requestHash: Requesthash;
  schemaVersion: Schemaversion16;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision;
  factsHash: Factshash;
  packageHash: Packagehash;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
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
export interface Createdids {
  [k: string]: {
    [k: string]: string;
  };
}
export interface TemplateMutationV1 {
  actionId: Actionid1;
  capture: ActionCapture;
  clientMutationId: Clientmutationid1;
  history: HistoryCapture;
  kind: Kind2;
  projectId: Projectid1;
  schemaVersion: Schemaversion;
  steps: Steps;
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
  packageHash: Packagehash1;
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
export interface TemplateProjectResponseV1 {
  durability: Durability;
  generation: RichGenerationState | null;
  identity: ResumeIdentity | null;
  presentation: TemplatePresentationV1 | null;
  saveError: Saveerror;
  savedDocumentRevision: Saveddocumentrevision;
  savedProjectRevision: Savedprojectrevision;
  schemaVersion: Schemaversion5;
  snapshot: TemplateSnapshotIdentity | null;
  workspace: WorkspaceV7;
}
export interface RichGenerationState {
  errorCode: Errorcode1;
  id: Id37;
  stage: Stage;
  startedAt?: Startedat;
  status: Status7;
}
export interface ResumeIdentity {
  subtitle: Subtitle;
  title: Title;
}
export interface TemplatePresentationV1 {
  blocks: Blocks;
  recipe: CompiledRecipe;
  schemaVersion: Schemaversion4;
  snapshot: TemplateSnapshotIdentity;
}
export interface Blocks {
  [k: string]: AuthoredPresentation;
}
export interface CompiledRecipe {
  capabilities: Capabilities;
  layout: Layout;
  placements: Placements;
  renderInputVersion: Renderinputversion;
  schemaVersion: Schemaversion3;
  style: Style;
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
  id: Id38;
  width: Width1;
  x: X;
}
export interface Placements {
  [k: string]: Placement;
}
export interface Placement {
  order: Order;
  region: Region1;
}
export interface Style {
  bullets: Bullets;
  colors: Colors;
  focus: Focus;
  fonts: Fonts;
  footer: Footer;
  header: Header;
  page: Page;
  section_band: Band;
  text: Text6;
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
  style: Style1;
  text: Text5;
}
export interface Header {
  divider: Divider | null;
  logo: Logo | null;
  name_top: NameTop;
  overflow: Overflow;
  profession_top: ProfessionTop;
}
export interface Divider {
  color: Color1;
  follow_header: FollowHeader;
  width: Width2;
  x1: X1;
  x2: X2;
  y: Y;
}
export interface Logo {
  asset: Asset;
  fit: Fit;
  height: Height1;
  top: Top;
  width: Width3;
  x: X3;
}
export interface Page {
  body_bottom: BodyBottom;
  continuation_body_top: ContinuationBodyTop;
  first_body_top: FirstBodyTop;
  height: Height2;
  width: Width4;
}
export interface Band {
  background: Background;
  heading_style: HeadingStyle;
  height: Height3;
  text_inset: TextInset;
}
export interface Text6 {
  [k: string]: TextStyle;
}
export interface TextStyle {
  color: Color2;
  font: Font1;
  line_height: LineHeight;
  size: Size1;
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
  title: Title1;
}
export interface ViewNode {
  background?: Background1;
  detail_style?: DetailStyle;
  experience_field?: ExperienceField;
  field?: Field3;
  fields?: Fields;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label1;
  name_field?: NameField;
  prefix?: Prefix;
  separator?: Separator;
  style: Style2;
  type: Type17;
  url_field?: UrlField;
}
export interface Label1 {
  [k: string]: string;
}
export interface Prefix {
  [k: string]: string;
}
export interface Title1 {
  [k: string]: string;
}
export interface WorkspaceV7 {
  createdAt: Createdat;
  documentRevision: Documentrevision1;
  formattingAsOf: PartialDate;
  mutationReplay: Mutationreplay;
  preDraft: RichPreDraftV2 | null;
  project: ProjectV6 | null;
  projectId: Projectid4;
  projectRevision: Projectrevision1;
  rulesUsed: Rules1 | null;
  schemaVersion: Schemaversion14;
  sourceObservedAt: PartialDate | null;
  syncRecords: Syncrecords;
  title: Title4;
  titleManuallySet: Titlemanuallyset;
  updatedAt: Updatedat;
  warnings: Warnings2;
}
export interface RichMutationReplay {
  clientMutationId: Clientmutationid2;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface RichPreDraftV2 {
  facts: WorkingFactsV2;
  importDraft?: ImportDraft | null;
  operations: Operations;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources1;
  templateOperations: Templateoperations;
  templatePackage: TemplatePackage | null;
  warnings: Warnings1;
}
export interface WorkingFactsV2 {
  builtinIdentities?: Builtinidentities;
  builtinManualScopes?: Builtinmanualscopes;
  extensions: Extensions;
  extraction?: ExtractionReport | null;
  manualScopes: Manualscopes;
  mode?: Mode1;
  observations: Observations;
  records: Records;
  relations: Relations1;
  revision: Revision35;
  schemaVersion: Schemaversion6;
  tombstones: Tombstones;
}
export interface BuiltinItemIdentity {
  canonicalFields?: Canonicalfields;
  cellIds: Cellids1;
  itemHandle: Itemhandle2;
  periodIds?: Periodids;
  recordId: Recordid9;
  semanticSchemaHash: Semanticschemahash1;
  semanticType: Semantictype1;
}
export interface Canonicalfields {
  [k: string]: CanonicalFieldBinding;
}
export interface CanonicalFieldBinding {
  cellId: Cellid7;
  fieldKey: Fieldkey4;
  periodId: Periodid;
}
export interface Cellids1 {
  [k: string]: string;
}
export interface Periodids {
  [k: string]: string;
}
export interface Builtinmanualscopes {
  [k: string]: string;
}
export interface ExtractionReport {
  counts: Counts;
  factCount: Factcount;
  recoveredRows: Recoveredrows;
  requestBytes: Requestbytes;
  status: Status8;
  unresolved: Unresolved;
}
export interface Counts {
  [k: string]: number;
}
export interface ExtractionIssue {
  code: Code1;
  page?: Page1;
  section: Section;
  sourceId: Sourceid2;
  unitId: Unitid2;
}
export interface Observation {
  admission: Admission;
  evidence: Evidence16;
  fieldKey: Fieldkey5;
  id: Id39;
  itemHandle: Itemhandle3;
  ownerRelations: Ownerrelations;
  proposalHash: Proposalhash;
  rawInput: Rawinput2;
  receiptIds: Receiptids;
  typedValue: JsonValue;
}
export interface RecordTombstone {
  actionId: Actionid5;
  orderIndex: Orderindex;
  recordId: Recordid10;
  revision: Revision36;
}
export interface ImportDraft {
  allowTextRewrite?: Allowtextrewrite;
  blocks?: Blocks1;
  facts?: Facts;
  finished?: Finished;
  issues?: Issues;
  profile?: ImportProfile;
  receipts?: Receipts;
  runId: Runid;
  sequence?: Sequence1;
  skillSha256: Skillsha256;
  sourceSha256: Sourcesha256;
  technologyGroups?: Technologygroups;
  version?: Version;
}
export interface ImportBlock {
  category?: Category1;
  duplicateOf?: Duplicateof;
  id: Id40;
  kind?: Kind50;
  listItem?: Listitem;
  modelBlock?: Modelblock;
  reason?: Reason;
  region?: Region2;
  sourceKeys?: Sourcekeys;
  text?: Text7;
  title?: Title2;
}
export interface ImportFact {
  id: Id41;
  record?: Record1;
  sourceKeys?: Sourcekeys1;
  text?: Text8;
}
export interface ImportEmployment {
  employer?: Employer;
  kind: Kind51;
  periods?: Periods2;
  role?: Role1;
  technologies?: Technologies;
}
export interface ImportPeriod {
  end?: End3;
  present?: Present;
  start?: Start4;
}
export interface ImportSkill {
  display: Display;
  experience?: Experience;
  technical?: Technical1;
}
export interface ImportEducation {
  completion?: Completion;
  institution?: Institution;
  kind: Kind52;
  qualification?: Qualification;
  specialty?: Specialty;
}
export interface ImportTechnology {
  display: Display1;
  experience?: Experience1;
  kind: Kind53;
  technical?: Technical2;
}
export interface ImportLanguage {
  kind: Kind54;
  language?: Language1;
  level?: Level1;
}
export interface ImportProfile {
  location?: Location;
  name?: Name;
  sourceKeys?: Sourcekeys2;
  title?: Title3;
}
export interface ImportReceipt {
  batchId: Batchid;
  requestSha256: Requestsha2561;
  sequence: Sequence;
}
export interface ImportTechnologyGroup {
  heading: Heading1;
  region?: Region3;
  sourceKeys?: Sourcekeys3;
  technologies: Technologies1;
}
export interface RichOperation {
  actionId: Actionid6;
  dependencies: Dependencies2;
  errorCode: Errorcode2;
  id: Id42;
  kind: Kind55;
  status: Status9;
}
export interface Source1 {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id43;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision38;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id44;
  origin: Origin13;
  revision: Revision37;
  text: Text9;
  unitId: Unitid3;
}
export interface SourceUnit {
  disposition: Disposition;
  id: Id45;
  location: SourceLocation;
  order: Order1;
  representedFactIds: Representedfactids;
  revision: Revision39;
  structure?: SourceStructure | null;
  text: Text10;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind56;
  row: Row;
}
/**
 * Observed layout cues, never semantic resume fields.
 */
export interface SourceStructure {
  blankBefore?: Blankbefore;
  bold?: Bold2;
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
  style?: Style3;
}
export interface SourceWarning {
  code: Code2;
  page?: Page2;
}
export interface ImportOperation {
  admittedAt: Admittedat;
  allocations: Allocations;
  attempts: Attempts;
  authorizations?: Authorizations;
  capture: ImportCapture;
  capturedItems?: Captureditems;
  capturedRelationRevisions?: Capturedrelationrevisions;
  cleanupRecords?: Cleanuprecords;
  clientRequestId?: Clientrequestid;
  expiresAt: Expiresat;
  exportAttempts: Exportattempts;
  finalization: FinalizationCandidate | null;
  finalizationHistory?: Finalizationhistory;
  id: Id50;
  inferenceClosed?: Inferenceclosed;
  issues?: Issues1;
  lastObservedAt: Lastobservedat;
  projectId: Projectid2;
  proposals: Proposals;
  publication: PublicationOutcome;
  receipts: Receipts1;
  relationAllocations?: Relationallocations;
  reviewInputs: Reviewinputs;
  schemaVersion: Schemaversion9;
  state: State8;
  taskInputs?: Taskinputs;
  taskResults?: Taskresults;
  tasks: Tasks;
}
export interface HandleAllocation {
  canonicalFields?: Canonicalfields1;
  cellIds: Cellids2;
  discoveryAttemptId: Discoveryattemptid;
  discoveryHash: Discoveryhash;
  itemHandle: Itemhandle4;
  key: Key;
  operationId: Operationid;
  periodIds?: Periodids1;
  recordId: Recordid11;
  semanticType: Semantictype2;
  taskId: Taskid;
}
export interface Canonicalfields1 {
  [k: string]: CanonicalFieldBinding;
}
export interface Cellids2 {
  [k: string]: string;
}
export interface Periodids1 {
  [k: string]: string;
}
export interface ImportAttempt {
  authorizationId?: Authorizationid;
  cleanup: CleanupOutcome;
  dispatchedAt: Dispatchedat;
  errorCode?: Errorcode3;
  id: Id46;
  inputHash: Inputhash;
  model: ModelCapture;
  operationId: Operationid1;
  outcome?: Outcome;
  owner: LaunchOwner;
  proposalRecordId: Proposalrecordid;
  rawReturn: Rawreturn;
  rawReturnHash: Rawreturnhash;
  requestValue?: Requestvalue;
  reservedAt: Reservedat;
  returnHash: Returnhash;
  returnedAt?: Returnedat;
  reviewInputRecordId: Reviewinputrecordid;
  reviewReceiptId: Reviewreceiptid;
  slot: Slot;
  state: State2;
  taskId: Taskid1;
  usage: ObservedUsage;
}
export interface CleanupOutcome {
  evidenceHash: Evidencehash;
  state: State1;
  witness: Witness;
}
export interface ModelCapture {
  adapter: Adapter;
  capabilityProfile: Capabilityprofile;
  capabilityVersion: Capabilityversion;
  configurationHash: Configurationhash;
  effort: Effort;
  model: Model;
}
export interface LaunchOwner {
  generation: Generation;
  incarnationId: Incarnationid;
  leaseId: Leaseid;
  pid: Pid;
  processStartWitness: Processstartwitness;
  reservationId: Reservationid;
  transportSessionId: Transportsessionid;
  transportTurnId: Transportturnid;
}
export interface ObservedUsage {
  cachedInputTokens: Cachedinputtokens;
  complete: Complete1;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
}
export interface ImportAuthorization {
  authorityHash: Authorityhash;
  authorizedAt: Authorizedat;
  dependencyHash: Dependencyhash;
  id: Id47;
  kind: Kind57;
  state: State3;
}
export interface ImportCapture {
  allowTextRewrite: Allowtextrewrite1;
  authorityHash: Authorityhash1;
  dependencyHash: Dependencyhash1;
  factRevisions: Factrevisions;
  fallback: ModelCapture | null;
  formattingAsOf: PartialDate;
  packageHash: Packagehash2;
  policy: RuntimePolicy;
  primary: ModelCapture;
  sourceHashes: Sourcehashes;
}
export interface Factrevisions {
  [k: string]: number;
}
export interface RuntimePolicy {
  callCap: Callcap;
  cleanupSeconds: Cleanupseconds;
  concurrency: Concurrency;
  fallbackRepairs: Fallbackrepairs;
  finalizationSeconds: Finalizationseconds;
  primaryRepairs: Primaryrepairs;
  processingSeconds: Processingseconds;
}
export interface Sourcehashes {
  [k: string]: string;
}
export interface CapturedItemIdentity {
  canonicalFields?: Canonicalfields2;
  cellIds: Cellids3;
  itemHandle: Itemhandle5;
  periodIds?: Periodids2;
  recordId: Recordid12;
  recordRevision: Recordrevision;
  semanticSchemaHash: Semanticschemahash2;
  semanticType: Semantictype3;
}
export interface Canonicalfields2 {
  [k: string]: CanonicalFieldBinding;
}
export interface Cellids3 {
  [k: string]: string;
}
export interface Periodids2 {
  [k: string]: string;
}
export interface Capturedrelationrevisions {
  [k: string]: number;
}
export interface AttemptCleanupRecord {
  attemptId: Attemptid;
  evidenceHash: Evidencehash1;
  neverDispatched: Neverdispatched;
  ownerHash: Ownerhash;
  verifiedAt: Verifiedat;
  witness: Witness1;
}
export interface ExportAttempt {
  artifactHash: Artifacthash;
  assetsHash: Assetshash;
  documentHash: Documenthash1;
  errorCode: Errorcode4;
  factsHash: Factshash1;
  id: Id48;
  packageHash: Packagehash3;
  presentationHash: Presentationhash1;
  publicationIntentId: Publicationintentid;
  rendererHash: Rendererhash;
  state: State4;
}
export interface FinalizationCandidate {
  authorityHash: Authorityhash2;
  authorizationId: Authorizationid1;
  candidateHash: Candidatehash;
  coverageHash: Coveragehash;
  dependencyHash: Dependencyhash2;
  documentHash: Documenthash2;
  expiresAt: Expiresat1;
  factsHash: Factshash2;
  id: Id49;
  issuesHash: Issueshash;
  operationId: Operationid2;
  packageHash: Packagehash4;
  sourceHash: Sourcehash;
  startedAt: Startedat1;
}
export interface ImportIssue {
  blockIds: Blockids3;
  category: Category2;
  code: Code3;
  id: Id51;
  importedFingerprint: Importedfingerprint2;
  lifecycleId: Lifecycleid1;
  message: Message;
  retiredByAction: Retiredbyaction;
  reviewInputHash: Reviewinputhash;
  ruleId: Ruleid;
  state: State5;
  targetIds: Targetids;
  taskId: Taskid2;
}
export interface ProposalRecord {
  admittedCellIds?: Admittedcellids;
  admittedRecordRevisions?: Admittedrecordrevisions;
  admittedRelationIds?: Admittedrelationids;
  admittedRelationRevisions?: Admittedrelationrevisions;
  appliedReceiptId?: Appliedreceiptid;
  attemptId: Attemptid1;
  errors: Errors;
  id: Id52;
  inputHash: Inputhash1;
  lineage: Lineage;
  proposalHash: Proposalhash1;
  rawReturn: Rawreturn1;
  rawReturnHash: Rawreturnhash1;
  reply: ProposalReply | null;
  resolvedFields: Resolvedfields;
  resolvedRelations?: Resolvedrelations;
  state: State6;
}
export interface Admittedrecordrevisions {
  [k: string]: number;
}
export interface Admittedrelationrevisions {
  [k: string]: number;
}
export interface Lineage1 {
  attemptId: Attemptid2;
  children: Children12;
  kind: Kind58;
  parents: Parents;
}
export interface ProposalReply {
  discoveries: Discoveries;
  fields: Fields1;
  lineage: Lineage2;
  payload: JsonValue;
  relations?: Relations2;
  schemaVersion: Schemaversion7;
}
export interface Discovery {
  key: Key1;
  pointer: Pointer4;
  semanticType: Semantictype4;
}
export interface ProposalField {
  effectiveCellIds: Effectivecellids;
  evidence: Evidence17;
  fieldKey: Fieldkey6;
  item: Item;
  pointer: Pointer5;
}
export interface DiscoverySelector {
  key: Key2;
  kind: Kind59;
}
export interface HandleSelector {
  itemHandle: Itemhandle6;
  kind: Kind60;
}
export interface ProposalLineage {
  children: Children13;
  kind: Kind61;
  parents: Parents1;
}
export interface ProposalRelation {
  evidence: Evidence18;
  kind: Kind62;
  relation: Relation1;
  subject: Subject;
  target: Target1;
}
export interface RelationDiscoverySelector {
  key: Key3;
  kind: Kind63;
}
export interface ExistingRelationSelector {
  kind: Kind64;
  relationId: Relationid2;
}
export interface FieldSidecar {
  effectiveCellIds: Effectivecellids1;
  evidence: Evidence19;
  fieldKey: Fieldkey7;
  itemHandle: Itemhandle7;
  pointer: Pointer6;
}
export interface PublicationOutcome {
  errorCode: Errorcode5;
  intentId: Intentid;
  state: State7;
  workspaceHash: Workspacehash;
}
export interface ReviewReceipt {
  attemptId: Attemptid3;
  completedAt: Completedat;
  expectedChecks: Expectedchecks;
  id: Id53;
  reply: ReviewReply;
  reviewInputHash: Reviewinputhash1;
}
export interface CheckTarget {
  ruleId: Ruleid1;
  targetId: Targetid1;
}
export interface ReviewReply {
  results: Results;
}
export interface ReviewDisposition {
  actionable: Actionable;
  disposition: Disposition1;
  evidence: Evidence20;
  reason: Reason1;
  ruleId: Ruleid2;
  targetId: Targetid2;
}
export interface RelationAllocation {
  discoveryAttemptId: Discoveryattemptid1;
  key: Key4;
  kind: Kind65;
  operationId: Operationid3;
  relationId: Relationid3;
  subjectId: Subjectid1;
  targetId: Targetid3;
  taskId: Taskid3;
}
export interface ReviewInputRecord {
  attemptId: Attemptid4;
  id: Id54;
  inputHash: Inputhash2;
  value: ReviewInput;
}
export interface ReviewInput {
  allowTextRewrite: Allowtextrewrite2;
  effectiveCells: Effectivecells;
  handleMap: Handlemap;
  occurrenceContext: JsonValue;
  occurrenceIndependent: Occurrenceindependent;
  packageHash: Packagehash5;
  policy: ModelCapture;
  proposalHash: Proposalhash2;
  protocol: Protocol;
  relations: Relations3;
  rules: Rules;
  schemaVersion: Schemaversion8;
  semanticContext: Semanticcontext;
  sourceSpans: Sourcespans;
  sourceTexts: Sourcetexts;
  targets: Targets;
}
export interface Check {
  id: Id55;
  kind: Kind66;
  parameters: CheckParameters;
  version: Version1;
}
export interface CheckParameters {
  fields: Fields2;
  instructions: Instructions;
}
export interface Semanticcontext {
  [k: string]: JsonValue;
}
export interface Sourcetexts {
  [k: string]: string;
}
export interface TaskInputRecord {
  capturedAt: Capturedat;
  id: Id56;
  inputHash: Inputhash3;
  taskId: Taskid4;
  value: Value2;
}
export interface Value2 {
  [k: string]: JsonValue;
}
export interface TaskResultRecord {
  disposition: Disposition2;
  id: Id57;
  inputHash: Inputhash4;
  issueIds: Issueids;
  itemHandles: Itemhandles;
  sourceSpans: Sourcespans1;
  taskId: Taskid5;
  value: JsonValue;
}
export interface ImportTask {
  allowedHandles: Allowedhandles;
  attemptIds: Attemptids;
  blockId: Blockid7;
  dependencies: Dependencies3;
  expectedChecks: Expectedchecks1;
  id: Id58;
  inputHash: Inputhash5;
  issueIds: Issueids1;
  kind: Kind67;
  operationId: Operationid4;
  proposalHash: Proposalhash3;
  receiptIds: Receiptids1;
  state: State9;
}
export interface TemplatePackage {
  assets: Assets;
  blocks: Blocks2;
  compilerVersion: Compilerversion;
  configHash: Confighash;
  definition: TemplateDefinition;
  id: Id71;
  manifest: CompilationManifest;
  operationVersion: Operationversion;
  originalBase64: Originalbase64;
  originalFormat: Originalformat;
  originalHash: Originalhash;
  packageHash: Packagehash6;
  projectionVersion: Projectionversion;
  recipe: CompiledRecipe;
  revision: Revision41;
  schemaVersion: Schemaversion10;
}
export interface CapturedAsset {
  bytesBase64: Bytesbase64;
  id: Id59;
  mimeType: Mimetype1;
  path: Path;
  role: Role2;
  sha256: Sha256;
  size: Size2;
}
export interface CompiledBlock {
  dependencyOrder: Dependencyorder;
  fullSchema: Fullschema;
  id: Id60;
  providerSchema: Providerschema;
  serverOnly: Serveronly;
}
export interface Fullschema {
  [k: string]: JsonValue;
}
export interface Providerschema {
  [k: string]: JsonValue;
}
export interface TemplateDefinition {
  assets: Assets1;
  blocks: Blocks3;
  content_definitions: ContentDefinitions;
  fact_types: FactTypes;
  layout: Layout;
  model: ModelInstructions;
  operations: Operations1;
  provenance: Provenance12;
  schema_version: SchemaVersion1;
  source: SourcePolicy;
  style: Style;
  template: TemplateIdentity;
}
export interface AssetDeclaration {
  embedding: Embedding;
  id: Id61;
  mime_type: MimeType;
  path: Path1;
  role: Role3;
}
export interface Block1 {
  bindings: Bindings;
  checks: Checks;
  content_schema: ContentSchema;
  depends_on: DependsOn;
  extract: Extract;
  id: Id62;
  mode: Mode2;
  operation: Operation;
  placement: Placement;
  rewrite: Rewrite;
  selectors: Selectors;
  view: View;
  when: Condition | null;
}
export interface Binding {
  field: Field4;
  item_pointer?: ItemPointer;
  pointer: Pointer7;
  relation: BindingRelation | null;
  semantic_type: SemanticType;
}
export interface BindingRelation {
  kind: Kind68;
  subject_pointer: SubjectPointer;
}
export interface ContentSchema {
  [k: string]: JsonValue;
}
export interface Rewrite {
  fields: Fields3;
  instructions: Instructions1;
}
export interface InputRef {
  id: Id63;
  kind: Kind69;
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
  id: Id64;
  relations: Relations4;
  schema: Schema;
  schema_version: SchemaVersion;
}
export interface BuiltinFields {
  [k: string]: BuiltinFieldBinding;
}
export interface BuiltinFieldBinding {
  field: Field5;
  period: Period1;
}
export interface RelationDeclaration {
  kind: Kind70;
  target_types: TargetTypes;
}
export interface Schema {
  [k: string]: JsonValue;
}
export interface ModelInstructions {
  extract: Extract1;
  permission: Permission;
  rewrite: Rewrite1;
}
export interface PartitionOperation {
  depends_on: DependsOn1;
  id: Id65;
  inputs: Inputs;
  kind: Kind71;
  parameters: PartitionParameters;
  version: Version2;
}
export interface PartitionParameters {
  compact: Compact;
  detailed: Detailed;
  years: Years;
}
export interface RoleOperation {
  depends_on: DependsOn2;
  id: Id66;
  inputs: Inputs1;
  kind: Kind72;
  parameters: RoleParameters;
  version: Version3;
}
export interface RoleParameters {
  matched: Matched;
  otherwise: Otherwise;
  role_families: RoleFamilies;
}
export interface SkillsOperation {
  depends_on: DependsOn3;
  id: Id67;
  inputs: Inputs2;
  kind: Kind73;
  parameters: SkillsParameters;
  version: Version4;
}
export interface SkillsParameters {
  groups: Groups;
  uncertain_group: UncertainGroup;
}
export interface PeriodOperation {
  depends_on: DependsOn4;
  id: Id68;
  inputs: Inputs3;
  kind: Kind74;
  parameters: PeriodParameters;
  version: Version5;
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
  id: Id69;
  inputs: Inputs4;
  kind: Kind75;
  parameters: EmptyParameters;
  version: Version6;
}
export interface EmptyParameters {}
export interface Provenance12 {
  [k: string]: JsonValue;
}
export interface SourcePolicy {
  retain_original: RetainOriginal;
  retain_unmapped_facts: RetainUnmappedFacts;
}
export interface TemplateIdentity {
  default_locale: DefaultLocale;
  id: Id70;
  name: Name1;
  revision: Revision40;
}
export interface CompilationManifest {
  capabilities: Capabilities1;
  profileId: Profileid;
  profileVersion: Profileversion;
  serverOnly: Serveronly1;
  supportedFormats: Supportedformats;
}
export interface Serveronly1 {
  [k: string]: string[];
}
export interface ProjectV6 {
  assets: Assets2;
  createdAt: Createdat1;
  document: RichDocumentV2;
  evidenceRecords: Evidencerecords;
  exportInputs?: Exportinputs;
  exports: Exports;
  facts: WorkingFactsV2;
  importCoverage: Importcoverage;
  importIssues: Importissues;
  operations: Operations2;
  projectId: Projectid3;
  renders: Renders;
  revision: Revision44;
  schemaVersion: Schemaversion13;
  sources: Sources2;
  templateOperations: Templateoperations1;
  templatePackage: TemplatePackage;
}
export interface LocalImageAsset {
  height: Height4;
  id: Id72;
  mimeType: Mimetype2;
  path: Path2;
  sha256: Sha2561;
  size: Size3;
  width: Width5;
}
export interface RichDocumentV2 {
  regions: Regions1;
  revision: Revision43;
  schemaVersion: Schemaversion11;
}
export interface TemplateRegion {
  blocks: Blocks4;
  id: Id73;
  revision: Revision42;
  role: Role4;
}
export interface ImmutableFactEvidence {
  evidence: Evidence21;
  id: Id74;
  rawText: Rawtext5;
}
export interface TemplateExportCapture {
  attemptId: Attemptid5;
  request: CapturedTemplateRenderInputV1;
  snapshot: TemplateSnapshotIdentity;
}
export interface CapturedTemplateRenderInputV1 {
  assets: Assets3;
  document: RichDocumentV2;
  documentHash: Documenthash3;
  facts: WorkingFactsV2;
  factsHash: Factshash3;
  packageHash: Packagehash7;
  presentationHash: Presentationhash2;
  renderInputVersion: Renderinputversion1;
  renderer: TemplateRendererIdentity;
  schemaVersion: Schemaversion12;
}
export interface TemplateRenderAsset {
  id: Id75;
  path: Path3;
  sha256: Sha2562;
  size: Size4;
}
export interface TemplateRendererIdentity {
  id: Id76;
  sha256: Sha2563;
  version: Version7;
}
export interface SpanCoverage {
  blockIds: Blockids4;
  disposition: Disposition3;
  itemHandle: Itemhandle8;
  reason: Reason2;
  span: SourceSpan;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision2;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id77;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface Rules1 {
  markdown: Markdown;
  revision: Revision45;
  sha256: Sha2564;
}
export interface TemplateSyncRecord {
  actionId: Actionid7;
  blockIds: Blockids5;
  capture: ActionCapture | null;
  dependencies: Dependencies4;
  errorCode: Errorcode6;
  factIds: Factids1;
  fieldKeys: Fieldkeys2;
  id: Id78;
  instruction?: Instruction1;
  kind?: Kind76;
  lifecycleId: Lifecycleid2;
  ownershipConflict: TemplateOwnershipConflict | null;
  proposedSteps?: Proposedsteps1;
  ready?: Ready1;
  resolutionOf?: TemplateSyncResolution | null;
  rewriteResult?: Rewriteresult1;
  rewriteSource?: Rewritesource1;
  schemaVersion: Schemaversion15;
  selection?: RichSelection | null;
  status: Status10;
}
export interface RichSyncRecord {
  actionId: Actionid8;
  blockIds: Blockids6;
  dependencies: Dependencies5;
  errorCode: Errorcode7;
  factIds: Factids2;
  fieldKeys: Fieldkeys3;
  id: Id79;
  instruction?: Instruction2;
  kind?: Kind77;
  proposedSteps?: Proposedsteps2;
  ready?: Ready2;
  rewriteResult?: Rewriteresult2;
  rewriteSource?: Rewritesource2;
  selection?: RichSelection | null;
  status: Status11;
}
export interface PutBlock {
  afterId: Afterid2;
  beforeRevision: Beforerevision11;
  block: Block2;
  keepChildren?: Keepchildren1;
  kind: Kind78;
  parentId: Parentid2;
}
export interface ParagraphBlock {
  children: Children14;
  content: Content27;
  id: Id93;
  props: ParagraphProps;
  provenance: Provenance24;
  revision: Revision58;
  type: Type32;
}
export interface HeadingBlock {
  children: Children15;
  content: Content26;
  id: Id92;
  props: HeadingProps;
  provenance: Provenance23;
  revision: Revision57;
  type: Type31;
}
export interface BulletBlock {
  children: Children16;
  content: Content25;
  id: Id91;
  props: ParagraphProps;
  provenance: Provenance22;
  revision: Revision56;
  type: Type30;
}
export interface NumberedBlock {
  children: Children17;
  content: Content24;
  id: Id90;
  props: NumberedProps;
  provenance: Provenance21;
  revision: Revision55;
  type: Type29;
}
export interface ChecklistBlock {
  children: Children18;
  content: Content23;
  id: Id89;
  props: ChecklistProps;
  provenance: Provenance20;
  revision: Revision54;
  type: Type28;
}
export interface ToggleBlock {
  children: Children19;
  content: Content22;
  id: Id88;
  props: ParagraphProps;
  provenance: Provenance19;
  revision: Revision53;
  type: Type27;
}
export interface QuoteBlock {
  children: Children20;
  content: Content21;
  id: Id87;
  props: ParagraphProps;
  provenance: Provenance18;
  revision: Revision52;
  type: Type26;
}
export interface CodeBlock {
  children: Children21;
  content: Content20;
  id: Id86;
  props: CodeProps;
  provenance: Provenance17;
  revision: Revision51;
  type: Type25;
}
export interface DividerBlock {
  children: Children22;
  content: Content19;
  id: Id85;
  props: EmptyProps;
  provenance: Provenance16;
  revision: Revision50;
  type: Type24;
}
export interface TableBlock {
  children: Children23;
  content: TableContent;
  id: Id84;
  props: ParagraphProps;
  provenance: Provenance15;
  revision: Revision49;
  type: Type23;
}
export interface ImageBlock {
  children: Children24;
  content: Content17;
  id: Id81;
  props: ImageProps;
  provenance: Provenance14;
  revision: Revision47;
  type: Type22;
}
export interface SectionBlock {
  children: Children25;
  content: Content15;
  id: Id80;
  props: SectionProps;
  provenance: Provenance13;
  revision: Revision46;
  type: Type21;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text11;
  type: Type18;
}
export interface Hyperlink {
  content: Content16;
  href: Href2;
  type: Type19;
}
export interface FactFieldSpan {
  bindingId: Bindingid2;
  bindingRootId?: Bindingrootid1;
  fieldKey: Fieldkey8;
  recordId: Recordid13;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision1;
  text: Text12;
  type: Type20;
}
export interface ImageProps {
  alignment: Alignment8;
  alt: Alt1;
  assetId: Assetid1;
  caption: Caption1;
  height: Height5;
  width: Width6;
}
export interface TableContent {
  columnWidths: Columnwidths1;
  headerCols?: Headercols1;
  headerRows: Headerrows1;
  rows: Rows1;
}
export interface TableRow {
  cells: Cells2;
  id: Id83;
}
export interface TableCell {
  alignment?: Alignment9;
  backgroundColor?: Backgroundcolor8;
  colspan?: Colspan1;
  content: Content18;
  id: Id82;
  revision: Revision48;
  rowspan?: Rowspan1;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision12;
  blockId: Blockid8;
  cellId: Cellid8;
  content: Content28;
  end: End4;
  field: Field6;
  kind: Kind79;
  start: Start5;
}
export interface RichWarning {
  blockIds: Blockids7;
  code: Code4;
  count?: Count;
  evidence: Evidence22;
  id: Id94;
  locations?: Locations;
  recordIds: Recordids;
}
export interface Evidence23 {
  sourceId: Sourceid3;
  sourceRevision: Sourcerevision2;
  unitId: Unitid4;
  unitRevision: Unitrevision2;
}
export interface WarningLocation {
  page?: Page3;
  sourceId: Sourceid4;
}
