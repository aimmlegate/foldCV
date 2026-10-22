export type Id = string;
export type Path = string;
export type Sha256 = string;
export type Size = number;
export type Assets = TemplateRenderAsset[];
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
export type Evidence2 = SourceSpan[];
export type Fieldkey4 = string;
export type Id20 = string;
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
export type Id21 = string;
export type Itemhandle2 = string;
export type Observationids1 = string[];
export type Active1 = boolean;
export type Id22 = string;
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
export type Id23 = string;
export type Rawinput1 = string;
export type Manualscopes = ManualEditScope[];
export type Mode = "structured" | "digest" | "imported";
export type Admission = "provisional" | "accepted" | "rejected" | "uncertain";
export type Evidence3 = SourceSpan[];
export type Fieldkey5 = string;
export type Id24 = string;
export type Itemhandle3 = string;
export type Ownerrelations = Relation[];
export type Proposalhash = string;
export type Rawinput2 = string;
export type Receiptids = string[];
export type Observations = Observation[];
export type Evidence4 = EvidenceSpan[];
export type Id25 = string;
export type Kind5 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision18 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected1 = boolean;
export type Value = string | null;
export type Origin1 = "source" | "user";
export type Revision19 = number;
export type Usercorrected2 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence5 = EvidenceSpan[];
export type Id26 = string;
export type Kind6 = "detail";
export type Label = string;
export type Origin2 = "source" | "user";
export type Revision20 = number;
export type Usercorrected3 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id27 = string;
export type Kind7 = "employment";
export type Origin3 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision21 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence7 = EvidenceSpan[];
export type Id28 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision22 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected5 = boolean;
export type Value1 = boolean | null;
export type Revision23 = number;
export type Periods = WorkingPeriod[];
export type Revision24 = number;
export type Usercorrected6 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id29 = string;
export type Jobid = string;
export type Kind8 = "subproject";
export type Origin4 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision25 = number;
export type Usercorrected7 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id30 = string;
export type Jobid1 = string | null;
export type Kind9 = "technology";
export type Origin5 = "source" | "user";
export type Revision26 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected8 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id31 = string;
export type Kind10 = "education";
export type Origin6 = "source" | "user";
export type Revision27 = number;
export type Usercorrected9 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id32 = string;
export type Kind11 = "language";
export type Origin7 = "source" | "user";
export type Revision28 = number;
export type Usercorrected10 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id33 = string;
export type Kind12 = "certification";
export type Origin8 = "source" | "user";
export type Revision29 = number;
export type Usercorrected11 = boolean;
export type Evidence13 = EvidenceSpan[];
export type Id34 = string;
export type Jobid2 = string | null;
export type Kind13 = "claim";
export type Origin9 = "source" | "user";
export type Revision30 = number;
export type Subprojectid1 = string | null;
export type Usercorrected12 = boolean;
export type Evidence14 = EvidenceSpan[];
export type Id35 = string;
export type Jobid3 = string | null;
export type Kind14 = "metric";
export type Origin10 = "source" | "user";
export type Revision31 = number;
export type Subprojectid2 = string | null;
export type Usercorrected13 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
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
export type Evidence15 = EvidenceSpan[];
export type Id36 = string;
export type Jobid4 = string | null;
export type Kind15 = "leadership";
export type Origin11 = "source" | "user";
export type Revision33 = number;
export type Subprojectid3 = string | null;
export type Usercorrected15 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision34 = number;
export type Status5 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence16 = EvidenceSpan[];
export type Id37 = string;
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
export type Bytesbase64 = string;
export type Id38 = string;
export type Mimetype = string;
export type Path1 = string;
export type Role1 = "font" | "logo" | "icon" | "catalog";
export type Sha2561 = string;
export type Size2 = number;
export type Assets1 = CapturedAsset[];
export type Dependencyorder = number;
export type Id39 = string;
export type Serveronly = string[];
export type Blocks1 = CompiledBlock[];
export type Compilerversion = string;
export type Confighash = string;
export type Embedding = "allowed" | "not_applicable";
export type Id40 = string;
export type MimeType = string;
export type Path2 = string;
export type Role2 = "font" | "logo" | "icon" | "catalog";
export type Assets2 = AssetDeclaration[];
export type Field = string;
export type ItemPointer = string | null;
export type Pointer = string;
export type Kind17 = "owned_by" | "extension_of" | "related_to";
export type SubjectPointer = string;
export type SemanticType = string;
export type Bindings = Binding[];
export type Id41 = string;
export type Kind18 =
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
export type DependsOn = string[];
export type Extract = string[];
export type Id42 = string;
export type Mode1 = "model" | "derived" | "source_copy";
export type Operation = string | null;
export type Order = number;
export type Region = "header" | "sidebar" | "main";
export type Fields1 = string[];
export type Instructions1 = string[];
export type Id43 = string;
export type Kind19 = "source" | "fact_type" | "block" | "operation";
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
export type Fields2 = string[];
export type HeaderSlot = ("name" | "profession") | null;
export type ItemField = string | null;
export type NameField = string | null;
export type Separator = string;
export type Style = string;
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
export type Id44 = string;
export type Kind20 = "owned_by" | "extension_of" | "related_to";
export type TargetTypes = string[];
export type Relations2 = RelationDeclaration[];
export type SchemaVersion = string;
export type FactTypes = FactType[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id45 = "header" | "sidebar" | "main";
export type Width1 = number;
export type X = number;
export type Regions1 = Region1[];
export type Extract1 = string[];
export type Permission = "allowTextRewrite";
export type Rewrite1 = string[];
export type DependsOn1 = string[];
export type Id46 = string;
export type Inputs = InputRef[];
export type Kind21 = "partition_employment";
export type Compact = string;
export type Detailed = string;
export type Years = number;
export type Version1 = 1;
export type DependsOn2 = string[];
export type Id47 = string;
export type Inputs1 = InputRef[];
export type Kind22 = "select_role_branch";
export type Matched = string;
export type Otherwise = string;
export type RoleFamilies = string[];
export type Version2 = 1;
export type DependsOn3 = string[];
export type Id48 = string;
export type Inputs2 = InputRef[];
export type Kind23 = "assign_skills";
export type Groups = string[];
export type UncertainGroup = string;
export type Version3 = 1;
export type DependsOn4 = string[];
export type Id49 = string;
export type Inputs3 = InputRef[];
export type Kind24 = "format_period";
export type Separator1 = string;
export type Version4 = 1;
export type DependsOn5 = string[];
export type Id50 = string;
export type Inputs4 = InputRef[];
export type Kind25 = "preserve_stated_text";
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
export type Text4 = string;
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
export type Background1 = string;
export type HeadingStyle = string;
export type Height3 = number;
export type TextInset = number;
export type Color2 = string;
export type Font1 = string;
export type LineHeight = number;
export type Size3 = number;
export type DefaultLocale = string;
export type Id51 = string;
export type Name = string;
export type Revision38 = string;
export type Id52 = string;
export type Capabilities = string[];
export type Profileid = string;
export type Profileversion = string;
export type Supportedformats = string[];
export type Operationversion = string;
export type Originalbase64 = string;
export type Originalformat = "yaml" | "json";
export type Originalhash = string;
export type Packagehash1 = string;
export type Projectionversion = string;
export type Capabilities1 = string[];
export type Renderinputversion = 1;
export type Schemaversion3 = 1;
export type Revision39 = string;
export type Schemaversion4 = 1;
export type Packagehash2 = string;
export type Presentationhash = string;
export type Renderinputversion1 = 1;
export type Id53 = string;
export type Sha2562 = string;
export type Version6 = string;
export type Schemaversion5 = 1;

export interface TemplateRenderRequestV1 {
  assets: Assets;
  document: RichDocumentV2;
  documentHash: Documenthash;
  facts: WorkingFactsV2;
  factsHash: Factshash;
  package: TemplatePackage;
  packageHash: Packagehash2;
  presentationHash: Presentationhash;
  renderInputVersion: Renderinputversion1;
  renderer: TemplateRendererIdentity;
  schemaVersion: Schemaversion5;
}
export interface TemplateRenderAsset {
  id: Id;
  path: Path;
  sha256: Sha256;
  size: Size;
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
  id: Id21;
  itemHandle: Itemhandle2;
  observationIds: Observationids1;
  relations: Relations;
  revision: Revision17;
  schemaVersion: Schemaversion1;
  semanticSchemaHash: Semanticschemahash1;
  semanticType: Semantictype1;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence2;
  fieldKey: Fieldkey4;
  id: Id20;
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
  id: Id22;
  kind: Kind4;
  revision: Revision16;
  subjectId: Subjectid;
  targetId: Targetid;
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
  id: Id23;
  rawInput: Rawinput1;
}
export interface Observation {
  admission: Admission;
  evidence: Evidence3;
  fieldKey: Fieldkey5;
  id: Id24;
  itemHandle: Itemhandle3;
  ownerRelations: Ownerrelations;
  proposalHash: Proposalhash;
  rawInput: Rawinput2;
  receiptIds: Receiptids;
  typedValue: JsonValue;
}
export interface CandidateRecord {
  evidence: Evidence4;
  id: Id25;
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
  rawText: Rawtext;
  revision: Revision18;
  status: Status1;
  userCorrected?: Usercorrected1;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence5;
  id: Id26;
  kind: Kind6;
  label: Label;
  origin: Origin2;
  revision: Revision20;
  userCorrected?: Usercorrected3;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence6;
  id: Id27;
  kind: Kind7;
  origin: Origin3;
  periods: Periods;
  revision: Revision24;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence7;
  id: Id28;
  present: WorkingFieldBool;
  revision: Revision23;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
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
  rawText: Rawtext2;
  revision: Revision22;
  status: Status3;
  userCorrected?: Usercorrected5;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence8;
  id: Id29;
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
  evidence: Evidence9;
  experience?: WorkingFieldStr;
  id: Id30;
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
  evidence: Evidence10;
  id: Id31;
  institution: WorkingFieldStr;
  kind: Kind10;
  origin: Origin6;
  qualification: WorkingFieldStr;
  revision: Revision27;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected9;
}
export interface LanguageRecord {
  evidence: Evidence11;
  id: Id32;
  kind: Kind11;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin7;
  revision: Revision28;
  userCorrected?: Usercorrected10;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence12;
  id: Id33;
  issuer: WorkingFieldStr;
  kind: Kind12;
  name: WorkingFieldStr;
  origin: Origin8;
  revision: Revision29;
  userCorrected?: Usercorrected11;
}
export interface ClaimRecord {
  evidence: Evidence13;
  id: Id34;
  jobId: Jobid2;
  kind: Kind13;
  origin: Origin9;
  revision: Revision30;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected12;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence14;
  id: Id35;
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
  rawText: Rawtext3;
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
  evidence: Evidence15;
  id: Id36;
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
  rawText: Rawtext4;
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
  evidence: Evidence16;
  id: Id37;
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
export interface TemplatePackage {
  assets: Assets1;
  blocks: Blocks1;
  compilerVersion: Compilerversion;
  configHash: Confighash;
  definition: TemplateDefinition;
  id: Id52;
  manifest: CompilationManifest;
  operationVersion: Operationversion;
  originalBase64: Originalbase64;
  originalFormat: Originalformat;
  originalHash: Originalhash;
  packageHash: Packagehash1;
  projectionVersion: Projectionversion;
  recipe: CompiledRecipe;
  revision: Revision39;
  schemaVersion: Schemaversion4;
}
export interface CapturedAsset {
  bytesBase64: Bytesbase64;
  id: Id38;
  mimeType: Mimetype;
  path: Path1;
  role: Role1;
  sha256: Sha2561;
  size: Size2;
}
export interface CompiledBlock {
  dependencyOrder: Dependencyorder;
  fullSchema: Fullschema;
  id: Id39;
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
  assets: Assets2;
  blocks: Blocks2;
  content_definitions: ContentDefinitions;
  fact_types: FactTypes;
  layout: Layout;
  model: ModelInstructions;
  operations: Operations;
  provenance: Provenance12;
  schema_version: SchemaVersion1;
  source: SourcePolicy;
  style: Style1;
  template: TemplateIdentity;
}
export interface AssetDeclaration {
  embedding: Embedding;
  id: Id40;
  mime_type: MimeType;
  path: Path2;
  role: Role2;
}
export interface Block {
  bindings: Bindings;
  checks: Checks;
  content_schema: ContentSchema;
  depends_on: DependsOn;
  extract: Extract;
  id: Id42;
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
  pointer: Pointer;
  relation: BindingRelation | null;
  semantic_type: SemanticType;
}
export interface BindingRelation {
  kind: Kind17;
  subject_pointer: SubjectPointer;
}
export interface Check {
  id: Id41;
  kind: Kind18;
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
  id: Id43;
  kind: Kind19;
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
  fields?: Fields2;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label1;
  name_field?: NameField;
  prefix?: Prefix;
  separator?: Separator;
  style: Style;
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
  id: Id44;
  relations: Relations2;
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
  kind: Kind20;
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
  id: Id45;
  width: Width1;
  x: X;
}
export interface ModelInstructions {
  extract: Extract1;
  permission: Permission;
  rewrite: Rewrite1;
}
export interface PartitionOperation {
  depends_on: DependsOn1;
  id: Id46;
  inputs: Inputs;
  kind: Kind21;
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
  id: Id47;
  inputs: Inputs1;
  kind: Kind22;
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
  id: Id48;
  inputs: Inputs2;
  kind: Kind23;
  parameters: SkillsParameters;
  version: Version3;
}
export interface SkillsParameters {
  groups: Groups;
  uncertain_group: UncertainGroup;
}
export interface PeriodOperation {
  depends_on: DependsOn4;
  id: Id49;
  inputs: Inputs3;
  kind: Kind24;
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
  id: Id50;
  inputs: Inputs4;
  kind: Kind25;
  parameters: EmptyParameters;
  version: Version5;
}
export interface EmptyParameters {}
export interface Provenance12 {
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
  page: Page1;
  section_band: Band;
  text: Text5;
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
  text: Text4;
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
export interface Page1 {
  body_bottom: BodyBottom;
  continuation_body_top: ContinuationBodyTop;
  first_body_top: FirstBodyTop;
  height: Height2;
  width: Width4;
}
export interface Band {
  background: Background1;
  heading_style: HeadingStyle;
  height: Height3;
  text_inset: TextInset;
}
export interface Text5 {
  [k: string]: TextStyle;
}
export interface TextStyle {
  color: Color2;
  font: Font1;
  line_height: LineHeight;
  size: Size3;
}
export interface TemplateIdentity {
  default_locale: DefaultLocale;
  id: Id51;
  name: Name;
  revision: Revision38;
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
  renderInputVersion: Renderinputversion;
  schemaVersion: Schemaversion3;
  style: Style1;
  views: Views;
}
export interface Placements {
  [k: string]: Placement;
}
export interface Views {
  [k: string]: View;
}
export interface TemplateRendererIdentity {
  id: Id53;
  sha256: Sha2562;
  version: Version6;
}
