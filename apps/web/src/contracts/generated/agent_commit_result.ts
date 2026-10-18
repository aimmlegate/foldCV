export type Durability = "pending" | "durable" | "failed";
export type Errorcode = string | null;
export type Id = string;
export type Stage = "assess_resume" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Startedat = string | null;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Subtitle = string;
export type Title = string;
export type Experience = string | null;
export type Experiencenote = string | null;
export type Logo = string | null;
export type Role =
  | "body"
  | "support"
  | "header_name"
  | "header_title"
  | "job_heading"
  | "profile_heading"
  | "section_heading"
  | "focus_heading"
  | "focus_entry"
  | "group";
export type Saveerror = string | null;
export type Saveddocumentrevision = number | null;
export type Savedprojectrevision = number | null;
export type Createdat = string;
export type Documentrevision = number;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Clientmutationid = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
export type Mutationreplay = RichMutationReplay[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status1 = "complete" | "partial";
export type Code = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page = number | null;
export type Section = string;
export type Sourceid = string;
export type Unitid = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Mode = "structured" | "digest" | "imported";
export type Sourceid1 = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid1 = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Id1 = string;
export type Kind = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected = boolean;
export type Value = string | null;
export type Origin = "source" | "user";
export type Revision1 = number;
export type Usercorrected1 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence1 = EvidenceSpan[];
export type Id2 = string;
export type Kind1 = "detail";
export type Label = string;
export type Origin1 = "source" | "user";
export type Revision2 = number;
export type Usercorrected2 = boolean;
export type Evidence2 = EvidenceSpan[];
export type Id3 = string;
export type Kind2 = "employment";
export type Origin2 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision3 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected3 = boolean;
export type Evidence3 = EvidenceSpan[];
export type Id4 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision4 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Value1 = boolean | null;
export type Revision5 = number;
export type Periods = WorkingPeriod[];
export type Revision6 = number;
export type Usercorrected5 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id5 = string;
export type Jobid = string;
export type Kind3 = "subproject";
export type Origin3 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision7 = number;
export type Usercorrected6 = boolean;
export type Evidence5 = EvidenceSpan[];
export type Id6 = string;
export type Jobid1 = string | null;
export type Kind4 = "technology";
export type Origin4 = "source" | "user";
export type Revision8 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected7 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id7 = string;
export type Kind5 = "education";
export type Origin5 = "source" | "user";
export type Revision9 = number;
export type Usercorrected8 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id8 = string;
export type Kind6 = "language";
export type Origin6 = "source" | "user";
export type Revision10 = number;
export type Usercorrected9 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id9 = string;
export type Kind7 = "certification";
export type Origin7 = "source" | "user";
export type Revision11 = number;
export type Usercorrected10 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id10 = string;
export type Jobid2 = string | null;
export type Kind8 = "claim";
export type Origin8 = "source" | "user";
export type Revision12 = number;
export type Subprojectid1 = string | null;
export type Usercorrected11 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id11 = string;
export type Jobid3 = string | null;
export type Kind9 = "metric";
export type Origin9 = "source" | "user";
export type Revision13 = number;
export type Subprojectid2 = string | null;
export type Usercorrected12 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision14 = number;
export type Status5 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
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
export type Evidence11 = EvidenceSpan[];
export type Id12 = string;
export type Jobid4 = string | null;
export type Kind10 = "leadership";
export type Origin10 = "source" | "user";
export type Revision15 = number;
export type Subprojectid3 = string | null;
export type Usercorrected14 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision16 = number;
export type Status6 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected15 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence12 = EvidenceSpan[];
export type Id13 = string;
export type Kind11 = "unresolved";
export type Origin11 = "source" | "user";
export type Revision17 = number;
export type Status7 = "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
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
export type Revision18 = number;
export type Actionid = string;
export type Orderindex = number;
export type Recordid = string;
export type Revision19 = number;
export type Tombstones = RecordTombstone[];
export type Category1 =
  ("identity" | "contacts" | "summary" | "experience" | "education" | "skills" | "languages" | "other") | null;
/**
 * @maxItems 1000
 */
export type Duplicateof = string[];
export type Id14 = string;
export type Kind12 = "paragraph" | "heading" | "section" | "bullet_list" | "duplicate";
export type Listitem = boolean;
export type Modelblock = boolean;
export type Region = "header" | "sidebar" | "main";
/**
 * @maxItems 1000
 */
export type Sourcekeys = string[];
export type Title1 = string | null;
/**
 * @maxItems 5000
 */
export type Blocks1 = ImportBlock[];
export type Id15 = string;
export type Record = (ImportEmployment | ImportEducation | ImportTechnology | ImportLanguage) | null;
export type Employer = string;
export type Kind13 = "employment";
export type End = string;
export type Present = boolean;
export type Start = string;
/**
 * @maxItems 40
 */
export type Periods2 = ImportPeriod[];
export type Role1 = string;
export type Display = string;
export type Experience1 = string;
export type Technical1 = boolean | null;
/**
 * @maxItems 100
 */
export type Technologies = (string | ImportSkill)[];
export type Completion = string;
export type Institution = string;
export type Kind14 = "education";
export type Qualification = string;
export type Specialty = string;
export type Display1 = string;
export type Experience2 = string;
export type Kind15 = "technology";
export type Technical2 = boolean | null;
export type Kind16 = "language";
export type Language = string;
export type Level = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys1 = string[];
export type Text1 = string;
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
export type Title2 = string;
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
export type Version = 1;
export type Actionid1 = string | null;
export type Fingerprint = string | null;
export type Id16 = string;
export type Kind17 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision20 = number;
export type Dependencies = DependencyStamp[];
export type Errorcode1 = string | null;
export type Id17 = string;
export type Kind18 =
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
export type Id18 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id19 = string;
export type Origin12 = "user";
export type Revision21 = number;
export type Text2 = string;
export type Unitid2 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision22 = number;
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id20 = string;
export type Column = number | null;
export type Index = number;
export type Kind19 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision23 = number;
export type Blankbefore = number | null;
export type Bold = boolean | null;
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
export type Text3 = string;
export type Units = SourceUnit[];
export type Code1 = string;
export type Page1 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources = Source[];
export type Warnings1 = string[];
export type Height = number;
export type Id21 = string;
export type Mimetype1 = "image/png" | "image/jpeg";
export type Path = string;
export type Sha256 = string;
export type Size = number;
export type Width = number;
export type Assets = LocalImageAsset[];
export type Createdat1 = string;
/**
 * @minItems 3
 * @maxItems 3
 */
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
export type Bold1 = boolean;
export type Code2 = boolean;
export type Italic = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text4 = string;
export type Type = "text";
export type Content1 = StyledText[];
export type Href = string;
export type Type1 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Fieldkey = string;
export type Recordid1 = string;
export type Syncedfactrevision = number;
export type Text5 = string;
export type Type2 = "fact_field";
export type Content = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id22 = string;
export type Alignment = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Presentation = "standard" | "focus";
export type Recordid2 = string | null;
export type Textcolor1 = string;
export type Evidence13 = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id23 = string;
export type Kind20 = "citation";
export type Recordid3 = string;
export type Fieldkey1 = string;
export type Id24 = string;
export type Kind21 = "field_binding";
export type Recordid4 = string;
export type Id25 = string;
export type Kind22 = "working_owner";
export type Recordid5 = string;
/**
 * @minItems 1
 */
export type Evidence14 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id26 = string;
export type Kind23 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision24 = number;
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
export type Id27 = string;
export type Alignment1 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height1 = number;
export type Width1 = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision25 = number;
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
export type Id28 = string;
export type Revision26 = number;
export type Rowspan = number;
export type Cells = TableCell[];
export type Id29 = string;
export type Id30 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision27 = number;
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
export type Id31 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision28 = number;
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
export type Id32 = string;
export type Backgroundcolor4 = string;
export type Language1 = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision29 = number;
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
export type Id33 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision30 = number;
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
export type Id34 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision31 = number;
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
export type Id35 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision32 = number;
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
export type Id36 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start1 = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision33 = number;
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
export type Id37 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision34 = number;
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
export type Id38 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level1 = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision35 = number;
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
export type Id39 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision36 = number;
export type Type14 = "paragraph";
export type Blocks2 = (
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
export type Id40 = string;
export type Revision37 = number;
export type Role2 = "header" | "sidebar" | "main";
export type Revision38 = number;
export type Schemaversion = 1;
export type Evidence15 = EvidenceSpan[];
export type Id41 = string;
export type Rawtext5 = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Blockids = string[];
export type Disposition1 = "placed" | "excluded";
export type Reason = string | null;
export type Sourceid2 = string;
export type Unitid3 = string;
export type Importcoverage = ImportCoverage[];
export type Operations1 = RichOperation[];
export type Projectid = string;
export type Documentrevision1 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id42 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision39 = number;
export type Schemaversion1 = 5;
export type Sources1 = Source[];
export type Path1 = string;
export type Sha2561 = string;
export type Size1 = number;
export type Assets1 = AssetRef[];
export type Contentpolicyversion = string;
export type Id43 = string;
export type Packagesha256 = string;
export type Version1 = string;
export type Projectid1 = string;
export type Projectrevision = number;
export type Markdown = string;
export type Revision40 = number;
export type Sha2562 = string;
export type Schemaversion2 = 6;
export type Actionid2 = string;
export type Blockids1 = string[];
export type Dependencies1 = DependencyStamp[];
export type Errorcode2 = string | null;
export type Factids = string[];
export type Fieldkeys1 = string[];
export type Id44 = string;
export type Instruction = string | null;
export type Kind24 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
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
export type Keepchildren = boolean;
export type Kind25 = "put_block";
export type Parentid = string;
export type Beforerevision1 = number;
export type Blockid = string;
export type Kind26 = "remove_block";
export type Afterid1 = string | null;
export type Beforerevision2 = number;
export type Blockid1 = string;
export type Kind27 = "move_block";
export type Parentid1 = string;
export type Beforerevision3 = number;
export type Blockid2 = string;
export type Cellid = string | null;
export type Content13 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End1 = number;
export type Field = "content" | "caption";
export type Kind28 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start2 = number;
export type Beforerevision4 = number | null;
export type Kind29 = "put_record";
export type Record1 =
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
export type Beforerevision5 = number;
export type Kind30 = "remove_record";
export type Recordid6 = string;
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
export type Blockids2 = [string, ...string[]];
export type Actionid3 = string;
export type Actiontoken = number;
export type Dependencies2 = DependencyStamp[];
export type Sessionid = string;
export type Kind31 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Status9 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Syncrecords = RichSyncRecord[];
export type Title3 = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;
export type Blockids3 = string[];
export type Code3 = string;
export type Count = number;
export type Sourceid3 = string;
export type Sourcerevision1 = number;
export type Unitid4 = string;
export type Unitrevision1 = number;
export type Evidence16 = Evidence17[];
export type Id45 = string;
export type Page2 = number | null;
export type Sourceid4 = string;
export type Locations = WarningLocation[];
export type Recordids = string[];
export type Warnings2 = RichWarning[];
export type Batchid1 = string;
export type Clientmutationid1 = string;
export type Disposition2 =
  | "prepared"
  | "offered"
  | "applying"
  | "saved"
  | "stale"
  | "rejected"
  | "cancelled"
  | "save_failed"
  | "outcome_unknown";
export type Documentrevision2 = number | null;
export type Durable = boolean;
export type Code4 =
  | "AGENT_DISABLED"
  | "AGENT_MODEL_REQUIRED"
  | "AGENT_MODEL_UNAVAILABLE"
  | "AGENT_MODEL_INCOMPATIBLE"
  | "AGENT_SETTINGS_CONFLICT"
  | "AGENT_SETTINGS_CORRUPT"
  | "AGENT_SETTINGS_SAVE_FAILED"
  | "AGENT_CONNECTION_UNAVAILABLE"
  | "AGENT_CONNECTION_CHANGED"
  | "AGENT_AUTH_REQUIRED"
  | "AGENT_QUOTA"
  | "AGENT_BUSY"
  | "AGENT_CANCELLED"
  | "AGENT_INTERRUPTED"
  | "AGENT_DEADLINE"
  | "AGENT_STARTUP_TIMEOUT"
  | "AGENT_PROTOCOL"
  | "AGENT_PROCESS_FAILED"
  | "AGENT_CLEANUP_FAILED"
  | "AGENT_RUNTIME_UNSUPPORTED"
  | "AGENT_MODEL_REROUTED"
  | "AGENT_UNEXPECTED_COMPACTION"
  | "AGENT_TOOL_DENIED"
  | "AGENT_TOOL_LIMIT"
  | "AGENT_OUTPUT_LIMIT"
  | "AGENT_CONTEXT_LIMIT"
  | "AGENT_ARGUMENT_INVALID"
  | "AGENT_WEB_DISABLED"
  | "AGENT_SOURCE_UNAVAILABLE"
  | "AGENT_SOURCE_DENIED"
  | "AGENT_SOURCE_LIMIT"
  | "AGENT_SCOPE_INVALID"
  | "AGENT_STALE_READ"
  | "AGENT_EDIT_INVALID"
  | "AGENT_EDIT_LIMIT"
  | "AGENT_EVIDENCE_INVALID"
  | "AGENT_NO_OWNER"
  | "AGENT_LEASE_EXPIRED"
  | "AGENT_OWNER_MISMATCH"
  | "AGENT_TICKET_INVALID"
  | "AGENT_RECEIPT_TIMEOUT"
  | "AGENT_SAVE_FAILED"
  | "AGENT_OUTCOME_UNKNOWN"
  | "AGENT_IDEMPOTENCY_CONFLICT"
  | "AGENT_NOT_FOUND"
  | "AGENT_CONVERSATION_FULL"
  | "AGENT_PROJECT_FULL"
  | "AGENT_STORE_CORRUPT"
  | "AGENT_STORE_UNAVAILABLE"
  | "AGENT_STORE_SAVE_FAILED"
  | "AGENT_PROJECT_DELETED"
  | "AGENT_CLEANUP_INCOMPLETE"
  | "AGENT_RESYNC_REQUIRED";
export type Factsrevision1 = number | null;
export type Projectrevision1 = number | null;
export type Requestsha2562 = string;
export type Runid1 = string;
export type Toolkey = string;

export interface AgentCommitResult {
  project: RichProjectResponse;
  receipt: AgentEditReceipt;
}
export interface RichProjectResponse {
  durability: Durability;
  generation: RichGenerationState | null;
  identity?: ResumeIdentity | null;
  presentation?: RichPresentation | null;
  saveError: Saveerror;
  savedDocumentRevision: Saveddocumentrevision;
  savedProjectRevision: Savedprojectrevision;
  workspace: WorkspaceV6;
}
export interface RichGenerationState {
  errorCode: Errorcode;
  id: Id;
  stage: Stage;
  startedAt?: Startedat;
  status: Status;
}
export interface ResumeIdentity {
  subtitle: Subtitle;
  title: Title;
}
export interface RichPresentation {
  blocks: Blocks;
}
export interface Blocks {
  [k: string]: BlockPresentation;
}
export interface BlockPresentation {
  experience?: Experience;
  experienceNote?: Experiencenote;
  logo?: Logo;
  role: Role;
}
export interface WorkspaceV6 {
  createdAt: Createdat;
  documentRevision: Documentrevision;
  formattingAsOf: PartialDate;
  mutationReplay: Mutationreplay;
  preDraft: RichPreDraft | null;
  project: ProjectV5 | null;
  projectId: Projectid1;
  projectRevision: Projectrevision;
  rulesUsed: Rules | null;
  schemaVersion: Schemaversion2;
  sourceObservedAt: PartialDate | null;
  syncRecords: Syncrecords;
  title: Title3;
  titleManuallySet: Titlemanuallyset;
  updatedAt: Updatedat;
  warnings: Warnings2;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface RichMutationReplay {
  clientMutationId: Clientmutationid;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface RichPreDraft {
  facts: WorkingFacts;
  importDraft?: ImportDraft | null;
  operations: Operations;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources;
  warnings: Warnings1;
}
export interface WorkingFacts {
  extraction?: ExtractionReport | null;
  mode?: Mode;
  records: Records;
  revision: Revision18;
  tombstones: Tombstones;
}
export interface ExtractionReport {
  counts: Counts;
  factCount: Factcount;
  recoveredRows: Recoveredrows;
  requestBytes: Requestbytes;
  status: Status1;
  unresolved: Unresolved;
}
export interface Counts {
  [k: string]: number;
}
export interface ExtractionIssue {
  code: Code;
  page?: Page;
  section: Section;
  sourceId: Sourceid;
  unitId: Unitid;
}
export interface CandidateRecord {
  evidence: Evidence;
  id: Id1;
  kind: Kind;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin;
  revision: Revision1;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected1;
}
export interface EvidenceSpan {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision;
  text: Text;
  unitId: Unitid1;
  unitRevision: Unitrevision;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision;
  status: Status2;
  userCorrected?: Usercorrected;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence1;
  id: Id2;
  kind: Kind1;
  label: Label;
  origin: Origin1;
  revision: Revision2;
  userCorrected?: Usercorrected2;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence2;
  id: Id3;
  kind: Kind2;
  origin: Origin2;
  periods: Periods;
  revision: Revision6;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected5;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence3;
  id: Id4;
  present: WorkingFieldBool;
  revision: Revision5;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision3;
  status: Status3;
  userCorrected?: Usercorrected3;
  value: PartialDate | null;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision4;
  status: Status4;
  userCorrected?: Usercorrected4;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence4;
  id: Id5;
  jobId: Jobid;
  kind: Kind3;
  name: WorkingFieldStr;
  origin: Origin3;
  periods: Periods1;
  revision: Revision7;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence5;
  experience?: WorkingFieldStr;
  id: Id6;
  jobId: Jobid1;
  kind: Kind4;
  origin: Origin4;
  revision: Revision8;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected7;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence6;
  id: Id7;
  institution: WorkingFieldStr;
  kind: Kind5;
  origin: Origin5;
  qualification: WorkingFieldStr;
  revision: Revision9;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected8;
}
export interface LanguageRecord {
  evidence: Evidence7;
  id: Id8;
  kind: Kind6;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin6;
  revision: Revision10;
  userCorrected?: Usercorrected9;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id9;
  issuer: WorkingFieldStr;
  kind: Kind7;
  name: WorkingFieldStr;
  origin: Origin7;
  revision: Revision11;
  userCorrected?: Usercorrected10;
}
export interface ClaimRecord {
  evidence: Evidence9;
  id: Id10;
  jobId: Jobid2;
  kind: Kind8;
  origin: Origin8;
  revision: Revision12;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected11;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence10;
  id: Id11;
  jobId: Jobid3;
  kind: Kind9;
  origin: Origin9;
  revision: Revision13;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected12;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision14;
  status: Status5;
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
  evidence: Evidence11;
  id: Id12;
  jobId: Jobid4;
  kind: Kind10;
  origin: Origin10;
  revision: Revision15;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected14;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision16;
  status: Status6;
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
  evidence: Evidence12;
  id: Id13;
  kind: Kind11;
  origin: Origin11;
  revision: Revision17;
  status: Status7;
  userCorrected?: Usercorrected16;
}
export interface RecordTombstone {
  actionId: Actionid;
  orderIndex: Orderindex;
  recordId: Recordid;
  revision: Revision19;
}
export interface ImportDraft {
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
  version?: Version;
}
export interface ImportBlock {
  category?: Category1;
  duplicateOf?: Duplicateof;
  id: Id14;
  kind?: Kind12;
  listItem?: Listitem;
  modelBlock?: Modelblock;
  region?: Region;
  sourceKeys?: Sourcekeys;
  title?: Title1;
}
export interface ImportFact {
  id: Id15;
  record?: Record;
  sourceKeys?: Sourcekeys1;
  text?: Text1;
}
export interface ImportEmployment {
  employer?: Employer;
  kind: Kind13;
  periods?: Periods2;
  role?: Role1;
  technologies?: Technologies;
}
export interface ImportPeriod {
  end?: End;
  present?: Present;
  start?: Start;
}
export interface ImportSkill {
  display: Display;
  experience?: Experience1;
  technical?: Technical1;
}
export interface ImportEducation {
  completion?: Completion;
  institution?: Institution;
  kind: Kind14;
  qualification?: Qualification;
  specialty?: Specialty;
}
export interface ImportTechnology {
  display: Display1;
  experience?: Experience2;
  kind: Kind15;
  technical?: Technical2;
}
export interface ImportLanguage {
  kind: Kind16;
  language?: Language;
  level?: Level;
}
export interface ImportProfile {
  location?: Location;
  name?: Name;
  sourceKeys?: Sourcekeys2;
  title?: Title2;
}
export interface ImportReceipt {
  batchId: Batchid;
  requestSha256: Requestsha2561;
  sequence: Sequence;
}
export interface RichOperation {
  actionId: Actionid1;
  dependencies: Dependencies;
  errorCode: Errorcode1;
  id: Id17;
  kind: Kind18;
  status: Status8;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id16;
  kind: Kind17;
  revision: Revision20;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id18;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision22;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id19;
  origin: Origin12;
  revision: Revision21;
  text: Text2;
  unitId: Unitid2;
}
export interface SourceUnit {
  disposition: Disposition;
  id: Id20;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision23;
  structure?: SourceStructure | null;
  text: Text3;
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
  bold?: Bold;
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
  code: Code1;
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
  projectId: Projectid;
  renders: Renders;
  revision: Revision39;
  schemaVersion: Schemaversion1;
  sources: Sources1;
  template: TemplateManifest;
}
export interface LocalImageAsset {
  height: Height;
  id: Id21;
  mimeType: Mimetype1;
  path: Path;
  sha256: Sha256;
  size: Size;
  width: Width;
}
export interface RichDocumentV1 {
  regions: Regions;
  revision: Revision38;
  schemaVersion: Schemaversion;
}
export interface RichRegion {
  blocks: Blocks2;
  id: Id40;
  revision: Revision37;
  role: Role2;
}
export interface ParagraphBlock {
  children: Children;
  content: Content12;
  id: Id39;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision36;
  type: Type14;
}
export interface HeadingBlock {
  children: Children1;
  content: Content11;
  id: Id38;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision35;
  type: Type13;
}
export interface BulletBlock {
  children: Children2;
  content: Content10;
  id: Id37;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision34;
  type: Type12;
}
export interface NumberedBlock {
  children: Children3;
  content: Content9;
  id: Id36;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision33;
  type: Type11;
}
export interface ChecklistBlock {
  children: Children4;
  content: Content8;
  id: Id35;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision32;
  type: Type10;
}
export interface ToggleBlock {
  children: Children5;
  content: Content7;
  id: Id34;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision31;
  type: Type9;
}
export interface QuoteBlock {
  children: Children6;
  content: Content6;
  id: Id33;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision30;
  type: Type8;
}
export interface CodeBlock {
  children: Children7;
  content: Content5;
  id: Id32;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision29;
  type: Type7;
}
export interface DividerBlock {
  children: Children8;
  content: Content4;
  id: Id31;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision28;
  type: Type6;
}
export interface TableBlock {
  children: Children9;
  content: TableContent;
  id: Id30;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision27;
  type: Type5;
}
export interface ImageBlock {
  children: Children10;
  content: Content2;
  id: Id27;
  props: ImageProps;
  provenance: Provenance1;
  revision: Revision25;
  type: Type4;
}
export interface SectionBlock {
  children: Children11;
  content: Content;
  id: Id22;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision24;
  type: Type3;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text4;
  type: Type;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold1;
  code?: Code2;
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
  recordId: Recordid1;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text5;
  type: Type2;
}
export interface SectionProps {
  alignment?: Alignment;
  backgroundColor?: Backgroundcolor1;
  presentation?: Presentation;
  recordId: Recordid2;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence13;
  fieldKeys: Fieldkeys;
  id: Id23;
  kind: Kind20;
  recordId: Recordid3;
}
export interface FieldBinding {
  fieldKey: Fieldkey1;
  id: Id24;
  kind: Kind21;
  recordId: Recordid4;
}
export interface WorkingOwnership {
  id: Id25;
  kind: Kind22;
  recordId: Recordid5;
}
export interface SourceWitness {
  evidence: Evidence14;
  id: Id26;
  kind: Kind23;
}
export interface ImageProps {
  alignment: Alignment1;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height1;
  width: Width1;
}
export interface TableContent {
  columnWidths: Columnwidths;
  headerCols?: Headercols;
  headerRows: Headerrows;
  rows: Rows;
}
export interface TableRow {
  cells: Cells;
  id: Id29;
}
export interface TableCell {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content3;
  id: Id28;
  revision: Revision26;
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
  language: Language1;
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
  start?: Start1;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor7;
  level: Level1;
  textColor?: Textcolor5;
}
export interface ImmutableFactEvidence {
  evidence: Evidence15;
  id: Id41;
  rawText: Rawtext5;
}
export interface ImportCoverage {
  blockIds: Blockids;
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
  id: Id42;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface TemplateManifest {
  assets: Assets1;
  contentPolicyVersion: Contentpolicyversion;
  id: Id43;
  packageSha256: Packagesha256;
  version: Version1;
}
export interface AssetRef {
  path: Path1;
  sha256: Sha2561;
  size: Size1;
}
export interface Rules {
  markdown: Markdown;
  revision: Revision40;
  sha256: Sha2562;
}
export interface RichSyncRecord {
  actionId: Actionid2;
  blockIds: Blockids1;
  dependencies: Dependencies1;
  errorCode: Errorcode2;
  factIds: Factids;
  fieldKeys: Fieldkeys1;
  id: Id44;
  instruction?: Instruction;
  kind?: Kind24;
  proposedSteps?: Proposedsteps;
  ready?: Ready;
  selection?: RichSelection | null;
  status: Status9;
}
export interface PutBlock {
  afterId: Afterid;
  beforeRevision: Beforerevision;
  block: Block;
  keepChildren?: Keepchildren;
  kind: Kind25;
  parentId: Parentid;
}
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid;
  kind: Kind26;
}
export interface MoveBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision2;
  blockId: Blockid1;
  kind: Kind27;
  parentId: Parentid1;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid2;
  cellId: Cellid;
  content: Content13;
  end: End1;
  field: Field;
  kind: Kind28;
  start: Start2;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind29;
  record: Record1;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind30;
  recordId: Recordid6;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids2;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind31;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid3;
  cellId: Cellid1;
  offset: Offset;
}
export interface ActionCapture {
  actionId: Actionid3;
  actionToken: Actiontoken;
  dependencies: Dependencies2;
  sessionId: Sessionid;
}
export interface RichWarning {
  blockIds: Blockids3;
  code: Code3;
  count?: Count;
  evidence: Evidence16;
  id: Id45;
  locations?: Locations;
  recordIds: Recordids;
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
export interface AgentEditReceipt {
  batchId: Batchid1;
  clientMutationId: Clientmutationid1;
  disposition: Disposition2;
  documentRevision: Documentrevision2;
  durable: Durable;
  error: AgentError | null;
  factsRevision: Factsrevision1;
  projectRevision: Projectrevision1;
  requestSha256: Requestsha2562;
  runId: Runid1;
  toolKey: Toolkey;
}
export interface AgentError {
  code: Code4;
}
