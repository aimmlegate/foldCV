export type Verdict = "likely" | "unlikely" | "uncertain";
export type Id = string;
export type Category =
  ("identity" | "contacts" | "summary" | "experience" | "education" | "skills" | "languages" | "other") | null;
/**
 * @maxItems 1000
 */
export type Duplicateof = string[];
export type Id1 = string;
export type Kind = "paragraph" | "heading" | "section" | "bullet_list" | "duplicate";
export type Listitem = boolean;
export type Modelblock = boolean;
export type Region = "header" | "sidebar" | "main";
/**
 * @maxItems 1000
 */
export type Sourcekeys = string[];
export type Title = string | null;
/**
 * @maxItems 5000
 */
export type Blocks = ImportBlock[];
export type Id2 = string;
export type Record = (ImportEmployment | ImportEducation | ImportTechnology | ImportLanguage) | null;
export type Employer = string;
export type Kind1 = "employment";
export type End = string;
export type Present = boolean;
export type Start = string;
/**
 * @maxItems 40
 */
export type Periods = ImportPeriod[];
export type Role = string;
export type Display = string;
export type Experience = string;
export type Technical = boolean | null;
/**
 * @maxItems 100
 */
export type Technologies = (string | ImportSkill)[];
export type Completion = string;
export type Institution = string;
export type Kind2 = "education";
export type Qualification = string;
export type Specialty = string;
export type Display1 = string;
export type Experience1 = string;
export type Kind3 = "technology";
export type Technical1 = boolean | null;
export type Kind4 = "language";
export type Language = string;
export type Level = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys1 = string[];
export type Text = string;
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
export type Title1 = string;
export type Batchid = string;
export type Requestsha256 = string;
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
export type Inputid = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text1 = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Text2 = string;
export type Id3 = string;
export type Certifications = CertificationDetails[];
export type Code = "team_size_conflict";
export type Evidence1 = EvidenceSpan[];
export type Factids = string[];
export type Id4 = string;
export type Jobid = string;
export type Conflicts = FactConflict[];
export type Id5 = string;
export type Education = EducationDetails[];
export type Employer1 = string;
export type Factids1 = string[];
export type Id6 = string;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Periods1 = Period[];
export type Role1 = string;
export type Factids2 = string[];
export type Id7 = string;
export type Name1 = string;
export type Subprojects = Subproject[];
export type Employment = Job[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status = "complete" | "partial";
export type Code1 = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page = number | null;
export type Section = string;
export type Sourceid1 = string;
export type Unitid1 = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Sourceid2 = string;
export type Sourcerevision1 = number;
export type Unitid2 = string;
export type Unitrevision1 = number;
export type Evidence2 = Evidence3[];
export type Id8 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind5 = "text";
export type Literalevidence = EvidenceSpan[];
export type Origin = "source" | "user";
export type Revision = number;
export type Subprojectid = string | null;
export type Text3 = string;
export type Evidence4 = Evidence3[];
export type Id9 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind6 = "technology";
export type Literalevidence1 = EvidenceSpan[];
export type Origin1 = "source" | "user";
export type Revision1 = number;
export type Subprojectid1 = string | null;
export type Canonicalid = string;
export type Display2 = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence5 = Evidence3[];
export type Id10 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind7 = "metric";
export type Literalevidence2 = EvidenceSpan[];
export type Origin2 = "source" | "user";
export type Revision2 = number;
export type Subprojectid2 = string | null;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period1 = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope1 = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence6 = Evidence3[];
export type Id11 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind8 = "leadership";
export type Literalevidence3 = EvidenceSpan[];
export type Origin3 = "source" | "user";
export type Revision3 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence7 = Evidence3[];
export type Id12 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid5 = string | null;
export type Kind9 = "date";
export type Literalevidence4 = EvidenceSpan[];
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid4 = string | null;
export type Evidence8 = Evidence3[];
export type Id13 = string;
export type Importance5 = "essential" | "normal" | "minor";
export type Jobid6 = string | null;
export type Kind10 = "text";
export type Origin5 = "source" | "user";
export type Revision5 = number;
export type Subprojectid5 = string | null;
export type Evidence9 = Evidence3[];
export type Id14 = string;
export type Importance6 = "essential" | "normal" | "minor";
export type Jobid7 = string | null;
export type Kind11 = "technology";
export type Origin6 = "source" | "user";
export type Revision6 = number;
export type Subprojectid6 = string | null;
export type Evidence10 = Evidence3[];
export type Id15 = string;
export type Importance7 = "essential" | "normal" | "minor";
export type Jobid8 = string | null;
export type Kind12 = "metric";
export type Origin7 = "source" | "user";
export type Revision7 = number;
export type Subprojectid7 = string | null;
export type Evidence11 = Evidence3[];
export type Id16 = string;
export type Importance8 = "essential" | "normal" | "minor";
export type Jobid9 = string | null;
export type Kind13 = "leadership";
export type Origin8 = "source" | "user";
export type Revision8 = number;
export type Subprojectid8 = string | null;
export type Evidence12 = Evidence3[];
export type Id17 = string;
export type Importance9 = "essential" | "normal" | "minor";
export type Jobid10 = string | null;
export type Kind14 = "date";
export type Origin9 = "source" | "user";
export type Revision9 = number;
export type Subprojectid9 = string | null;
export type Evidence13 = Evidence3[];
export type Id18 = string;
export type Importance10 = "essential" | "normal" | "minor";
export type Jobid11 = string | null;
export type Kind15 = "candidate_detail";
export type Origin10 = "source" | "user";
export type Revision10 = number;
export type Subprojectid10 = string | null;
export type Field = "name" | "title" | "location" | "education" | "certification" | "language" | "private_metadata";
export type Fieldid = string | null;
export type Text4 = string;
export type Evidence14 = Evidence3[];
export type Id19 = string;
export type Importance11 = "essential" | "normal" | "minor";
export type Jobid12 = string | null;
export type Kind16 = "name_assessment";
export type Origin11 = "source" | "user";
export type Revision11 = number;
export type Subprojectid11 = string | null;
export type Evidence15 = EvidenceSpan[];
export type Missingsurname = boolean | null;
export type Revision12 = number;
export type Evidence16 = Evidence3[];
export type Id20 = string;
export type Importance12 = "essential" | "normal" | "minor";
export type Jobid13 = string | null;
export type Kind17 = "source_observation";
export type Origin12 = "source" | "user";
export type Revision13 = number;
export type Subprojectid12 = string | null;
export type Revision14 = number;
export type Evidence17 = Evidence3[];
export type Id21 = string;
export type Importance13 = "essential" | "normal" | "minor";
export type Jobid14 = string | null;
export type Kind18 = "employment";
export type Literalevidence5 = EvidenceSpan[];
export type Origin13 = "source" | "user";
export type Revision15 = number;
export type Subprojectid13 = string | null;
export type Employer2 = string;
export type Jobid15 = string;
export type Endtext = string;
export type Evidence18 = EvidenceSpan[];
export type Id22 = string;
export type Present1 = boolean;
export type Starttext = string;
export type Periods2 = EmploymentPeriodValue[];
export type Role2 = string;
export type Subprojects1 = Subproject[];
export type Facts1 = (
  | (GuiTextFact | GuiTechnologyFact | GuiMetricFact | GuiLeadershipFact | GuiDateFact)
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
  | EmploymentFact
)[];
export type Endtext1 = string;
export type Evidence19 = EvidenceSpan[];
export type Id23 = string;
export type Present2 = boolean;
export type Starttext1 = string;
export type Id24 = string;
export type Languages = LanguageDetails[];
export type Kind19 = "phone" | "email" | "messenger" | "birth_date" | "age" | "platform_metadata";
export type Privatedetails = PrivateDetails[];
export type Rulesrevision = number;
/**
 * @maxItems 40
 */
export type Certifications1 = CertificationDetails[];
/**
 * @maxItems 40
 */
export type Education1 = EducationDetails[];
export type Importance14 = "essential" | "normal" | "minor";
export type Jobtempid = string | null;
export type Kind20 = "text" | "technology" | "date" | "metric" | "leadership";
export type Literalevidence6 = EvidenceSpan[];
export type Sourceid3 = string;
export type Subprojecttempid = string | null;
export type Tempid = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids = [string, ...string[]];
export type Value = TextValue | TechnologyValue | PartialDate | MetricValue | LeadershipValue;
/**
 * @maxItems 500
 */
export type Facts2 = GuiFactProposal[];
export type Employer3 = string;
/**
 * @maxItems 20
 */
export type Periods3 =
  | []
  | [GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ];
export type Endtext2 = string | null;
export type Evidence20 = EvidenceSpan[];
export type Present3 = boolean;
export type Starttext2 = string | null;
export type Role3 = string;
export type Sourceid4 = string;
export type Name2 = string;
export type Tempid1 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids1 = [string, ...string[]];
/**
 * @maxItems 100
 */
export type Subprojects2 = ProposedSubproject[];
export type Tempid2 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids2 = [string, ...string[]];
/**
 * @maxItems 100
 */
export type Jobs = GuiJobProposal[];
/**
 * @maxItems 40
 */
export type Languages1 = LanguageDetails[];
/**
 * @maxItems 100
 */
export type Privatedetails1 = PrivateDetails[];
export type Schemaversion = 1;
export type Disposition = "facts" | "administrative" | "duplicate" | "unresolved";
export type Duplicateof1 = string | null;
export type Facttempids = string[];
export type Sourceid5 = string;
export type Unitid3 = string;
/**
 * @maxItems 5000
 */
export type Units = UnitProposal[];
export type Sourcefingerprint = string;
export type Byteref = string;
export type Bytesha256 = string;
export type Id25 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id26 = string;
export type Origin14 = "user";
export type Revision16 = number;
export type Text5 = string;
export type Unitid4 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision17 = number;
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id27 = string;
export type Column = number | null;
export type Index = number;
export type Kind21 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision18 = number;
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
export type Text6 = string;
export type Units1 = SourceUnit[];
export type Code2 = string;
export type Page1 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources = Source[];
export type Schemaversion1 = 1;
export type Createdat = string;
export type Documentrevision = number;
export type Clientmutationid = string;
export type Requestsha2561 = string;
export type Resultingrevision = number;
export type Mutationreplay = RichMutationReplay[];
export type Mode = "structured" | "digest" | "imported";
export type Evidence21 = EvidenceSpan[];
export type Id28 = string;
export type Kind22 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision19 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected = boolean;
export type Value1 = string | null;
export type Origin15 = "source" | "user";
export type Revision20 = number;
export type Usercorrected1 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence22 = EvidenceSpan[];
export type Id29 = string;
export type Kind23 = "detail";
export type Label = string;
export type Origin16 = "source" | "user";
export type Revision21 = number;
export type Usercorrected2 = boolean;
export type Evidence23 = EvidenceSpan[];
export type Id30 = string;
export type Kind24 = "employment";
export type Origin17 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision22 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected3 = boolean;
export type Evidence24 = EvidenceSpan[];
export type Id31 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision23 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Value2 = boolean | null;
export type Revision24 = number;
export type Periods4 = WorkingPeriod[];
export type Revision25 = number;
export type Usercorrected5 = boolean;
export type Evidence25 = EvidenceSpan[];
export type Id32 = string;
export type Jobid16 = string;
export type Kind25 = "subproject";
export type Origin18 = "source" | "user";
export type Periods5 = WorkingPeriod[];
export type Revision26 = number;
export type Usercorrected6 = boolean;
export type Evidence26 = EvidenceSpan[];
export type Id33 = string;
export type Jobid17 = string | null;
export type Kind26 = "technology";
export type Origin19 = "source" | "user";
export type Revision27 = number;
export type Subprojectid14 = string | null;
export type Technical2 = boolean | null;
export type Usercorrected7 = boolean;
export type Evidence27 = EvidenceSpan[];
export type Id34 = string;
export type Kind27 = "education";
export type Origin20 = "source" | "user";
export type Revision28 = number;
export type Usercorrected8 = boolean;
export type Evidence28 = EvidenceSpan[];
export type Id35 = string;
export type Kind28 = "language";
export type Origin21 = "source" | "user";
export type Revision29 = number;
export type Usercorrected9 = boolean;
export type Evidence29 = EvidenceSpan[];
export type Id36 = string;
export type Kind29 = "certification";
export type Origin22 = "source" | "user";
export type Revision30 = number;
export type Usercorrected10 = boolean;
export type Evidence30 = EvidenceSpan[];
export type Id37 = string;
export type Jobid18 = string | null;
export type Kind30 = "claim";
export type Origin23 = "source" | "user";
export type Revision31 = number;
export type Subprojectid15 = string | null;
export type Usercorrected11 = boolean;
export type Evidence31 = EvidenceSpan[];
export type Id38 = string;
export type Jobid19 = string | null;
export type Kind31 = "metric";
export type Origin24 = "source" | "user";
export type Revision32 = number;
export type Subprojectid16 = string | null;
export type Usercorrected12 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision33 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected13 = boolean;
export type Evidence32 = EvidenceSpan[];
export type Id39 = string;
export type Jobid20 = string | null;
export type Kind32 = "leadership";
export type Origin25 = "source" | "user";
export type Revision34 = number;
export type Subprojectid17 = string | null;
export type Usercorrected14 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision35 = number;
export type Status5 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected15 = boolean;
export type Category1 = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence33 = EvidenceSpan[];
export type Id40 = string;
export type Kind33 = "unresolved";
export type Origin26 = "source" | "user";
export type Revision36 = number;
export type Status6 = "unresolved" | "pending" | "conflict";
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
export type Revision37 = number;
export type Actionid = string;
export type Orderindex = number;
export type Recordid = string;
export type Revision38 = number;
export type Tombstones = RecordTombstone[];
export type Actionid1 = string | null;
export type Fingerprint = string | null;
export type Id41 = string;
export type Kind34 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision39 = number;
export type Dependencies = DependencyStamp[];
export type Errorcode = string | null;
export type Id42 = string;
export type Kind35 =
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
export type Selectedinput = "text" | "file";
export type Selectedsourceid = string | null;
export type Sources1 = Source[];
export type Warnings1 = string[];
export type Height = number;
export type Id43 = string;
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
export type Code3 = boolean;
export type Italic = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text7 = string;
export type Type = "text";
export type Content1 = StyledText[];
export type Href = string;
export type Type1 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Fieldkey = string;
export type Recordid1 = string;
export type Syncedfactrevision = number;
export type Text8 = string;
export type Type2 = "fact_field";
export type Content = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id44 = string;
export type Alignment = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Presentation = "standard" | "focus";
export type Recordid2 = string | null;
export type Textcolor1 = string;
export type Evidence34 = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id45 = string;
export type Kind36 = "citation";
export type Recordid3 = string;
export type Fieldkey1 = string;
export type Id46 = string;
export type Kind37 = "field_binding";
export type Recordid4 = string;
export type Id47 = string;
export type Kind38 = "working_owner";
export type Recordid5 = string;
/**
 * @minItems 1
 */
export type Evidence35 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id48 = string;
export type Kind39 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision40 = number;
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
export type Id49 = string;
export type Alignment1 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height1 = number;
export type Width1 = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision41 = number;
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
export type Id50 = string;
export type Revision42 = number;
export type Rowspan = number;
export type Cells = TableCell[];
export type Id51 = string;
export type Id52 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision43 = number;
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
export type Id53 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision44 = number;
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
export type Id54 = string;
export type Backgroundcolor4 = string;
export type Language1 = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision45 = number;
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
export type Id55 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision46 = number;
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
export type Id56 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision47 = number;
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
export type Id57 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision48 = number;
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
export type Id58 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start1 = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision49 = number;
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
export type Id59 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision50 = number;
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
export type Id60 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level1 = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision51 = number;
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
export type Id61 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision52 = number;
export type Type14 = "paragraph";
export type Blocks1 = (
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
export type Id62 = string;
export type Revision53 = number;
export type Role4 = "header" | "sidebar" | "main";
export type Revision54 = number;
export type Schemaversion2 = 1;
export type Evidence36 = EvidenceSpan[];
export type Id63 = string;
export type Rawtext5 = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Blockids = string[];
export type Disposition2 = "placed" | "excluded";
export type Reason = string | null;
export type Sourceid6 = string;
export type Unitid5 = string;
export type Importcoverage = ImportCoverage[];
export type Operations1 = RichOperation[];
export type Projectid = string;
export type Documentrevision1 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id64 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision55 = number;
export type Schemaversion3 = 5;
export type Sources2 = Source[];
export type Path1 = string;
export type Sha2561 = string;
export type Size1 = number;
export type Assets1 = AssetRef[];
export type Contentpolicyversion = string;
export type Id65 = string;
export type Packagesha256 = string;
export type Version1 = string;
export type Projectid1 = string;
export type Projectrevision = number;
export type Markdown = string;
export type Revision56 = number;
export type Sha2562 = string;
export type Schemaversion4 = 6;
export type Actionid2 = string;
export type Blockids1 = string[];
export type Dependencies1 = DependencyStamp[];
export type Errorcode1 = string | null;
export type Factids3 = string[];
export type Fieldkeys1 = string[];
export type Id66 = string;
export type Instruction = string | null;
export type Kind40 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
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
export type Kind41 = "put_block";
export type Parentid = string;
export type Beforerevision1 = number;
export type Blockid = string;
export type Kind42 = "remove_block";
export type Afterid1 = string | null;
export type Beforerevision2 = number;
export type Blockid1 = string;
export type Kind43 = "move_block";
export type Parentid1 = string;
export type Beforerevision3 = number;
export type Blockid2 = string;
export type Cellid = string | null;
export type Content13 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End1 = number;
export type Field1 = "content" | "caption";
export type Kind44 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start2 = number;
export type Beforerevision4 = number | null;
export type Kind45 = "put_record";
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
export type Kind46 = "remove_record";
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
export type Kind47 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Status8 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Syncrecords = RichSyncRecord[];
export type Title2 = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;
export type Blockids3 = string[];
export type Code4 = string;
export type Count = number;
export type Evidence37 = Evidence3[];
export type Id67 = string;
export type Page2 = number | null;
export type Sourceid7 = string;
export type Locations = WarningLocation[];
export type Recordids = string[];
export type Warnings2 = RichWarning[];

export interface ProcessingCandidateV1 {
  assessment: ResumeAssessment | null;
  id: Id;
  importDraft?: ImportDraft | null;
  inputId: Inputid;
  normalized: GuiNormalizedResult | null;
  schemaVersion: Schemaversion1;
  workspace: WorkspaceV6 | null;
}
export interface ResumeAssessment {
  verdict: Verdict;
}
export interface ImportDraft {
  blocks?: Blocks;
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
  category?: Category;
  duplicateOf?: Duplicateof;
  id: Id1;
  kind?: Kind;
  listItem?: Listitem;
  modelBlock?: Modelblock;
  region?: Region;
  sourceKeys?: Sourcekeys;
  title?: Title;
}
export interface ImportFact {
  id: Id2;
  record?: Record;
  sourceKeys?: Sourcekeys1;
  text?: Text;
}
export interface ImportEmployment {
  employer?: Employer;
  kind: Kind1;
  periods?: Periods;
  role?: Role;
  technologies?: Technologies;
}
export interface ImportPeriod {
  end?: End;
  present?: Present;
  start?: Start;
}
export interface ImportSkill {
  display: Display;
  experience?: Experience;
  technical?: Technical;
}
export interface ImportEducation {
  completion?: Completion;
  institution?: Institution;
  kind: Kind2;
  qualification?: Qualification;
  specialty?: Specialty;
}
export interface ImportTechnology {
  display: Display1;
  experience?: Experience1;
  kind: Kind3;
  technical?: Technical1;
}
export interface ImportLanguage {
  kind: Kind4;
  language?: Language;
  level?: Level;
}
export interface ImportProfile {
  location?: Location;
  name?: Name;
  sourceKeys?: Sourcekeys2;
  title?: Title1;
}
export interface ImportReceipt {
  batchId: Batchid;
  requestSha256: Requestsha256;
  sequence: Sequence;
}
export interface GuiNormalizedResult {
  candidate: CandidateDetails;
  certifications: Certifications;
  conflicts?: Conflicts;
  education: Education;
  employment?: Employment;
  extraction?: ExtractionReport | null;
  facts: Facts1;
  fieldFactIds: Fieldfactids;
  jobPeriods?: Jobperiods;
  languages: Languages;
  nameAssessment: NameAssessment;
  observationAssessment: ObservationAssessment;
  privateDetails: Privatedetails;
  rulesRevision: Rulesrevision;
  semanticProposal: GuiSemanticProposal;
  sourceFingerprint: Sourcefingerprint;
  sourceObservedAt: PartialDate | null;
  sources: Sources;
}
export interface CandidateDetails {
  location: SupportedText;
  name: SupportedText;
  title: SupportedText;
}
export interface SupportedText {
  evidence: Evidence;
  text: Text2;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text1;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface CertificationDetails {
  dateText: SupportedText;
  id: Id3;
  issuer: SupportedText;
  name: SupportedText;
}
export interface FactConflict {
  code: Code;
  evidence: Evidence1;
  factIds: Factids;
  id: Id4;
  jobId: Jobid;
}
export interface EducationDetails {
  dateText: SupportedText;
  id: Id5;
  institution: SupportedText;
  qualification: SupportedText;
  specialty: SupportedText;
}
export interface Job {
  employer: Employer1;
  factIds: Factids1;
  id: Id6;
  periods: Periods1;
  role: Role1;
  subprojects: Subprojects;
}
export interface Period {
  end: PartialDate | null;
  start: PartialDate;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface Subproject {
  factIds: Factids2;
  id: Id7;
  name: Name1;
  period: Period | null;
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
  sourceId: Sourceid1;
  unitId: Unitid1;
}
export interface GuiTextFact {
  evidence: Evidence2;
  id: Id8;
  importance: Importance;
  jobId: Jobid1;
  kind: Kind5;
  literalEvidence: Literalevidence;
  origin: Origin;
  revision: Revision;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface Evidence3 {
  sourceId: Sourceid2;
  sourceRevision: Sourcerevision1;
  unitId: Unitid2;
  unitRevision: Unitrevision1;
}
export interface TextValue {
  text: Text3;
}
export interface GuiTechnologyFact {
  evidence: Evidence4;
  id: Id9;
  importance: Importance1;
  jobId: Jobid2;
  kind: Kind6;
  literalEvidence: Literalevidence1;
  origin: Origin1;
  revision: Revision1;
  subprojectId: Subprojectid1;
  value: TechnologyValue;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display2;
  scope: Scope;
}
export interface GuiMetricFact {
  evidence: Evidence5;
  id: Id10;
  importance: Importance2;
  jobId: Jobid3;
  kind: Kind7;
  literalEvidence: Literalevidence2;
  origin: Origin2;
  revision: Revision2;
  subprojectId: Subprojectid2;
  value: MetricValue;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period1;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope1;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface GuiLeadershipFact {
  evidence: Evidence6;
  id: Id11;
  importance: Importance3;
  jobId: Jobid4;
  kind: Kind8;
  literalEvidence: Literalevidence3;
  origin: Origin3;
  revision: Revision3;
  subprojectId: Subprojectid3;
  value: LeadershipValue;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface GuiDateFact {
  evidence: Evidence7;
  id: Id12;
  importance: Importance4;
  jobId: Jobid5;
  kind: Kind9;
  literalEvidence: Literalevidence4;
  origin: Origin4;
  revision: Revision4;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface TextFact {
  evidence: Evidence8;
  id: Id13;
  importance: Importance5;
  jobId: Jobid6;
  kind: Kind10;
  origin: Origin5;
  revision: Revision5;
  subprojectId: Subprojectid5;
  value: TextValue;
}
export interface TechnologyFact {
  evidence: Evidence9;
  id: Id14;
  importance: Importance6;
  jobId: Jobid7;
  kind: Kind11;
  origin: Origin6;
  revision: Revision6;
  subprojectId: Subprojectid6;
  value: TechnologyValue;
}
export interface MetricFact {
  evidence: Evidence10;
  id: Id15;
  importance: Importance7;
  jobId: Jobid8;
  kind: Kind12;
  origin: Origin7;
  revision: Revision7;
  subprojectId: Subprojectid7;
  value: MetricValue;
}
export interface LeadershipFact {
  evidence: Evidence11;
  id: Id16;
  importance: Importance8;
  jobId: Jobid9;
  kind: Kind13;
  origin: Origin8;
  revision: Revision8;
  subprojectId: Subprojectid8;
  value: LeadershipValue;
}
export interface DateFact {
  evidence: Evidence12;
  id: Id17;
  importance: Importance9;
  jobId: Jobid10;
  kind: Kind14;
  origin: Origin9;
  revision: Revision9;
  subprojectId: Subprojectid9;
  value: PartialDate;
}
export interface CandidateFact {
  evidence: Evidence13;
  id: Id18;
  importance: Importance10;
  jobId: Jobid11;
  kind: Kind15;
  origin: Origin10;
  revision: Revision10;
  subprojectId: Subprojectid10;
  value: CandidateDetail;
}
export interface CandidateDetail {
  field: Field;
  fieldId?: Fieldid;
  text: Text4;
}
export interface NameAssessmentFact {
  evidence: Evidence14;
  id: Id19;
  importance: Importance11;
  jobId: Jobid12;
  kind: Kind16;
  origin: Origin11;
  revision: Revision11;
  subprojectId: Subprojectid11;
  value: NameAssessment;
}
export interface NameAssessment {
  evidence: Evidence15;
  missingSurname: Missingsurname;
  revision: Revision12;
}
export interface ObservationFact {
  evidence: Evidence16;
  id: Id20;
  importance: Importance12;
  jobId: Jobid13;
  kind: Kind17;
  origin: Origin12;
  revision: Revision13;
  subprojectId: Subprojectid12;
  value: ObservationAssessment;
}
export interface ObservationAssessment {
  evidence: EvidenceSpan | null;
  revision: Revision14;
  sourceObservedAt: PartialDate | null;
}
export interface EmploymentFact {
  evidence: Evidence17;
  id: Id21;
  importance: Importance13;
  jobId: Jobid14;
  kind: Kind18;
  literalEvidence: Literalevidence5;
  origin: Origin13;
  revision: Revision15;
  subprojectId: Subprojectid13;
  value: EmploymentValue;
}
export interface EmploymentValue {
  employer: Employer2;
  jobId: Jobid15;
  periods: Periods2;
  role: Role2;
  subprojects: Subprojects1;
}
export interface EmploymentPeriodValue {
  end: PartialDate | null;
  endText: Endtext;
  evidence: Evidence18;
  id: Id22;
  present: Present1;
  start: PartialDate | null;
  startText: Starttext;
}
export interface Fieldfactids {
  [k: string]: string[];
}
export interface Jobperiods {
  [k: string]: NormalizedPeriod[];
}
export interface NormalizedPeriod {
  end: PartialDate | null;
  endText: Endtext1;
  evidence: Evidence19;
  id: Id23;
  present: Present2;
  start: PartialDate | null;
  startText: Starttext1;
}
export interface LanguageDetails {
  id: Id24;
  name: SupportedText;
  proficiency: SupportedText;
}
export interface PrivateDetails {
  kind: Kind19;
  value: SupportedText;
}
export interface GuiSemanticProposal {
  candidate: CandidateDetails;
  certifications: Certifications1;
  education: Education1;
  facts: Facts2;
  jobs: Jobs;
  languages: Languages1;
  nameAssessment: NameAssessment;
  observationAssessment: ObservationAssessment;
  privateDetails: Privatedetails1;
  schemaVersion: Schemaversion;
  units: Units;
}
export interface GuiFactProposal {
  importance?: Importance14;
  jobTempId?: Jobtempid;
  kind: Kind20;
  literalEvidence?: Literalevidence6;
  sourceId: Sourceid3;
  subprojectTempId?: Subprojecttempid;
  tempId: Tempid;
  unitIds: Unitids;
  value: Value;
}
export interface GuiJobProposal {
  employer: Employer3;
  periods: Periods3;
  role: Role3;
  sourceId: Sourceid4;
  subprojects?: Subprojects2;
  tempId: Tempid2;
  unitIds: Unitids2;
}
export interface GuiPeriodProposal {
  end: PartialDate | null;
  endText?: Endtext2;
  evidence?: Evidence20;
  present?: Present3;
  start: PartialDate | null;
  startText?: Starttext2;
}
export interface ProposedSubproject {
  name: Name2;
  period?: Period | null;
  tempId: Tempid1;
  unitIds: Unitids1;
}
export interface UnitProposal {
  disposition: Disposition;
  duplicateOf?: Duplicateof1;
  factTempIds: Facttempids;
  sourceId: Sourceid5;
  unitId: Unitid3;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id25;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision17;
  units: Units1;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id26;
  origin: Origin14;
  revision: Revision16;
  text: Text5;
  unitId: Unitid4;
}
export interface SourceUnit {
  disposition: Disposition1;
  id: Id27;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision18;
  structure?: SourceStructure | null;
  text: Text6;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind21;
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
  code: Code2;
  page?: Page1;
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
  schemaVersion: Schemaversion4;
  sourceObservedAt: PartialDate | null;
  syncRecords: Syncrecords;
  title: Title2;
  titleManuallySet: Titlemanuallyset;
  updatedAt: Updatedat;
  warnings: Warnings2;
}
export interface RichMutationReplay {
  clientMutationId: Clientmutationid;
  requestSha256: Requestsha2561;
  resultingRevision: Resultingrevision;
}
export interface RichPreDraft {
  facts: WorkingFacts;
  importDraft?: ImportDraft | null;
  operations: Operations;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources1;
  warnings: Warnings1;
}
export interface WorkingFacts {
  extraction?: ExtractionReport | null;
  mode?: Mode;
  records: Records;
  revision: Revision37;
  tombstones: Tombstones;
}
export interface CandidateRecord {
  evidence: Evidence21;
  id: Id28;
  kind: Kind22;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin15;
  revision: Revision20;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected1;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision19;
  status: Status1;
  userCorrected?: Usercorrected;
  value: Value1;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence22;
  id: Id29;
  kind: Kind23;
  label: Label;
  origin: Origin16;
  revision: Revision21;
  userCorrected?: Usercorrected2;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence23;
  id: Id30;
  kind: Kind24;
  origin: Origin17;
  periods: Periods4;
  revision: Revision25;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected5;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence24;
  id: Id31;
  present: WorkingFieldBool;
  revision: Revision24;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision22;
  status: Status2;
  userCorrected?: Usercorrected3;
  value: PartialDate | null;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision23;
  status: Status3;
  userCorrected?: Usercorrected4;
  value: Value2;
}
export interface SubprojectRecord {
  evidence: Evidence25;
  id: Id32;
  jobId: Jobid16;
  kind: Kind25;
  name: WorkingFieldStr;
  origin: Origin18;
  periods: Periods5;
  revision: Revision26;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence26;
  experience?: WorkingFieldStr;
  id: Id33;
  jobId: Jobid17;
  kind: Kind26;
  origin: Origin19;
  revision: Revision27;
  subprojectId: Subprojectid14;
  technical?: Technical2;
  userCorrected?: Usercorrected7;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence27;
  id: Id34;
  institution: WorkingFieldStr;
  kind: Kind27;
  origin: Origin20;
  qualification: WorkingFieldStr;
  revision: Revision28;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected8;
}
export interface LanguageRecord {
  evidence: Evidence28;
  id: Id35;
  kind: Kind28;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin21;
  revision: Revision29;
  userCorrected?: Usercorrected9;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence29;
  id: Id36;
  issuer: WorkingFieldStr;
  kind: Kind29;
  name: WorkingFieldStr;
  origin: Origin22;
  revision: Revision30;
  userCorrected?: Usercorrected10;
}
export interface ClaimRecord {
  evidence: Evidence30;
  id: Id37;
  jobId: Jobid18;
  kind: Kind30;
  origin: Origin23;
  revision: Revision31;
  subprojectId: Subprojectid15;
  userCorrected?: Usercorrected11;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence31;
  id: Id38;
  jobId: Jobid19;
  kind: Kind31;
  origin: Origin24;
  revision: Revision32;
  subprojectId: Subprojectid16;
  userCorrected?: Usercorrected12;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision33;
  status: Status4;
  userCorrected?: Usercorrected13;
  value: MetricValue | null;
}
export interface LeadershipRecord {
  evidence: Evidence32;
  id: Id39;
  jobId: Jobid20;
  kind: Kind32;
  origin: Origin25;
  revision: Revision34;
  subprojectId: Subprojectid17;
  userCorrected?: Usercorrected14;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision35;
  status: Status5;
  userCorrected?: Usercorrected15;
  value: LeadershipValue | null;
}
export interface UnresolvedRecord {
  category: Category1;
  evidence: Evidence33;
  id: Id40;
  kind: Kind33;
  origin: Origin26;
  revision: Revision36;
  status: Status6;
  userCorrected?: Usercorrected16;
}
export interface RecordTombstone {
  actionId: Actionid;
  orderIndex: Orderindex;
  recordId: Recordid;
  revision: Revision38;
}
export interface RichOperation {
  actionId: Actionid1;
  dependencies: Dependencies;
  errorCode: Errorcode;
  id: Id42;
  kind: Kind35;
  status: Status7;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id41;
  kind: Kind34;
  revision: Revision39;
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
  revision: Revision55;
  schemaVersion: Schemaversion3;
  sources: Sources2;
  template: TemplateManifest;
}
export interface LocalImageAsset {
  height: Height;
  id: Id43;
  mimeType: Mimetype1;
  path: Path;
  sha256: Sha256;
  size: Size;
  width: Width;
}
export interface RichDocumentV1 {
  regions: Regions;
  revision: Revision54;
  schemaVersion: Schemaversion2;
}
export interface RichRegion {
  blocks: Blocks1;
  id: Id62;
  revision: Revision53;
  role: Role4;
}
export interface ParagraphBlock {
  children: Children;
  content: Content12;
  id: Id61;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision52;
  type: Type14;
}
export interface HeadingBlock {
  children: Children1;
  content: Content11;
  id: Id60;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision51;
  type: Type13;
}
export interface BulletBlock {
  children: Children2;
  content: Content10;
  id: Id59;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision50;
  type: Type12;
}
export interface NumberedBlock {
  children: Children3;
  content: Content9;
  id: Id58;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision49;
  type: Type11;
}
export interface ChecklistBlock {
  children: Children4;
  content: Content8;
  id: Id57;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision48;
  type: Type10;
}
export interface ToggleBlock {
  children: Children5;
  content: Content7;
  id: Id56;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision47;
  type: Type9;
}
export interface QuoteBlock {
  children: Children6;
  content: Content6;
  id: Id55;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision46;
  type: Type8;
}
export interface CodeBlock {
  children: Children7;
  content: Content5;
  id: Id54;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision45;
  type: Type7;
}
export interface DividerBlock {
  children: Children8;
  content: Content4;
  id: Id53;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision44;
  type: Type6;
}
export interface TableBlock {
  children: Children9;
  content: TableContent;
  id: Id52;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision43;
  type: Type5;
}
export interface ImageBlock {
  children: Children10;
  content: Content2;
  id: Id49;
  props: ImageProps;
  provenance: Provenance1;
  revision: Revision41;
  type: Type4;
}
export interface SectionBlock {
  children: Children11;
  content: Content;
  id: Id44;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision40;
  type: Type3;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text7;
  type: Type;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold1;
  code?: Code3;
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
  text: Text8;
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
  evidence: Evidence34;
  fieldKeys: Fieldkeys;
  id: Id45;
  kind: Kind36;
  recordId: Recordid3;
}
export interface FieldBinding {
  fieldKey: Fieldkey1;
  id: Id46;
  kind: Kind37;
  recordId: Recordid4;
}
export interface WorkingOwnership {
  id: Id47;
  kind: Kind38;
  recordId: Recordid5;
}
export interface SourceWitness {
  evidence: Evidence35;
  id: Id48;
  kind: Kind39;
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
  id: Id51;
}
export interface TableCell {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content3;
  id: Id50;
  revision: Revision42;
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
  evidence: Evidence36;
  id: Id63;
  rawText: Rawtext5;
}
export interface ImportCoverage {
  blockIds: Blockids;
  disposition: Disposition2;
  reason: Reason;
  sourceId: Sourceid6;
  unitId: Unitid5;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision1;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id64;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface TemplateManifest {
  assets: Assets1;
  contentPolicyVersion: Contentpolicyversion;
  id: Id65;
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
  revision: Revision56;
  sha256: Sha2562;
}
export interface RichSyncRecord {
  actionId: Actionid2;
  blockIds: Blockids1;
  dependencies: Dependencies1;
  errorCode: Errorcode1;
  factIds: Factids3;
  fieldKeys: Fieldkeys1;
  id: Id66;
  instruction?: Instruction;
  kind?: Kind40;
  proposedSteps?: Proposedsteps;
  ready?: Ready;
  selection?: RichSelection | null;
  status: Status8;
}
export interface PutBlock {
  afterId: Afterid;
  beforeRevision: Beforerevision;
  block: Block;
  keepChildren?: Keepchildren;
  kind: Kind41;
  parentId: Parentid;
}
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid;
  kind: Kind42;
}
export interface MoveBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision2;
  blockId: Blockid1;
  kind: Kind43;
  parentId: Parentid1;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid2;
  cellId: Cellid;
  content: Content13;
  end: End1;
  field: Field1;
  kind: Kind44;
  start: Start2;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind45;
  record: Record1;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind46;
  recordId: Recordid6;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids2;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind47;
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
  code: Code4;
  count?: Count;
  evidence: Evidence37;
  id: Id67;
  locations?: Locations;
  recordIds: Recordids;
}
export interface WarningLocation {
  page?: Page2;
  sourceId: Sourceid7;
}
