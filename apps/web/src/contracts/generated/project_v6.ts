export type Height = number;
export type Id = string;
export type Mimetype = "image/png" | "image/jpeg";
export type Path = string;
export type Sha256 = string;
export type Size = number;
export type Width = number;
export type Assets = LocalImageAsset[];
export type Createdat = string;
/**
 * @minItems 3
 * @maxItems 3
 */
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
export type Size1 = number | null;
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
export type Kind = "citation";
export type Recordid3 = string;
export type Fieldkey2 = string;
export type Id3 = string;
export type Kind1 = "field_binding";
export type Recordid4 = string;
export type Id4 = string;
export type Kind2 = "working_owner";
export type Recordid5 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id5 = string;
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
export type Id6 = string;
export type Alignment2 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Height1 = number;
export type Width1 = number;
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
export type Id7 = string;
export type Revision2 = number;
export type Rowspan = number;
export type Cells = TemplateTableCell[];
export type Id8 = string;
export type Rows = TemplateTableRow[];
export type Id9 = string;
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
export type Id10 = string;
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
export type Id11 = string;
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
export type Id12 = string;
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
export type Id13 = string;
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
export type Id14 = string;
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
export type Id15 = string;
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
export type Id16 = string;
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
export type Id17 = string;
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
export type Id18 = string;
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
export type Id19 = string;
export type Revision13 = number;
export type Role = "header" | "sidebar" | "main";
export type Revision14 = number;
export type Schemaversion = 2;
export type Evidence2 = EvidenceSpan[];
export type Id20 = string;
export type Rawtext = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Attemptid = string;
export type Id21 = string;
export type Path1 = string;
export type Sha2561 = string;
export type Size2 = number;
export type Assets1 = TemplateRenderAsset[];
export type Documenthash = string;
export type Cellid2 = string;
export type Fieldkey3 = string;
export type Periodid = string | null;
export type Itemhandle1 = string;
export type Recordid6 = string;
export type Semanticschemahash = string;
export type Semantictype = string;
export type Builtinidentities = BuiltinItemIdentity[];
export type Active = boolean;
export type Admissionreceiptids = string[];
export type Evidence3 = SourceSpan[];
export type Fieldkey4 = string;
export type Id22 = string;
export type Manualscopeid = string | null;
export type Observationids = string[];
export type Origin = "model" | "source" | "human";
export type Rawinput = string;
export type Revision15 = number;
export type State = "admitted" | "human_raw" | "pending_manual" | "uncertain";
export type JsonValue = unknown;
export type Usercorrected = boolean;
export type Cells1 = ExtensionCell[];
export type Copyofrecordid = string | null;
export type Id23 = string;
export type Itemhandle2 = string;
export type Observationids1 = string[];
export type Active1 = boolean;
export type Id24 = string;
export type Kind4 = "owned_by" | "extension_of" | "related_to";
export type Revision16 = number;
export type Subjectid = string;
export type Targetid = string;
export type Relations = Relation[];
export type Revision17 = number;
export type Schemaversion1 = 1;
export type Semanticschemahash1 = string;
export type Semantictype1 = string;
export type Extensions = ExtensionRecord[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status = "complete" | "partial";
export type Code1 = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page = number | null;
export type Section = string;
export type Sourceid2 = string;
export type Unitid2 = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Actionid = string;
export type Blockids = string[];
export type Cellids1 = string[];
export type Id25 = string;
export type Rawinput1 = string;
export type Manualscopes = ManualEditScope[];
export type Mode = "structured" | "digest" | "imported";
export type Admission = "provisional" | "accepted" | "rejected" | "uncertain";
export type Evidence4 = SourceSpan[];
export type Fieldkey5 = string;
export type Id26 = string;
export type Itemhandle3 = string;
export type Ownerrelations = Relation[];
export type Proposalhash = string;
export type Rawinput2 = string;
export type Receiptids = string[];
export type Observations = Observation[];
export type Evidence5 = EvidenceSpan[];
export type Id27 = string;
export type Kind5 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext1 = string;
export type Revision18 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected1 = boolean;
export type Value = string | null;
export type Origin1 = "source" | "user";
export type Revision19 = number;
export type Usercorrected2 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence6 = EvidenceSpan[];
export type Id28 = string;
export type Kind6 = "detail";
export type Label = string;
export type Origin2 = "source" | "user";
export type Revision20 = number;
export type Usercorrected3 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id29 = string;
export type Kind7 = "employment";
export type Origin3 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext2 = string;
export type Revision21 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence8 = EvidenceSpan[];
export type Id30 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext3 = string;
export type Revision22 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected5 = boolean;
export type Value1 = boolean | null;
export type Revision23 = number;
export type Periods = WorkingPeriod[];
export type Revision24 = number;
export type Usercorrected6 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id31 = string;
export type Jobid = string;
export type Kind8 = "subproject";
export type Origin4 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision25 = number;
export type Usercorrected7 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id32 = string;
export type Jobid1 = string | null;
export type Kind9 = "technology";
export type Origin5 = "source" | "user";
export type Revision26 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected8 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id33 = string;
export type Kind10 = "education";
export type Origin6 = "source" | "user";
export type Revision27 = number;
export type Usercorrected9 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id34 = string;
export type Kind11 = "language";
export type Origin7 = "source" | "user";
export type Revision28 = number;
export type Usercorrected10 = boolean;
export type Evidence13 = EvidenceSpan[];
export type Id35 = string;
export type Kind12 = "certification";
export type Origin8 = "source" | "user";
export type Revision29 = number;
export type Usercorrected11 = boolean;
export type Evidence14 = EvidenceSpan[];
export type Id36 = string;
export type Jobid2 = string | null;
export type Kind13 = "claim";
export type Origin9 = "source" | "user";
export type Revision30 = number;
export type Subprojectid1 = string | null;
export type Usercorrected12 = boolean;
export type Evidence15 = EvidenceSpan[];
export type Id37 = string;
export type Jobid3 = string | null;
export type Kind14 = "metric";
export type Origin10 = "source" | "user";
export type Revision31 = number;
export type Subprojectid2 = string | null;
export type Usercorrected13 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext4 = string;
export type Revision32 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected14 = boolean;
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
export type Evidence16 = EvidenceSpan[];
export type Id38 = string;
export type Jobid4 = string | null;
export type Kind15 = "leadership";
export type Origin11 = "source" | "user";
export type Revision33 = number;
export type Subprojectid3 = string | null;
export type Usercorrected15 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext5 = string;
export type Revision34 = number;
export type Status5 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence17 = EvidenceSpan[];
export type Id39 = string;
export type Kind16 = "unresolved";
export type Origin12 = "source" | "user";
export type Revision35 = number;
export type Status6 = "unresolved" | "pending" | "conflict";
export type Usercorrected17 = boolean;
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
export type Revision36 = number;
export type Schemaversion2 = 2;
export type Actionid1 = string;
export type Orderindex = number;
export type Recordid7 = string;
export type Revision37 = number;
export type Tombstones = RecordTombstone[];
export type Factshash = string;
export type Packagehash1 = string;
export type Presentationhash = string;
export type Renderinputversion = 1;
export type Id40 = string;
export type Sha2562 = string;
export type Version = string;
export type Schemaversion3 = 1;
export type Documenthash1 = string;
export type Documentrevision = number;
export type Factshash1 = string;
export type Packagehash2 = string;
export type Presentationhash1 = string;
export type Projectid = string;
export type Projectrevision = number;
export type Exportinputs = TemplateExportCapture[];
export type Artifacthash = string | null;
export type Assetshash = string;
export type Documenthash2 = string;
export type Errorcode = string | null;
export type Factshash2 = string;
export type Id41 = string;
export type Packagehash3 = string;
export type Presentationhash2 = string;
export type Publicationintentid = string | null;
export type Rendererhash = string;
export type State1 = "pending" | "running" | "completed" | "failed";
export type Exports = ExportAttempt[];
export type Blockids1 = string[];
export type Disposition = "accepted" | "fallback" | "source_only" | "multiple_views";
export type Itemhandle4 = string | null;
export type Reason = string | null;
export type Importcoverage = SpanCoverage[];
export type Blockids2 = string[];
export type Category1 = "content_violation" | "uncertain_interpretation" | "check_not_completed";
export type Code2 = string;
export type Id42 = string;
export type Importedfingerprint = string;
export type Lifecycleid = string;
export type Message = string;
export type Retiredbyaction = string | null;
export type Reviewinputhash = string | null;
export type Ruleid = string | null;
export type State2 = "active" | "retired";
export type Targetids = string[];
export type Taskid = string;
export type Importissues = ImportIssue[];
export type Actionid2 = string | null;
export type Fingerprint = string | null;
export type Id43 = string;
export type Kind17 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision38 = number;
export type Dependencies = DependencyStamp[];
export type Errorcode1 = string | null;
export type Id44 = string;
export type Kind18 =
  | "extract"
  | "assess_resume"
  | "normalize_semantics"
  | "draft_prose"
  | "render"
  | "project_save"
  | "rewrite_prose"
  | "reconcile_edits";
export type Status7 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Operations = RichOperation[];
export type Projectid1 = string;
export type Documentrevision1 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id45 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision39 = number;
export type Schemaversion4 = 6;
export type Byteref = string;
export type Bytesha256 = string;
export type Id46 = string;
export type Mimetype1 = string;
export type Originalname = string;
export type Id47 = string;
export type Origin13 = "user";
export type Revision40 = number;
export type Text4 = string;
export type Unitid3 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision41 = number;
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id48 = string;
export type Column = number | null;
export type Index = number;
export type Kind19 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision42 = number;
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
export type Style = string | null;
export type Text5 = string;
export type Units = SourceUnit[];
export type Code3 = string;
export type Page1 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources = Source[];
export type Admittedat = string | null;
export type Discoveryattemptid = string;
export type Discoveryhash = string;
export type Itemhandle5 = string;
export type Key = string;
export type Operationid = string;
export type Recordid8 = string;
export type Semantictype2 = string;
export type Taskid1 = string;
export type Allocations = HandleAllocation[];
export type Authorizationid = string | null;
export type Evidencehash = string | null;
export type State3 = "pending" | "verified" | "unknown";
export type Witness = string | null;
export type Dispatchedat = string | null;
export type Errorcode2 = string | null;
export type Id49 = string;
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
export type State4 = "reserved" | "dispatch_started" | "returned" | "outcome_unknown" | "reconciled" | "released";
export type Taskid2 = string;
export type Cachedinputtokens = number | null;
export type Complete1 = boolean;
export type Inputtokens = number | null;
export type Outputtokens = number | null;
export type Attempts = ImportAttempt[];
export type Authorityhash = string;
export type Authorizedat = string;
export type Dependencyhash = string;
export type Id50 = string;
export type Kind20 = "start" | "resume";
export type State5 = "active" | "cancelled";
export type Authorizations = ImportAuthorization[];
export type Allowtextrewrite = boolean;
export type Authorityhash1 = string;
export type Dependencyhash1 = string;
export type Packagehash4 = string;
export type Callcap = number;
export type Cleanupseconds = 5;
export type Concurrency = 1;
export type Fallbackrepairs = 1;
export type Finalizationseconds = number;
export type Primaryrepairs = 1;
export type Processingseconds = number;
export type Itemhandle6 = string;
export type Recordid9 = string;
export type Recordrevision = number;
export type Semanticschemahash2 = string;
export type Semantictype3 = string;
export type Captureditems = CapturedItemIdentity[];
export type Attemptid1 = string;
export type Evidencehash1 = string;
export type Neverdispatched = boolean;
export type Ownerhash = string;
export type Verifiedat = string;
export type Witness1 = string;
export type Cleanuprecords = AttemptCleanupRecord[];
export type Clientrequestid = string | null;
export type Expiresat = string | null;
export type Exportattempts = ExportAttempt[];
export type Authorityhash2 = string;
export type Authorizationid1 = string;
export type Candidatehash = string;
export type Coveragehash = string;
export type Dependencyhash2 = string;
export type Documenthash3 = string;
export type Expiresat1 = string;
export type Factshash3 = string;
export type Id51 = string;
export type Issueshash = string;
export type Operationid2 = string;
export type Packagehash5 = string;
export type Sourcehash = string;
export type Startedat = string;
export type Finalizationhistory = FinalizationCandidate[];
export type Id52 = string;
export type Inferenceclosed = boolean;
export type Issues = ImportIssue[];
export type Lastobservedat = string | null;
export type Projectid2 = string;
export type Admittedcellids = string[];
export type Admittedrelationids = string[];
export type Appliedreceiptid = string | null;
export type Attemptid2 = string;
export type Errors = string[];
export type Id53 = string;
export type Inputhash1 = string;
export type Attemptid3 = string;
export type Children12 = string[];
export type Kind21 = "add" | "split" | "merge";
export type Parents = string[];
export type Lineage = Lineage1[];
export type Proposalhash1 = string;
export type Rawreturn1 = string;
export type Rawreturnhash1 = string;
export type Key1 = string;
export type Pointer = string;
export type Semantictype4 = string;
export type Discoveries = Discovery[];
export type Effectivecellids = string[];
export type Evidence18 = SourceSpan[];
export type Fieldkey6 = string;
export type Item = DiscoverySelector | HandleSelector;
export type Key2 = string;
export type Kind22 = "discovery_key";
export type Itemhandle7 = string;
export type Kind23 = "handle";
export type Pointer1 = string;
export type Fields = ProposalField[];
export type Children13 = string[];
export type Kind24 = "add" | "split" | "merge";
export type Parents1 = string[];
export type Lineage2 = ProposalLineage[];
export type Evidence19 = SourceSpan[];
export type Kind25 = "owned_by" | "extension_of" | "related_to";
export type Relation1 = RelationDiscoverySelector | ExistingRelationSelector;
export type Key3 = string;
export type Kind26 = "discovery_key";
export type Kind27 = "relation_id";
export type Relationid = string;
export type Subject = DiscoverySelector | HandleSelector;
export type Target = DiscoverySelector | HandleSelector;
export type Relations2 = ProposalRelation[];
export type Schemaversion5 = 1;
export type Effectivecellids1 = string[];
export type Evidence20 = SourceSpan[];
export type Fieldkey7 = string;
export type Itemhandle8 = string;
export type Pointer2 = string;
export type Resolvedfields = FieldSidecar[];
export type Resolvedrelations = Relation[];
export type State6 = "invalid" | "provisional" | "accepted" | "rejected";
export type Proposals = ProposalRecord[];
export type Errorcode3 = string | null;
export type Intentid = string | null;
export type State7 = "pending" | "saved" | "failed_before_replacement" | "outcome_unknown" | "cancelled";
export type Workspacehash = string | null;
export type Attemptid4 = string;
export type Completedat = string;
export type Ruleid1 = string;
export type Targetid1 = string;
export type Expectedchecks = CheckTarget[];
export type Id54 = string;
export type Actionable = boolean;
export type Disposition2 = "satisfied" | "violation" | "uncertain";
export type Evidence21 = SourceSpan[];
export type Reason1 = string;
export type Ruleid2 = string;
export type Targetid2 = string;
export type Results = ReviewDisposition[];
export type Reviewinputhash1 = string;
export type Receipts = ReviewReceipt[];
export type Discoveryattemptid1 = string;
export type Key4 = string;
export type Kind28 = "owned_by" | "extension_of" | "related_to";
export type Operationid3 = string;
export type Relationid1 = string;
export type Subjectid1 = string;
export type Targetid3 = string;
export type Taskid3 = string;
export type Relationallocations = RelationAllocation[];
export type Attemptid5 = string;
export type Id55 = string;
export type Inputhash2 = string;
export type Allowtextrewrite1 = boolean;
export type Effectivecells = ExtensionCell[];
export type Ref = string;
export type Text6 = string;
export type Evidence22 = EvidenceOption[];
export type Handlemap = (HandleAllocation | CapturedItemIdentity)[];
export type Occurrenceindependent = boolean;
export type Packagehash6 = string;
export type Proposalhash2 = string;
export type Protocol = "template_import_v1";
export type Relations3 = Relation[];
export type Id56 = string;
export type Kind29 =
  | "content_schema"
  | "evidence_identity"
  | "protected_values"
  | "claim_ownership"
  | "complete_assignment"
  | "semantic_support"
  | "task_result_separation"
  | "attribution";
export type Fields1 = string[];
export type Instructions = string[];
export type Version1 = 1;
export type Rules = Check[];
export type Schemaversion6 = 1 | 2;
export type Sourcespans = SourceSpan[];
export type Targets = CheckTarget[];
export type Reviewinputs = ReviewInputRecord[];
export type Schemaversion7 = 1;
export type State8 =
  "captured" | "processing" | "cleanup_pending" | "finalizing" | "published" | "cancelled" | "failed" | "fenced";
export type Capturedat = string;
export type Id57 = string;
export type Inputhash3 = string;
export type Taskid4 = string;
export type Taskinputs = TaskInputRecord[];
export type Disposition3 = "admitted" | "derived" | "source_fallback" | "empty";
export type Id58 = string;
export type Inputhash4 = string;
export type Issueids = string[];
export type Itemhandles = string[];
export type Sourcespans1 = SourceSpan[];
export type Taskid5 = string;
export type Taskresults = TaskResultRecord[];
export type Allowedhandles = string[];
export type Attemptids = string[];
export type Blockid = string;
export type Dependencies1 = string[];
export type Expectedchecks1 = CheckTarget[];
export type Id59 = string;
export type Inputhash5 = string;
export type Issueids1 = string[];
export type Kind30 = "extract" | "rewrite" | "derive" | "source_copy";
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
export type Id60 = string;
export type Mimetype2 = string;
export type Path2 = string;
export type Role1 = "font" | "logo" | "icon" | "catalog";
export type Sha2563 = string;
export type Size3 = number;
export type Assets2 = CapturedAsset[];
export type Dependencyorder = number;
export type Id61 = string;
export type Serveronly = string[];
export type Blocks1 = CompiledBlock[];
export type Compilerversion = string;
export type Confighash = string;
export type Embedding = "allowed" | "not_applicable";
export type Id62 = string;
export type MimeType = string;
export type Path3 = string;
export type Role2 = "font" | "logo" | "icon" | "catalog";
export type Assets3 = AssetDeclaration[];
export type Field = string;
export type ItemPointer = string | null;
export type Pointer3 = string;
export type Kind31 = "owned_by" | "extension_of" | "related_to";
export type SubjectPointer = string;
export type SemanticType = string;
export type Bindings = Binding[];
export type Checks = Check[];
export type DependsOn = string[];
export type Extract = string[];
export type Id63 = string;
export type Mode1 = "model" | "derived" | "source_copy";
export type Operation = string | null;
export type Order1 = number;
export type Region = "header" | "sidebar" | "main";
export type Fields2 = string[];
export type Instructions1 = string[];
export type Id64 = string;
export type Kind32 = "source" | "fact_type" | "block" | "operation";
export type Selectors = InputRef[];
export type FallbackStyle = string | null;
export type Heading = "none" | "plain" | "band";
export type Inset = number;
export type ItemGap = number;
export type Mode2 = "object" | "items";
export type Background = string | null;
export type DetailStyle = string | null;
export type ExperienceField = string | null;
export type Field1 = string | null;
export type Fields3 = string[];
export type HeaderSlot = ("name" | "profession") | null;
export type ItemField = string | null;
export type NameField = string | null;
export type Separator = string;
export type Style1 = string;
export type Type17 = "text" | "join_fields" | "join_items" | "bullets" | "tags" | "period" | "link" | "focus_entry";
export type UrlField = string | null;
export type Nodes = ViewNode[];
export type Equals = string;
export type Operation1 = string;
export type Blocks2 = Block[];
export type Field2 = string;
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
export type Id65 = string;
export type Kind33 = "owned_by" | "extension_of" | "related_to";
export type TargetTypes = string[];
export type Relations4 = RelationDeclaration[];
export type SchemaVersion = string;
export type FactTypes = FactType[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id66 = "header" | "sidebar" | "main";
export type Width2 = number;
export type X = number;
export type Regions1 = Region1[];
export type Extract1 = string[];
export type Permission = "allowTextRewrite";
export type Rewrite1 = string[];
export type DependsOn1 = string[];
export type Id67 = string;
export type Inputs = InputRef[];
export type Kind34 = "partition_employment";
export type Compact = string;
export type Detailed = string;
export type Years = number;
export type Version2 = 1;
export type DependsOn2 = string[];
export type Id68 = string;
export type Inputs1 = InputRef[];
export type Kind35 = "select_role_branch";
export type Field3 = string;
export type SemanticType1 = string;
export type Matched = string;
export type Otherwise = string;
export type RoleFamilies = string[];
export type Version3 = 1;
export type DependsOn3 = string[];
export type Id69 = string;
export type Inputs2 = InputRef[];
export type Kind36 = "assign_skills";
export type Groups = string[];
export type UncertainGroup = string;
export type Version4 = 1;
export type DependsOn4 = string[];
export type Id70 = string;
export type Inputs3 = InputRef[];
export type Kind37 = "format_period";
export type Separator1 = string;
export type Version5 = 1;
export type DependsOn5 = string[];
export type Id71 = string;
export type Inputs4 = InputRef[];
export type Kind38 = "preserve_stated_text";
export type Version6 = 1;
export type Operations1 = (
  PartitionOperation | RoleOperation | SkillsOperation | PeriodOperation | PreserveOperation
)[];
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
export type Style3 = string;
export type Text7 = string;
export type Color1 = string;
export type FollowHeader = true;
export type Width3 = number;
export type X1 = number;
export type X2 = number;
export type Y = number;
export type Asset = string;
export type Fit = "contain";
export type Height2 = number;
export type Top = number;
export type Width4 = number;
export type X3 = number;
export type NameTop = number;
export type Overflow = "grow_header_and_move_body";
export type ProfessionTop = number;
export type BodyBottom = number;
export type ContinuationBodyTop = number;
export type FirstBodyTop = number;
export type Height3 = number;
export type Width5 = number;
export type Background1 = string;
export type HeadingStyle = string;
export type Height4 = number;
export type TextInset = number;
export type Color2 = string;
export type Font1 = string;
export type LineHeight = number;
export type Size4 = number;
export type DefaultLocale = string;
export type Id72 = string;
export type Name = string;
export type Revision43 = string;
export type Id73 = string;
export type Capabilities = string[];
export type Profileid = string;
export type Profileversion = string;
export type Supportedformats = string[];
export type Operationversion = string;
export type Originalbase64 = string;
export type Originalformat = "yaml" | "json";
export type Originalhash = string;
export type Packagehash7 = string;
export type Projectionversion = string;
export type Capabilities1 = string[];
export type Renderinputversion1 = 1;
export type Schemaversion8 = 1;
export type Revision44 = string;
export type Schemaversion9 = 1;

export interface ProjectV6 {
  assets: Assets;
  createdAt: Createdat;
  document: RichDocumentV2;
  evidenceRecords: Evidencerecords;
  exportInputs?: Exportinputs;
  exports: Exports;
  facts: WorkingFactsV2;
  importCoverage: Importcoverage;
  importIssues: Importissues;
  operations: Operations;
  projectId: Projectid1;
  renders: Renders;
  revision: Revision39;
  schemaVersion: Schemaversion4;
  sources: Sources;
  templateOperations: Templateoperations;
  templatePackage: TemplatePackage;
}
export interface LocalImageAsset {
  height: Height;
  id: Id;
  mimeType: Mimetype;
  path: Path;
  sha256: Sha256;
  size: Size;
  width: Width;
}
export interface RichDocumentV2 {
  regions: Regions;
  revision: Revision14;
  schemaVersion: Schemaversion;
}
export interface TemplateRegion {
  blocks: Blocks;
  id: Id19;
  revision: Revision13;
  role: Role;
}
export interface TemplateParagraphBlock {
  children: Children;
  content: Content13;
  id: Id18;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision12;
  type: Type16;
}
export interface TemplateHeadingBlock {
  children: Children1;
  content: Content12;
  id: Id17;
  presentation: AuthoredPresentation | null;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision11;
  type: Type15;
}
export interface TemplateBulletBlock {
  children: Children2;
  content: Content11;
  id: Id16;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision10;
  type: Type14;
}
export interface TemplateNumberedBlock {
  children: Children3;
  content: Content10;
  id: Id15;
  presentation: AuthoredPresentation | null;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision9;
  type: Type13;
}
export interface TemplateChecklistBlock {
  children: Children4;
  content: Content9;
  id: Id14;
  presentation: AuthoredPresentation | null;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision8;
  type: Type12;
}
export interface TemplateToggleBlock {
  children: Children5;
  content: Content8;
  id: Id13;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision7;
  type: Type11;
}
export interface TemplateQuoteBlock {
  children: Children6;
  content: Content7;
  id: Id12;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision6;
  type: Type10;
}
export interface TemplateCodeBlock {
  children: Children7;
  content: Content6;
  id: Id11;
  presentation: AuthoredPresentation | null;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision5;
  type: Type9;
}
export interface TemplateDividerBlock {
  children: Children8;
  content: Content5;
  id: Id10;
  presentation: AuthoredPresentation | null;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision4;
  type: Type8;
}
export interface TemplateTableBlock {
  children: Children9;
  content: TemplateTableContent;
  id: Id9;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision3;
  type: Type7;
}
export interface TemplateImageBlock {
  children: Children10;
  content: Content3;
  id: Id6;
  presentation: AuthoredPresentation | null;
  props: TemplateImageProps;
  provenance: Provenance1;
  revision: Revision1;
  type: Type6;
}
export interface TemplateSectionBlock {
  children: Children11;
  content: Content;
  id: Id1;
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
  size: Size1;
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
  id: Id3;
  kind: Kind1;
  recordId: Recordid4;
}
export interface WorkingOwnership {
  id: Id4;
  kind: Kind2;
  recordId: Recordid5;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id5;
  kind: Kind3;
}
export interface TemplateImageProps {
  alignment: Alignment2;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height1;
  width: Width1;
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
export interface ImmutableFactEvidence {
  evidence: Evidence2;
  id: Id20;
  rawText: Rawtext;
}
export interface TemplateExportCapture {
  attemptId: Attemptid;
  request: CapturedTemplateRenderInputV1;
  snapshot: TemplateSnapshotIdentity;
}
export interface CapturedTemplateRenderInputV1 {
  assets: Assets1;
  document: RichDocumentV2;
  documentHash: Documenthash;
  facts: WorkingFactsV2;
  factsHash: Factshash;
  packageHash: Packagehash1;
  presentationHash: Presentationhash;
  renderInputVersion: Renderinputversion;
  renderer: TemplateRendererIdentity;
  schemaVersion: Schemaversion3;
}
export interface TemplateRenderAsset {
  id: Id21;
  path: Path1;
  sha256: Sha2561;
  size: Size2;
}
export interface WorkingFactsV2 {
  builtinIdentities?: Builtinidentities;
  builtinManualScopes?: Builtinmanualscopes;
  extensions: Extensions;
  extraction?: ExtractionReport | null;
  manualScopes: Manualscopes;
  mode?: Mode;
  observations: Observations;
  records: Records;
  relations: Relations1;
  revision: Revision36;
  schemaVersion: Schemaversion2;
  tombstones: Tombstones;
}
export interface BuiltinItemIdentity {
  canonicalFields?: Canonicalfields;
  cellIds: Cellids;
  itemHandle: Itemhandle1;
  periodIds?: Periodids;
  recordId: Recordid6;
  semanticSchemaHash: Semanticschemahash;
  semanticType: Semantictype;
}
export interface Canonicalfields {
  [k: string]: CanonicalFieldBinding;
}
export interface CanonicalFieldBinding {
  cellId: Cellid2;
  fieldKey: Fieldkey3;
  periodId: Periodid;
}
export interface Cellids {
  [k: string]: string;
}
export interface Periodids {
  [k: string]: string;
}
export interface Builtinmanualscopes {
  [k: string]: string;
}
export interface ExtensionRecord {
  active: Active;
  cells: Cells1;
  copyOfRecordId?: Copyofrecordid;
  id: Id23;
  itemHandle: Itemhandle2;
  observationIds: Observationids1;
  relations: Relations;
  retiredCellIds?: Retiredcellids;
  revision: Revision17;
  schemaVersion: Schemaversion1;
  semanticSchemaHash: Semanticschemahash1;
  semanticType: Semantictype1;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence3;
  fieldKey: Fieldkey4;
  id: Id22;
  manualScopeId: Manualscopeid;
  observationIds: Observationids;
  origin: Origin;
  rawInput: Rawinput;
  revision: Revision15;
  state: State;
  typedValue: JsonValue;
  userCorrected: Usercorrected;
}
export interface Relation {
  active: Active1;
  id: Id24;
  kind: Kind4;
  revision: Revision16;
  subjectId: Subjectid;
  targetId: Targetid;
}
export interface Retiredcellids {
  [k: string]: string;
}
export interface ExtractionReport {
  counts: Counts;
  factCount: Factcount;
  recoveredRows: Recoveredrows;
  requestBytes: Requestbytes;
  status: Status;
  unresolved: Unresolved;
}
export interface Counts {
  [k: string]: number;
}
export interface ExtractionIssue {
  code: Code1;
  page?: Page;
  section: Section;
  sourceId: Sourceid2;
  unitId: Unitid2;
}
export interface ManualEditScope {
  actionId: Actionid;
  blockIds: Blockids;
  cellIds: Cellids1;
  id: Id25;
  rawInput: Rawinput1;
}
export interface Observation {
  admission: Admission;
  evidence: Evidence4;
  fieldKey: Fieldkey5;
  id: Id26;
  itemHandle: Itemhandle3;
  ownerRelations: Ownerrelations;
  proposalHash: Proposalhash;
  rawInput: Rawinput2;
  receiptIds: Receiptids;
  typedValue: JsonValue;
}
export interface CandidateRecord {
  evidence: Evidence5;
  id: Id27;
  kind: Kind5;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin1;
  revision: Revision19;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected2;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext1;
  revision: Revision18;
  status: Status1;
  userCorrected?: Usercorrected1;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence6;
  id: Id28;
  kind: Kind6;
  label: Label;
  origin: Origin2;
  revision: Revision20;
  userCorrected?: Usercorrected3;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence7;
  id: Id29;
  kind: Kind7;
  origin: Origin3;
  periods: Periods;
  revision: Revision24;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id30;
  present: WorkingFieldBool;
  revision: Revision23;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext2;
  revision: Revision21;
  status: Status2;
  userCorrected?: Usercorrected4;
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
  rawText: Rawtext3;
  revision: Revision22;
  status: Status3;
  userCorrected?: Usercorrected5;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence9;
  id: Id31;
  jobId: Jobid;
  kind: Kind8;
  name: WorkingFieldStr;
  origin: Origin4;
  periods: Periods1;
  revision: Revision25;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected7;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence10;
  experience?: WorkingFieldStr;
  id: Id32;
  jobId: Jobid1;
  kind: Kind9;
  origin: Origin5;
  revision: Revision26;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected8;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence11;
  id: Id33;
  institution: WorkingFieldStr;
  kind: Kind10;
  origin: Origin6;
  qualification: WorkingFieldStr;
  revision: Revision27;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected9;
}
export interface LanguageRecord {
  evidence: Evidence12;
  id: Id34;
  kind: Kind11;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin7;
  revision: Revision28;
  userCorrected?: Usercorrected10;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence13;
  id: Id35;
  issuer: WorkingFieldStr;
  kind: Kind12;
  name: WorkingFieldStr;
  origin: Origin8;
  revision: Revision29;
  userCorrected?: Usercorrected11;
}
export interface ClaimRecord {
  evidence: Evidence14;
  id: Id36;
  jobId: Jobid2;
  kind: Kind13;
  origin: Origin9;
  revision: Revision30;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected12;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence15;
  id: Id37;
  jobId: Jobid3;
  kind: Kind14;
  origin: Origin10;
  revision: Revision31;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected13;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext4;
  revision: Revision32;
  status: Status4;
  userCorrected?: Usercorrected14;
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
  evidence: Evidence16;
  id: Id38;
  jobId: Jobid4;
  kind: Kind15;
  origin: Origin11;
  revision: Revision33;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected15;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext5;
  revision: Revision34;
  status: Status5;
  userCorrected?: Usercorrected16;
  value: LeadershipValue | null;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface UnresolvedRecord {
  category: Category;
  evidence: Evidence17;
  id: Id39;
  kind: Kind16;
  origin: Origin12;
  revision: Revision35;
  status: Status6;
  userCorrected?: Usercorrected17;
}
export interface RecordTombstone {
  actionId: Actionid1;
  orderIndex: Orderindex;
  recordId: Recordid7;
  revision: Revision37;
}
export interface TemplateRendererIdentity {
  id: Id40;
  sha256: Sha2562;
  version: Version;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash1;
  documentRevision: Documentrevision;
  factsHash: Factshash1;
  packageHash: Packagehash2;
  presentationHash: Presentationhash1;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
export interface ExportAttempt {
  artifactHash: Artifacthash;
  assetsHash: Assetshash;
  documentHash: Documenthash2;
  errorCode: Errorcode;
  factsHash: Factshash2;
  id: Id41;
  packageHash: Packagehash3;
  presentationHash: Presentationhash2;
  publicationIntentId: Publicationintentid;
  rendererHash: Rendererhash;
  state: State1;
}
export interface SpanCoverage {
  blockIds: Blockids1;
  disposition: Disposition;
  itemHandle: Itemhandle4;
  reason: Reason;
  span: SourceSpan;
}
export interface ImportIssue {
  blockIds: Blockids2;
  category: Category1;
  code: Code2;
  id: Id42;
  importedFingerprint: Importedfingerprint;
  lifecycleId: Lifecycleid;
  message: Message;
  retiredByAction: Retiredbyaction;
  reviewInputHash: Reviewinputhash;
  ruleId: Ruleid;
  state: State2;
  targetIds: Targetids;
  taskId: Taskid;
}
export interface RichOperation {
  actionId: Actionid2;
  dependencies: Dependencies;
  errorCode: Errorcode1;
  id: Id44;
  kind: Kind18;
  status: Status7;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id43;
  kind: Kind17;
  revision: Revision38;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision1;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id45;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id46;
  mimeType: Mimetype1;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision41;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id47;
  origin: Origin13;
  revision: Revision40;
  text: Text4;
  unitId: Unitid3;
}
export interface SourceUnit {
  disposition: Disposition1;
  id: Id48;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision42;
  structure?: SourceStructure | null;
  text: Text5;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind19;
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
  style?: Style;
}
export interface SourceWarning {
  code: Code3;
  page?: Page1;
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
  id: Id52;
  inferenceClosed?: Inferenceclosed;
  issues?: Issues;
  lastObservedAt: Lastobservedat;
  projectId: Projectid2;
  proposals: Proposals;
  publication: PublicationOutcome;
  receipts: Receipts;
  relationAllocations?: Relationallocations;
  reviewInputs: Reviewinputs;
  schemaVersion: Schemaversion7;
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
  itemHandle: Itemhandle5;
  key: Key;
  operationId: Operationid;
  periodIds?: Periodids1;
  recordId: Recordid8;
  semanticType: Semantictype2;
  taskId: Taskid1;
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
  errorCode?: Errorcode2;
  id: Id49;
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
  state: State4;
  taskId: Taskid2;
  usage: ObservedUsage;
}
export interface CleanupOutcome {
  evidenceHash: Evidencehash;
  state: State3;
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
  id: Id50;
  kind: Kind20;
  state: State5;
}
export interface ImportCapture {
  allowTextRewrite: Allowtextrewrite;
  authorityHash: Authorityhash1;
  dependencyHash: Dependencyhash1;
  factRevisions: Factrevisions;
  fallback: ModelCapture | null;
  formattingAsOf: PartialDate;
  packageHash: Packagehash4;
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
  itemHandle: Itemhandle6;
  periodIds?: Periodids2;
  recordId: Recordid9;
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
  attemptId: Attemptid1;
  evidenceHash: Evidencehash1;
  neverDispatched: Neverdispatched;
  ownerHash: Ownerhash;
  verifiedAt: Verifiedat;
  witness: Witness1;
}
export interface FinalizationCandidate {
  authorityHash: Authorityhash2;
  authorizationId: Authorizationid1;
  candidateHash: Candidatehash;
  coverageHash: Coveragehash;
  dependencyHash: Dependencyhash2;
  documentHash: Documenthash3;
  expiresAt: Expiresat1;
  factsHash: Factshash3;
  id: Id51;
  issuesHash: Issueshash;
  operationId: Operationid2;
  packageHash: Packagehash5;
  sourceHash: Sourcehash;
  startedAt: Startedat;
}
export interface ProposalRecord {
  admittedCellIds?: Admittedcellids;
  admittedRecordRevisions?: Admittedrecordrevisions;
  admittedRelationIds?: Admittedrelationids;
  admittedRelationRevisions?: Admittedrelationrevisions;
  appliedReceiptId?: Appliedreceiptid;
  attemptId: Attemptid2;
  errors: Errors;
  id: Id53;
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
  attemptId: Attemptid3;
  children: Children12;
  kind: Kind21;
  parents: Parents;
}
export interface ProposalReply {
  discoveries: Discoveries;
  fields: Fields;
  lineage: Lineage2;
  payload: JsonValue;
  relations?: Relations2;
  schemaVersion: Schemaversion5;
}
export interface Discovery {
  key: Key1;
  pointer: Pointer;
  semanticType: Semantictype4;
}
export interface ProposalField {
  effectiveCellIds: Effectivecellids;
  evidence: Evidence18;
  fieldKey: Fieldkey6;
  item: Item;
  pointer: Pointer1;
}
export interface DiscoverySelector {
  key: Key2;
  kind: Kind22;
}
export interface HandleSelector {
  itemHandle: Itemhandle7;
  kind: Kind23;
}
export interface ProposalLineage {
  children: Children13;
  kind: Kind24;
  parents: Parents1;
}
export interface ProposalRelation {
  evidence: Evidence19;
  kind: Kind25;
  relation: Relation1;
  subject: Subject;
  target: Target;
}
export interface RelationDiscoverySelector {
  key: Key3;
  kind: Kind26;
}
export interface ExistingRelationSelector {
  kind: Kind27;
  relationId: Relationid;
}
export interface FieldSidecar {
  effectiveCellIds: Effectivecellids1;
  evidence: Evidence20;
  fieldKey: Fieldkey7;
  itemHandle: Itemhandle8;
  pointer: Pointer2;
}
export interface PublicationOutcome {
  errorCode: Errorcode3;
  intentId: Intentid;
  state: State7;
  workspaceHash: Workspacehash;
}
export interface ReviewReceipt {
  attemptId: Attemptid4;
  completedAt: Completedat;
  expectedChecks: Expectedchecks;
  id: Id54;
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
  disposition: Disposition2;
  evidence: Evidence21;
  reason: Reason1;
  ruleId: Ruleid2;
  targetId: Targetid2;
}
export interface RelationAllocation {
  discoveryAttemptId: Discoveryattemptid1;
  key: Key4;
  kind: Kind28;
  operationId: Operationid3;
  relationId: Relationid1;
  subjectId: Subjectid1;
  targetId: Targetid3;
  taskId: Taskid3;
}
export interface ReviewInputRecord {
  attemptId: Attemptid5;
  id: Id55;
  inputHash: Inputhash2;
  value: ReviewInput;
}
export interface ReviewInput {
  allowTextRewrite: Allowtextrewrite1;
  effectiveCells: Effectivecells;
  evidence?: Evidence22;
  handleMap: Handlemap;
  occurrenceContext: JsonValue;
  occurrenceIndependent: Occurrenceindependent;
  packageHash: Packagehash6;
  policy: ModelCapture;
  proposalHash: Proposalhash2;
  protocol: Protocol;
  relations: Relations3;
  rules: Rules;
  schemaVersion: Schemaversion6;
  semanticContext: Semanticcontext;
  sourceSpans: Sourcespans;
  sourceTexts: Sourcetexts;
  targets: Targets;
}
export interface EvidenceOption {
  ref: Ref;
  span: SourceSpan;
  text: Text6;
}
export interface Check {
  id: Id56;
  kind: Kind29;
  parameters: CheckParameters;
  version: Version1;
}
export interface CheckParameters {
  fields: Fields1;
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
  id: Id57;
  inputHash: Inputhash3;
  taskId: Taskid4;
  value: Value2;
}
export interface Value2 {
  [k: string]: JsonValue;
}
export interface TaskResultRecord {
  disposition: Disposition3;
  id: Id58;
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
  blockId: Blockid;
  dependencies: Dependencies1;
  expectedChecks: Expectedchecks1;
  id: Id59;
  inputHash: Inputhash5;
  issueIds: Issueids1;
  kind: Kind30;
  operationId: Operationid4;
  proposalHash: Proposalhash3;
  receiptIds: Receiptids1;
  state: State9;
}
export interface TemplatePackage {
  assets: Assets2;
  blocks: Blocks1;
  compilerVersion: Compilerversion;
  configHash: Confighash;
  definition: TemplateDefinition;
  id: Id73;
  manifest: CompilationManifest;
  operationVersion: Operationversion;
  originalBase64: Originalbase64;
  originalFormat: Originalformat;
  originalHash: Originalhash;
  packageHash: Packagehash7;
  projectionVersion: Projectionversion;
  recipe: CompiledRecipe;
  revision: Revision44;
  schemaVersion: Schemaversion9;
}
export interface CapturedAsset {
  bytesBase64: Bytesbase64;
  id: Id60;
  mimeType: Mimetype2;
  path: Path2;
  role: Role1;
  sha256: Sha2563;
  size: Size3;
}
export interface CompiledBlock {
  dependencyOrder: Dependencyorder;
  fullSchema: Fullschema;
  id: Id61;
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
  assets: Assets3;
  blocks: Blocks2;
  content_definitions: ContentDefinitions;
  fact_types: FactTypes;
  layout: Layout;
  model: ModelInstructions;
  operations: Operations1;
  provenance: Provenance12;
  schema_version: SchemaVersion1;
  source: SourcePolicy;
  style: Style2;
  template: TemplateIdentity;
}
export interface AssetDeclaration {
  embedding: Embedding;
  id: Id62;
  mime_type: MimeType;
  path: Path3;
  role: Role2;
}
export interface Block {
  bindings: Bindings;
  checks: Checks;
  content_schema: ContentSchema;
  depends_on: DependsOn;
  extract: Extract;
  id: Id63;
  mode: Mode1;
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
  pointer: Pointer3;
  relation: BindingRelation | null;
  semantic_type: SemanticType;
}
export interface BindingRelation {
  kind: Kind31;
  subject_pointer: SubjectPointer;
}
export interface ContentSchema {
  [k: string]: JsonValue;
}
export interface Placement {
  order: Order1;
  region: Region;
}
export interface Rewrite {
  fields: Fields2;
  instructions: Instructions1;
}
export interface InputRef {
  id: Id64;
  kind: Kind32;
}
export interface View {
  fallback_style?: FallbackStyle;
  heading: Heading;
  inset: Inset;
  item_gap: ItemGap;
  mode: Mode2;
  nodes: Nodes;
  title: Title;
}
export interface ViewNode {
  background?: Background;
  detail_style?: DetailStyle;
  experience_field?: ExperienceField;
  field?: Field1;
  fields?: Fields3;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label1;
  name_field?: NameField;
  prefix?: Prefix;
  separator?: Separator;
  style: Style1;
  type: Type17;
  url_field?: UrlField;
}
export interface Label1 {
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
  id: Id65;
  relations: Relations4;
  schema: Schema;
  schema_version: SchemaVersion;
}
export interface BuiltinFields {
  [k: string]: BuiltinFieldBinding;
}
export interface BuiltinFieldBinding {
  field: Field2;
  period: Period1;
}
export interface RelationDeclaration {
  kind: Kind33;
  target_types: TargetTypes;
}
export interface Schema {
  [k: string]: JsonValue;
}
export interface Layout {
  pagination: Pagination;
  reading_order: ReadingOrder;
  regions: Regions1;
}
export interface Pagination {
  allow_more_pages: AllowMorePages;
  allow_project_split: AllowProjectSplit;
  keep_heading_with_next: KeepHeadingWithNext;
  truncate_content: TruncateContent;
}
export interface Region1 {
  flow: Flow;
  id: Id66;
  width: Width2;
  x: X;
}
export interface ModelInstructions {
  extract: Extract1;
  permission: Permission;
  rewrite: Rewrite1;
}
export interface PartitionOperation {
  depends_on: DependsOn1;
  id: Id67;
  inputs: Inputs;
  kind: Kind34;
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
  id: Id68;
  inputs: Inputs1;
  kind: Kind35;
  parameters: RoleParameters;
  version: Version3;
}
export interface RoleParameters {
  classification?: FactField | null;
  matched: Matched;
  otherwise: Otherwise;
  role_families: RoleFamilies;
}
export interface FactField {
  field: Field3;
  semantic_type: SemanticType1;
}
export interface SkillsOperation {
  depends_on: DependsOn3;
  id: Id69;
  inputs: Inputs2;
  kind: Kind36;
  parameters: SkillsParameters;
  version: Version4;
}
export interface SkillsParameters {
  groups: Groups;
  uncertain_group: UncertainGroup;
}
export interface PeriodOperation {
  depends_on: DependsOn4;
  id: Id70;
  inputs: Inputs3;
  kind: Kind37;
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
  id: Id71;
  inputs: Inputs4;
  kind: Kind38;
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
export interface Style2 {
  bullets: Bullets;
  colors: Colors;
  focus: Focus;
  fonts: Fonts;
  footer: Footer;
  header: Header;
  page: Page2;
  section_band: Band;
  text: Text8;
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
  style: Style3;
  text: Text7;
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
  width: Width3;
  x1: X1;
  x2: X2;
  y: Y;
}
export interface Logo {
  asset: Asset;
  fit: Fit;
  height: Height2;
  top: Top;
  width: Width4;
  x: X3;
}
export interface Page2 {
  body_bottom: BodyBottom;
  continuation_body_top: ContinuationBodyTop;
  first_body_top: FirstBodyTop;
  height: Height3;
  width: Width5;
}
export interface Band {
  background: Background1;
  heading_style: HeadingStyle;
  height: Height4;
  text_inset: TextInset;
}
export interface Text8 {
  [k: string]: TextStyle;
}
export interface TextStyle {
  color: Color2;
  font: Font1;
  line_height: LineHeight;
  size: Size4;
}
export interface TemplateIdentity {
  default_locale: DefaultLocale;
  id: Id72;
  name: Name;
  revision: Revision43;
}
export interface CompilationManifest {
  capabilities: Capabilities;
  profileId: Profileid;
  profileVersion: Profileversion;
  serverOnly: Serveronly1;
  supportedFormats: Supportedformats;
}
export interface Serveronly1 {
  [k: string]: string[];
}
export interface CompiledRecipe {
  capabilities: Capabilities1;
  layout: Layout;
  placements: Placements;
  renderInputVersion: Renderinputversion1;
  schemaVersion: Schemaversion8;
  style: Style2;
  views: Views;
}
export interface Placements {
  [k: string]: Placement;
}
export interface Views {
  [k: string]: View;
}
