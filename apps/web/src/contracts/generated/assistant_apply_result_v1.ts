export type Action = "rename" | "formatting_date" | "archive" | "restore" | "delete";
export type Archived = boolean | null;
export type Deleted = boolean;
export type Title = string | null;
export type Changedblockids = string[];
export type Clientmutationid = string;
export type Documentrevision = number;
export type Actionid = string;
export type Kind = "edit";
export type Replayed = boolean;
export type Durability = "pending" | "durable" | "failed";
export type Errorcode = string | null;
export type Id = string;
export type Stage = "assess_resume" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Startedat = string | null;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Subtitle = string;
export type Title1 = string;
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
export type Records = string[];
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
export type Blockid = string;
export type Jobid = string | null;
export type Label = string;
export type Afterid = string | null;
export type Parentid = string;
export type Technologytargets = EditorTechnologyTarget[];
export type Capabilities = string[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id1 = "header" | "sidebar" | "main";
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
export type MissingIcon = "text_only" | "initial";
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
export type Documentrevision1 = number;
export type Factshash = string;
export type Packagehash1 = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;
export type Saveerror = string | null;
export type Saveddocumentrevision = number | null;
export type Savedprojectrevision = number | null;
export type Schemaversion2 = 1;
export type Createdat = string;
export type Documentrevision2 = number;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Clientmutationid1 = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
export type Mutationreplay = RichMutationReplay[];
export type Cellid = string;
export type Fieldkey = string;
export type Periodid = string | null;
export type Itemhandle1 = string;
export type Recordid = string;
export type Semanticschemahash = string;
export type Semantictype = string;
export type Builtinidentities = BuiltinItemIdentity[];
export type Active = boolean;
export type Admissionreceiptids = string[];
export type End = number;
export type Slicehash = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Start = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = SourceSpan[];
export type Fieldkey1 = string;
export type Id2 = string;
export type Manualscopeid = string | null;
export type Observationids = string[];
export type Origin = "model" | "source" | "human";
export type Rawinput = string;
export type Revision = number;
export type State = "admitted" | "human_raw" | "pending_manual" | "uncertain";
export type JsonValue = unknown;
export type Usercorrected = boolean;
export type Cells = ExtensionCell[];
export type Copyofrecordid = string | null;
export type Id3 = string;
export type Itemhandle2 = string;
export type Observationids1 = string[];
export type Active1 = boolean;
export type Id4 = string;
export type Kind1 = "owned_by" | "extension_of" | "related_to";
export type Revision1 = number;
export type Subjectid = string;
export type Targetid = string;
export type Relations = Relation[];
export type Revision2 = number;
export type Schemaversion3 = 1;
export type Semanticschemahash1 = string;
export type Semantictype1 = string;
export type Extensions = ExtensionRecord[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status1 = "complete" | "partial";
export type Code = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page1 = number | null;
export type Section = string;
export type Sourceid1 = string;
export type Unitid1 = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Actionid1 = string;
export type Blockids = string[];
export type Cellids1 = string[];
export type Id5 = string;
export type Rawinput1 = string;
export type Manualscopes = ManualEditScope[];
export type Mode1 = "structured" | "digest" | "imported";
export type Admission = "provisional" | "accepted" | "rejected" | "uncertain";
export type Evidence1 = SourceSpan[];
export type Fieldkey2 = string;
export type Id6 = string;
export type Itemhandle3 = string;
export type Ownerrelations = Relation[];
export type Proposalhash = string;
export type Rawinput2 = string;
export type Receiptids = string[];
export type Observations = Observation[];
export type Sourceid2 = string;
export type Sourcerevision1 = number;
export type Text2 = string;
export type Unitid2 = string;
export type Unitrevision1 = number;
export type Evidence2 = EvidenceSpan[];
export type Id7 = string;
export type Kind2 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision3 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected1 = boolean;
export type Value = string | null;
export type Origin1 = "source" | "user";
export type Revision4 = number;
export type Usercorrected2 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence3 = EvidenceSpan[];
export type Id8 = string;
export type Kind3 = "detail";
export type Label2 = string;
export type Origin2 = "source" | "user";
export type Revision5 = number;
export type Usercorrected3 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id9 = string;
export type Kind4 = "employment";
export type Origin3 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision6 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Evidence5 = EvidenceSpan[];
export type Id10 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision7 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected5 = boolean;
export type Value1 = boolean | null;
export type Revision8 = number;
export type Periods = WorkingPeriod[];
export type Revision9 = number;
export type Usercorrected6 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id11 = string;
export type Jobid1 = string;
export type Kind5 = "subproject";
export type Origin4 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision10 = number;
export type Usercorrected7 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id12 = string;
export type Jobid2 = string | null;
export type Kind6 = "technology";
export type Origin5 = "source" | "user";
export type Revision11 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected8 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id13 = string;
export type Kind7 = "education";
export type Origin6 = "source" | "user";
export type Revision12 = number;
export type Usercorrected9 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id14 = string;
export type Kind8 = "language";
export type Origin7 = "source" | "user";
export type Revision13 = number;
export type Usercorrected10 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id15 = string;
export type Kind9 = "certification";
export type Origin8 = "source" | "user";
export type Revision14 = number;
export type Usercorrected11 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id16 = string;
export type Jobid3 = string | null;
export type Kind10 = "claim";
export type Origin9 = "source" | "user";
export type Revision15 = number;
export type Subprojectid1 = string | null;
export type Usercorrected12 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id17 = string;
export type Jobid4 = string | null;
export type Kind11 = "metric";
export type Origin10 = "source" | "user";
export type Revision16 = number;
export type Subprojectid2 = string | null;
export type Usercorrected13 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision17 = number;
export type Status5 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
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
export type Evidence13 = EvidenceSpan[];
export type Id18 = string;
export type Jobid5 = string | null;
export type Kind12 = "leadership";
export type Origin11 = "source" | "user";
export type Revision18 = number;
export type Subprojectid3 = string | null;
export type Usercorrected15 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision19 = number;
export type Status6 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Action1 = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence14 = EvidenceSpan[];
export type Id19 = string;
export type Kind13 = "unresolved";
export type Origin12 = "source" | "user";
export type Revision20 = number;
export type Status7 = "unresolved" | "pending" | "conflict";
export type Usercorrected17 = boolean;
export type Records1 = (
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
export type Revision21 = number;
export type Schemaversion4 = 2;
export type Actionid2 = string;
export type Orderindex = number;
export type Recordid1 = string;
export type Revision22 = number;
export type Tombstones = RecordTombstone[];
export type Allowtextrewrite = boolean;
export type Category1 =
  ("identity" | "contacts" | "summary" | "experience" | "education" | "skills" | "languages" | "other") | null;
/**
 * @maxItems 1000
 */
export type Duplicateof = string[];
export type Id20 = string;
export type Kind14 = "paragraph" | "heading" | "section" | "bullet_list" | "duplicate" | "source_only";
export type Listitem = boolean;
export type Modelblock = boolean;
export type Reason = string | null;
export type Region2 = "header" | "sidebar" | "main";
/**
 * @maxItems 1000
 */
export type Sourcekeys = string[];
export type Text3 = string | null;
export type Title3 = string | null;
/**
 * @maxItems 5000
 */
export type Blocks3 = ImportBlock[];
export type Id21 = string;
export type Record = (ImportEmployment | ImportEducation | ImportTechnology | ImportLanguage) | null;
export type Employer = string;
export type Kind15 = "employment";
export type End1 = string;
export type Present = boolean;
export type Start1 = string;
/**
 * @maxItems 40
 */
export type Periods2 = ImportPeriod[];
export type Role = string;
export type Display = string;
export type Experience = string;
export type Technical1 = boolean | null;
/**
 * @maxItems 100
 */
export type Technologies = (string | ImportSkill)[];
export type Completion = string;
export type Institution = string;
export type Kind16 = "education";
export type Qualification = string;
export type Specialty = string;
export type Display1 = string;
export type Experience1 = string;
export type Kind17 = "technology";
export type Technical2 = boolean | null;
export type Kind18 = "language";
export type Language = string;
export type Level = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys1 = string[];
export type Text4 = string;
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
export type Title4 = string;
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
export type Actionid3 = string | null;
export type Fingerprint = string | null;
export type Id22 = string;
export type Kind19 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision23 = number;
export type Dependencies = DependencyStamp[];
export type Errorcode1 = string | null;
export type Id23 = string;
export type Kind20 =
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
export type Id24 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id25 = string;
export type Origin13 = "user";
export type Revision24 = number;
export type Text5 = string;
export type Unitid3 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision25 = number;
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id26 = string;
export type Column = number | null;
export type Index = number;
export type Kind21 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order1 = number;
export type Representedfactids = string[];
export type Revision26 = number;
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
export type Style4 = string | null;
export type Text6 = string;
export type Units = SourceUnit[];
export type Code1 = string;
export type Page2 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources = Source[];
export type Admittedat = string | null;
export type Discoveryattemptid = string;
export type Discoveryhash = string;
export type Itemhandle4 = string;
export type Key = string;
export type Operationid = string;
export type Recordid2 = string;
export type Semantictype2 = string;
export type Taskid = string;
export type Allocations = HandleAllocation[];
export type Authorizationid = string | null;
export type Evidencehash = string | null;
export type State1 = "pending" | "verified" | "unknown";
export type Witness = string | null;
export type Dispatchedat = string | null;
export type Errorcode2 = string | null;
export type Id27 = string;
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
export type Slot =
  "initial" | "review" | "primary_repair" | "fallback_repair" | "replacement_review" | "outline" | "outline_review";
export type State2 = "reserved" | "dispatch_started" | "returned" | "outcome_unknown" | "reconciled" | "released";
export type Taskid1 = string;
export type Cachedinputtokens = number | null;
export type Complete = boolean;
export type Inputtokens = number | null;
export type Outputtokens = number | null;
export type Attempts = ImportAttempt[];
export type Authorityhash = string;
export type Authorizedat = string;
export type Dependencyhash = string;
export type Id28 = string;
export type Kind22 = "start" | "resume";
export type State3 = "active" | "cancelled";
export type Authorizations = ImportAuthorization[];
export type Allowtextrewrite1 = boolean;
export type Authorityhash1 = string;
export type Dependencyhash1 = string;
export type Packagehash2 = string;
export type Callcap = number;
export type Cleanupseconds = 5;
export type Concurrency = number;
export type Fallbackrepairs = 1;
export type Finalizationseconds = number;
export type Primaryrepairs = 1;
export type Processingseconds = number;
export type Itemhandle5 = string;
export type Recordid3 = string;
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
export type Errorcode3 = string | null;
export type Factshash1 = string;
export type Id29 = string;
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
export type Id30 = string;
export type Issueshash = string;
export type Operationid2 = string;
export type Packagehash4 = string;
export type Sourcehash = string;
export type Startedat1 = string;
export type Finalizationhistory = FinalizationCandidate[];
export type Id31 = string;
export type Inferenceclosed = boolean;
export type Blockids1 = string[];
export type Category2 = "content_violation" | "uncertain_interpretation" | "check_not_completed";
export type Code2 = string;
export type Id32 = string;
export type Importedfingerprint = string;
export type Lifecycleid = string;
export type Message = string;
export type Retiredbyaction = string | null;
export type Reviewinputhash = string | null;
export type Ruleid = string | null;
export type State5 = "active" | "retired";
export type Targetids = string[];
export type Taskid2 = string;
export type Issues1 = ImportIssue[];
export type Lastobservedat = string | null;
export type Projectid1 = string;
export type Admittedcellids = string[];
export type Admittedrelationids = string[];
export type Appliedreceiptid = string | null;
export type Attemptid1 = string;
export type Fieldkey3 = string;
export type Pointer = string;
export type Text7 = string;
export type Droppedvalues = DroppedValue[];
export type Errors = string[];
export type Id33 = string;
export type Inputhash1 = string;
export type Attemptid2 = string;
export type Children = string[];
export type Kind23 = "add" | "split" | "merge";
export type Parents = string[];
export type Lineage = Lineage1[];
export type Proposalhash1 = string;
export type Rawreturn1 = string;
export type Rawreturnhash1 = string;
export type Key1 = string;
export type Pointer1 = string;
export type Semantictype4 = string;
export type Discoveries = Discovery[];
export type Effectivecellids = string[];
export type Evidence15 = SourceSpan[];
export type Fieldkey4 = string;
export type Item = DiscoverySelector | HandleSelector;
export type Key2 = string;
export type Kind24 = "discovery_key";
export type Itemhandle6 = string;
export type Kind25 = "handle";
export type Pointer2 = string;
export type Fields1 = ProposalField[];
export type Children1 = string[];
export type Kind26 = "add" | "split" | "merge";
export type Parents1 = string[];
export type Lineage2 = ProposalLineage[];
export type Evidence16 = SourceSpan[];
export type Kind27 = "owned_by" | "extension_of" | "related_to";
export type Relation1 = RelationDiscoverySelector | ExistingRelationSelector;
export type Key3 = string;
export type Kind28 = "discovery_key";
export type Kind29 = "relation_id";
export type Relationid = string;
export type Subject = DiscoverySelector | HandleSelector;
export type Target = DiscoverySelector | HandleSelector;
export type Relations2 = ProposalRelation[];
export type Schemaversion5 = 1;
export type Effectivecellids1 = string[];
export type Evidence17 = SourceSpan[];
export type Fieldkey5 = string;
export type Itemhandle7 = string;
export type Pointer3 = string;
export type Resolvedfields = FieldSidecar[];
export type Resolvedrelations = Relation[];
export type State6 = "invalid" | "provisional" | "accepted" | "rejected";
export type Proposals = ProposalRecord[];
export type Errorcode4 = string | null;
export type Intentid = string | null;
export type State7 = "pending" | "saved" | "failed_before_replacement" | "outcome_unknown" | "cancelled";
export type Workspacehash = string | null;
export type Attemptid3 = string;
export type Completedat = string;
export type Ruleid1 = string;
export type Targetid1 = string;
export type Expectedchecks = CheckTarget[];
export type Id34 = string;
export type Actionable = boolean;
export type Disposition1 = "satisfied" | "violation" | "uncertain";
export type Evidence18 = SourceSpan[];
export type Reason1 = string;
export type Ruleid2 = string;
export type Targetid2 = string;
export type Results = ReviewDisposition[];
export type Reviewinputhash1 = string;
export type Receipts1 = ReviewReceipt[];
export type Discoveryattemptid1 = string;
export type Key4 = string;
export type Kind30 = "owned_by" | "extension_of" | "related_to";
export type Operationid3 = string;
export type Relationid1 = string;
export type Subjectid1 = string;
export type Targetid3 = string;
export type Taskid3 = string;
export type Relationallocations = RelationAllocation[];
export type Attemptid4 = string;
export type Id35 = string;
export type Inputhash2 = string;
export type Allowtextrewrite2 = boolean;
export type Effectivecells = ExtensionCell[];
export type Ref = string;
export type Text8 = string;
export type Evidence19 = EvidenceOption[];
export type Handlemap = (HandleAllocation | CapturedItemIdentity)[];
export type Occurrenceindependent = boolean;
export type Packagehash5 = string;
export type Proposalhash2 = string;
export type Protocol = "template_import_v1";
export type Relations3 = Relation[];
export type Id36 = string;
export type Kind31 =
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
export type Schemaversion6 = 1 | 2;
export type Actionable1 = boolean;
export type Disposition2 = "satisfied" | "violation" | "uncertain";
export type Evidence20 = SourceSpan[];
export type Origin14 = "verbatim" | "reused";
export type Reason2 = string;
export type Ruleid3 = string;
export type Targetid4 = string;
export type Settled = SettledCheck[];
export type Sourcespans = SourceSpan[];
export type Targets = CheckTarget[];
export type Reviewinputs = ReviewInputRecord[];
export type Schemaversion7 = 1;
export type State8 =
  "captured" | "processing" | "cleanup_pending" | "finalizing" | "published" | "cancelled" | "failed" | "fenced";
export type Capturedat = string;
export type Id37 = string;
export type Inputhash3 = string;
export type Taskid4 = string;
export type Taskinputs = TaskInputRecord[];
export type Disposition3 = "admitted" | "derived" | "source_fallback" | "empty";
export type Id38 = string;
export type Inputhash4 = string;
export type Issueids = string[];
export type Itemhandles = string[];
export type Sourcespans1 = SourceSpan[];
export type Taskid5 = string;
export type Taskresults = TaskResultRecord[];
export type Allowedhandles = string[];
export type Attemptids = string[];
export type Blockid1 = string;
export type Dependencies1 = string[];
export type Index1 = number;
export type Origin15 = "outline" | "review";
/**
 * @minItems 1
 */
export type Parts = [EntryPart, ...EntryPart[]];
export type Spans = SourceSpan[];
export type Title5 = string;
export type Spans1 = SourceSpan[];
export type Title6 = string;
export type Expectedchecks1 = CheckTarget[];
export type Id39 = string;
export type Inputhash5 = string;
export type Issueids1 = string[];
export type Kind32 = "extract" | "rewrite" | "derive" | "source_copy" | "outline_review";
export type Operationid4 = string;
export type Parenttaskid = string | null;
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
export type Id40 = string;
export type Mimetype1 = string;
export type Path = string;
export type Role1 = "font" | "logo" | "icon" | "catalog";
export type Sha256 = string;
export type Size3 = number;
export type Assets = StoredAsset[];
export type Dependencyorder = number;
export type Id41 = string;
export type Serveronly = string[];
export type Blocks4 = CompiledBlock[];
export type Compilerversion = string;
export type Confighash = string;
export type Embedding = "allowed" | "not_applicable";
export type Id42 = string;
export type MimeType = string;
export type Path1 = string;
export type Role2 = "font" | "logo" | "icon" | "catalog";
export type Assets1 = AssetDeclaration[];
export type Field1 = string;
export type ItemPointer = string | null;
export type Pointer4 = string;
export type Kind33 = "owned_by" | "extension_of" | "related_to";
export type SubjectPointer = string;
export type SemanticType = string;
export type Bindings = Binding[];
export type Checks = Check[];
export type DependsOn = string[];
export type Effort1 = ("low" | "medium" | "high") | null;
export type Extract = string[];
export type Id43 = string;
export type Mode2 = "model" | "derived" | "source_copy";
export type Operation = string | null;
/**
 * Outline the list first, then extract its entries in parallel groups. A model list without item limits only.
 */
export type PerEntry = boolean;
export type Fields3 = string[];
export type Instructions1 = string[];
export type Id44 = string;
export type Kind34 = "source" | "fact_type" | "block" | "operation";
export type Selectors = InputRef[];
export type Equals = string;
export type Operation1 = string;
export type Blocks5 = Block[];
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
export type Id45 = string;
export type Kind35 = "owned_by" | "extension_of" | "related_to";
export type TargetTypes = string[];
export type Relations4 = RelationDeclaration[];
export type SchemaVersion = string;
export type FactTypes = FactType[];
export type Extract1 = string[];
export type Permission = "allowTextRewrite";
export type Rewrite1 = string[];
export type DependsOn1 = string[];
export type Id46 = string;
export type Inputs = InputRef[];
export type Kind36 = "partition_employment";
export type Compact = string;
export type Detailed = string;
export type Years = number;
export type Version2 = 1;
export type DependsOn2 = string[];
export type Id47 = string;
export type Inputs1 = InputRef[];
export type Kind37 = "select_role_branch";
export type Field3 = string;
export type SemanticType1 = string;
export type Matched = string;
export type Otherwise = string;
export type RoleFamilies = string[];
export type Version3 = 1;
export type DependsOn3 = string[];
export type Id48 = string;
export type Inputs2 = InputRef[];
export type Kind38 = "assign_skills";
export type Groups = string[];
export type UncertainGroup = string;
export type Version4 = 1;
export type DependsOn4 = string[];
export type Id49 = string;
export type Inputs3 = InputRef[];
export type Kind39 = "format_period";
export type Separator1 = string;
export type Version5 = 1;
export type DependsOn5 = string[];
export type Id50 = string;
export type Inputs4 = InputRef[];
export type Kind40 = "preserve_stated_text";
export type Version6 = 1;
export type Operations1 = (
  PartitionOperation | RoleOperation | SkillsOperation | PeriodOperation | PreserveOperation
)[];
export type SchemaVersion1 = 3;
export type RetainOriginal = true;
export type RetainUnmappedFacts = true;
export type DefaultLocale = string;
export type Id51 = string;
export type Name1 = string;
export type Revision27 = string;
export type Id52 = string;
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
export type Revision28 = string;
export type Schemaversion8 = 1;
export type Warnings1 = string[];
export type Height3 = number;
export type Id53 = string;
export type Mimetype2 = "image/png" | "image/jpeg";
export type Path2 = string;
export type Sha2561 = string;
export type Size4 = number;
export type Width4 = number;
export type Assets2 = LocalImageAsset[];
export type Createdat1 = string;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Regions1 = [TemplateRegion, TemplateRegion, TemplateRegion];
export type Children13 = (
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
export type Citations = SourceSpan[];
export type Backgroundcolor = string;
export type Bold3 = boolean;
export type Code3 = boolean;
export type Italic2 = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text9 = string;
export type Type1 = "text";
export type Content1 = PresentedText[];
export type Href = string;
export type Type2 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Cellid1 = string | null;
export type Citations1 = SourceSpan[];
export type Complete1 = boolean;
export type Fieldkey6 = string;
export type Occurrenceid = string;
export type Recordid4 = string;
export type Syncedfactrevision = number;
export type Text10 = string;
export type Type3 = "fact_field";
export type Content2 = (PresentedText | FieldOccurrence)[];
export type Href1 = string;
export type Cellid2 = string;
export type Fieldkey7 = string;
export type Occurrenceid1 = string;
export type Recordid5 = string;
export type Type4 = "bound_link";
export type Citations2 = SourceSpan[];
export type Fragmentid = string;
export type Occurrenceid2 = string;
export type Scopeid = string;
export type Text11 = string;
export type Type5 = "manual_scope";
export type Content = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id54 = string;
export type Alignment2 = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Manualorder = boolean;
export type Presentation = "standard" | "focus";
export type Recordid6 = string | null;
export type Textcolor1 = string;
export type Evidence21 = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id55 = string;
export type Kind41 = "citation";
export type Recordid7 = string;
export type Fieldkey8 = string;
export type Id56 = string;
export type Kind42 = "field_binding";
export type Recordid8 = string;
export type Id57 = string;
export type Kind43 = "working_owner";
export type Recordid9 = string;
/**
 * @minItems 1
 */
export type Evidence22 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id58 = string;
export type Kind44 = "source";
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision29 = number;
export type Type6 = "section";
export type Children12 = (
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
export type Id59 = string;
export type Alignment3 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Height4 = number;
export type Width5 = number;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision30 = number;
export type Type7 = "image";
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
/**
 * @minItems 1
 */
export type Columnwidths = [number | null, ...(number | null)[]];
export type Headercols = number;
export type Headerrows = number;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor2 = string;
export type Colspan = number;
export type Content4 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id60 = string;
export type Revision31 = number;
export type Rowspan = number;
export type Cells1 = TemplateTableCell[];
export type Id61 = string;
export type Rows = TemplateTableRow[];
export type Id62 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision32 = number;
export type Type8 = "table";
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
export type Content5 = null;
export type Id63 = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision33 = number;
export type Type9 = "divider";
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
export type Content6 = string;
export type Id64 = string;
export type Backgroundcolor4 = string;
export type Language1 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision34 = number;
export type Type10 = "code";
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
export type Content7 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id65 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision35 = number;
export type Type11 = "quote";
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
export type Content8 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id66 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision36 = number;
export type Type12 = "toggle_list";
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
export type Content9 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id67 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision37 = number;
export type Type13 = "check_list";
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
export type Content10 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id68 = string;
export type Alignment7 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start2 = number | null;
export type Textcolor4 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision38 = number;
export type Type14 = "numbered_list";
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
export type Content11 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id69 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision39 = number;
export type Type15 = "bullet_list";
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
export type Content12 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id70 = string;
export type Alignment8 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level1 = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision40 = number;
export type Type16 = "heading";
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
export type Content13 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id71 = string;
export type Provenance12 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision41 = number;
export type Type17 = "paragraph";
export type Blocks6 = (
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
export type Id72 = string;
export type Revision42 = number;
export type Role3 = "header" | "sidebar" | "main";
export type Revision43 = number;
export type Schemaversion9 = 2;
export type Evidence23 = EvidenceSpan[];
export type Id73 = string;
export type Rawtext5 = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Attemptid5 = string;
export type Id74 = string;
export type Path3 = string;
export type Sha2562 = string;
export type Size5 = number;
export type Assets3 = TemplateRenderAsset[];
export type Documenthash3 = string;
export type Factshash3 = string;
export type Packagehash7 = string;
export type Presentationhash2 = string;
export type Renderinputversion1 = 1;
export type Id75 = string;
export type Sha2563 = string;
export type Version7 = string;
export type Schemaversion10 = 1;
export type Exportinputs = TemplateExportCapture[];
export type Exports = ExportAttempt[];
export type Blockids2 = string[];
export type Disposition4 = "accepted" | "fallback" | "source_only" | "multiple_views";
export type Itemhandle8 = string | null;
export type Reason3 = string | null;
export type Importcoverage = SpanCoverage[];
export type Operationid5 = string;
export type Sha2564 = string;
export type Importhistory = ImportHistoryRef[];
export type Importissues = ImportIssue[];
export type Operations2 = RichOperation[];
export type Projectid2 = string;
export type Documentrevision3 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id76 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision44 = number;
export type Schemaversion11 = 6;
export type Sources1 = Source[];
export type Templateoperations1 = ImportOperation[];
export type Projectid3 = string;
export type Projectrevision1 = number;
export type Markdown = string;
export type Revision45 = number;
export type Sha2565 = string;
export type Schemaversion12 = 7;
export type Actionid4 = string;
export type Blockids3 = string[];
export type Actionid5 = string;
export type Actiontoken = number;
export type Dependencies2 = DependencyStamp[];
export type Sessionid = string;
export type Dependencies3 = DependencyStamp[];
export type Errorcode5 = string | null;
export type Factids = string[];
export type Fieldkeys1 = string[];
export type Id77 = string;
export type Instruction = string | null;
export type Kind45 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Lifecycleid1 = string;
export type Beforeownerid = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Movedoccurrenceids = [string, ...string[]];
export type Proposedownerid = string;
export type Recordid10 = string;
export type Relationid2 = string | null;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Remainingoccurrenceids = [string, ...string[]];
export type Afterid1 = string | null;
export type Beforerevision = number | null;
export type Block1 =
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
export type Keepchildren = boolean;
export type Kind46 = "put_block";
export type Parentid1 = string;
export type Beforerevision1 = number;
export type Blockid2 = string;
export type Kind47 = "remove_block";
export type Afterid2 = string | null;
export type Beforerevision2 = number;
export type Blockid3 = string;
export type Kind48 = "move_block";
export type Parentid2 = string;
export type Beforerevision3 = number;
export type Blockid4 = string;
export type Cellid3 = string | null;
export type Content14 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End2 = number;
export type Field4 = "content" | "caption";
export type Flankbindings = FlankBinding[] | null;
export type Fragmentid1 = string;
export type Role4 = "prefix" | "suffix";
export type Source1 = FieldFlankSource | ManualScopeFlankSource;
export type Bindingid1 = string;
export type Kind49 = "field";
export type Fragmentid2 = string;
export type Kind50 = "manual_scope";
export type Sourceend = number;
export type Sourcestart = number;
export type Kind51 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start3 = number;
export type Beforerevision4 = number | null;
export type Kind52 = "put_record";
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
export type Kind53 = "remove_record";
export type Recordid11 = string;
export type Beforerevision6 = number | null;
export type Kind54 = "put_extension";
export type Beforerevision7 = number;
export type Kind55 = "remove_extension";
export type Recordid12 = string;
export type Beforerevision8 = number | null;
export type Kind56 = "put_relation";
export type Beforerevision9 = number;
export type Kind57 = "remove_relation";
export type Relationid3 = string;
export type Kind58 = "put_manual_scope";
export type Afterscopeid = string | null;
export type Beforescopeid = string | null;
export type Cellid4 = string;
export type Kind59 = "set_builtin_manual_scope";
export type Actionid6 = string;
export type Afterlifecycleid = string;
export type Afterstate = "active" | "retired";
export type Beforelifecycleid = string;
export type Beforestate = "active" | "retired";
export type Importedfingerprint1 = string;
export type Issueid = string;
export type Kind60 = "set_issue_state";
export type Afterblockids = string[];
export type Beforeblockids = string[];
export type Kind61 = "set_authored_anchors";
export type Target1 = IssueAnchorTarget | CoverageAnchorTarget;
export type Beforelifecycleid1 = string;
export type Beforestate1 = "active" | "retired";
export type Importedfingerprint2 = string;
export type Issueid1 = string;
export type Kind62 = "issue";
export type Coverageidentityhash = string;
export type Coverageindex = number;
export type Coveragesequencehash = string;
export type Kind63 = "coverage";
export type Aftersemantichash = string;
export type Beforerevision10 = number;
export type Beforesemantichash = string;
export type Blockid5 = string;
export type Kind64 = "restore_authored_block_patch";
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Patch = [
  PatchSet | PatchInsert | PatchRemove | PatchSpliceText,
  ...(PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[]
];
export type Kind65 = "set";
export type Pointer5 = string;
export type Valuewire = string;
export type Kind66 = "insert";
export type Pointer6 = string;
export type Valuewire1 = string;
export type Kind67 = "remove";
export type Pointer7 = string;
export type Beforetexthash = string;
export type End3 = number;
export type Kind68 = "splice_text";
export type Pointer8 = string;
export type Start4 = number;
export type Text12 = string;
export type Blockid6 = string;
export type Cellid5 = string | null;
export type Field5 = "content" | "caption";
export type Inlineindex = number;
export type After = ScopeDisplayBinding | LiteralDisplayBinding;
export type Fragmentid3 = string;
export type Kind69 = "manual_scope";
export type Occurrenceid3 = string;
export type Scopeid1 = string;
export type Kind70 = "literal";
export type Beforehash = string;
/**
 * @maxItems 1000
 */
export type Assignments = ScopeDisplayAssignment[];
export type Kind71 = "set_manual_scope_displays";
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
export type Blockid7 = string;
export type Cellid6 = string | null;
export type Field6 = "content" | "caption";
export type Fragmenthash = string;
export type Fragmentid4 = string;
export type Occurrenceid4 = string;
export type Scopehash = string;
export type Scopeid2 = string;
/**
 * @maxItems 1000
 */
export type Sources2 = ScopeDisplaySource[];
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
export type Schemaversion13 = 2;
export type Blockid8 = string;
export type Cellid7 = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids4 = [string, ...string[]];
export type Kind72 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Status9 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Actionid7 = string;
export type Blockids5 = string[];
export type Dependencies4 = DependencyStamp[];
export type Errorcode6 = string | null;
export type Factids1 = string[];
export type Fieldkeys2 = string[];
export type Id78 = string;
export type Instruction1 = string | null;
export type Kind73 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Afterid3 = string | null;
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
export type Text13 = string;
export type Type18 = "text";
export type Content16 = StyledText[];
export type Href2 = string;
export type Type19 = "link";
export type Bindingid2 = string;
export type Bindingrootid1 = string | null;
export type Fieldkey9 = string;
export type Recordid13 = string;
export type Syncedfactrevision1 = number;
export type Text14 = string;
export type Type20 = "fact_field";
export type Content15 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id79 = string;
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
export type Id80 = string;
export type Alignment9 = "left" | "center" | "right";
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
export type Alignment10 = "left" | "center" | "right" | "justify";
export type Backgroundcolor8 = string;
export type Colspan1 = number;
export type Content18 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id81 = string;
export type Revision48 = number;
export type Rowspan1 = number;
export type Cells2 = TableCell[];
export type Id82 = string;
export type Id83 = string;
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
export type Id84 = string;
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
export type Id85 = string;
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
export type Id86 = string;
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
export type Id87 = string;
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
export type Id88 = string;
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
export type Id89 = string;
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
export type Id90 = string;
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
export type Id91 = string;
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
export type Id92 = string;
export type Provenance24 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision58 = number;
export type Type32 = "paragraph";
export type Keepchildren1 = boolean;
export type Kind74 = "put_block";
export type Parentid3 = string;
export type Beforerevision12 = number;
export type Blockid9 = string;
export type Cellid8 = string | null;
export type Content28 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End4 = number;
export type Field7 = "content" | "caption";
export type Kind75 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start5 = number;
/**
 * @maxItems 1000
 */
export type Proposedsteps1 = (PutBlock | RemoveBlock | MoveBlock | ReplaceInlineRange | PutRecord | RemoveRecord)[];
export type Ready1 = boolean;
export type Rewriteresult1 = string | null;
export type Rewritesource1 = string | null;
export type Status10 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Syncrecords = (TemplateSyncRecord | RichSyncRecord)[];
export type Title7 = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;
export type Blockids6 = string[];
export type Code4 = string;
export type Count = number;
export type Sourceid3 = string;
export type Sourcerevision2 = number;
export type Unitid4 = string;
export type Unitrevision2 = number;
export type Evidence24 = Evidence25[];
export type Id93 = string;
export type Page3 = number | null;
export type Sourceid4 = string;
export type Locations = WarningLocation[];
export type Recordids = string[];
export type Warnings2 = RichWarning[];
export type Revision59 = number;
export type Schemaversion14 = 1;
export type Appliedrevision = number | null;
export type Baserevision = number;
export type Conversationid = string;
export type Createdat2 = string;
export type Expectedactionid = string | null;
export type Id94 = string;
export type Kind76 = "edit" | "history" | "action";
export type Blockid10 = string;
export type Cellid9 = string | null;
export type Field8 = "content" | "caption";
export type Op = "set_block_text";
export type Text15 = string;
export type Blockid11 = string;
export type Cellid10 = string | null;
export type Field9 = "content" | "caption";
export type Find = string;
export type Op1 = "replace_text";
export type Replace = string;
export type Afterblockid = string | null;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Blocks7 =
  | [NewBlock]
  | [NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ];
export type Kind77 = "paragraph" | "heading" | "bullet" | "numbered";
export type Level2 = 1 | 2 | 3;
export type Text16 = string;
export type Op2 = "insert_blocks";
export type Parentid4 = string | null;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Blockids7 = [string, ...string[]];
export type Op3 = "delete_blocks";
export type Afterblockid1 = string | null;
export type Blockid12 = string;
export type Op4 = "move_block";
export type Parentid5 = string | null;
export type Alignment11 = ("left" | "center" | "right" | "justify") | null;
export type Backgroundcolor9 = string | null;
export type Blockid13 = string;
export type Kind78 = ("paragraph" | "heading" | "bullet" | "numbered") | null;
export type Level3 = (1 | 2 | 3) | null;
export type Op5 = "format_block";
export type Textcolor6 = string | null;
export type Field10 = string;
export type Op6 = "update_fact";
export type Recordid14 = string;
export type Value3 = string;
export type Jobid6 = string | null;
export type Kind79 = "candidate" | "employment" | "technology" | "education" | "language" | "claim" | "period";
export type Op7 = "create_fact";
export type Op8 = "delete_fact";
export type Recordid15 = string;
export type Direction = "undo" | "redo";
export type Op9 = "history";
export type Action2 = "rename" | "formatting_date" | "archive" | "restore" | "delete";
export type Op10 = "action";
export type Targetid5 = string | null;
export type Value4 = string | null;
/**
 * @maxItems 100
 */
export type Ops = (
  | SetBlockTextOp
  | ReplaceTextOp
  | InsertBlocksOp
  | DeleteBlocksOp
  | MoveBlockOp
  | FormatBlockOp
  | UpdateFactOp
  | CreateFactOp
  | DeleteFactOp
  | HistoryOp
  | ActionOp
)[];
export type After1 = string;
export type Before = string;
export type Label3 = string;
export type Target2 = string;
/**
 * @maxItems 200
 */
export type Preview = PreviewEntryV1[];
export type Projectid4 = string;
export type Runid1 = string;
export type Schemaversion15 = 1;
export type State10 = "draft" | "applied" | "discarded";
export type Summary = string;
export type Updatedat1 = string;

export interface AssistantApplyResultV1 {
  action: AssistantActionResultV1 | null;
  edit: EditResultV1 | null;
  proposal: AssistantChangeProposalV1;
}
export interface AssistantActionResultV1 {
  action: Action;
  archived: Archived;
  deleted: Deleted;
  title: Title;
}
export interface EditResultV1 {
  changedBlockIds: Changedblockids;
  clientMutationId: Clientmutationid;
  createdBlocks: Createdblocks;
  createdIds: Createdids;
  documentRevision: Documentrevision;
  history: HistoryStateV1;
  replayed: Replayed;
  response: TemplateProjectResponseV1;
  revision: Revision59;
  schemaVersion: Schemaversion14;
}
export interface Createdblocks {
  [k: string]: string[];
}
export interface Createdids {
  [k: string]: {
    [k: string]: string;
  };
}
export interface HistoryStateV1 {
  redo: HistoryActionV1 | null;
  undo: HistoryActionV1 | null;
}
export interface HistoryActionV1 {
  actionId: Actionid;
  kind: Kind;
}
export interface TemplateProjectResponseV1 {
  durability: Durability;
  generation: RichGenerationState | null;
  identity: ResumeIdentity | null;
  presentation: TemplatePresentationV1 | null;
  saveError: Saveerror;
  savedDocumentRevision: Saveddocumentrevision;
  savedProjectRevision: Savedprojectrevision;
  schemaVersion: Schemaversion2;
  snapshot: TemplateSnapshotIdentity | null;
  workspace: WorkspaceV7;
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
  title: Title1;
}
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
  focusPanel?: EditorFocusPanel | null;
  fonts: Fonts;
  iconFiles?: Iconfiles;
  icons: Icons;
  styles: Styles;
  technologyTargets?: Technologytargets;
}
export interface Blocks1 {
  [k: string]: EditorBlock;
}
export interface EditorBlock {
  band?: Band;
  chips?: Chips;
  focus?: EditorFocus | null;
  inline?: Inline;
  links?: Links;
  style: Style;
}
export interface Chips {
  [k: string]: string;
}
export interface EditorFocus {
  blocks: Blocks2;
  icon: Icon;
}
export interface Inline {
  [k: string]: string;
}
/**
 * The facts panel can add, remove and move Focus rows and set their years.
 */
export interface EditorFocusPanel {
  records: Records;
}
export interface Iconfiles {
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
/**
 * Where the facts panel adds a technology: a line of one scope, a job section that has none yet, or a group view
 * the document no longer shows (block id view:<view id>).
 */
export interface EditorTechnologyTarget {
  blockId: Blockid;
  jobId: Jobid;
  label: Label;
  placement: EditorPlacement;
}
/**
 * A block's parent block or region and the sibling before it, as a panel placement context names them.
 */
export interface EditorPlacement {
  afterId: Afterid;
  parentId: Parentid;
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
  id: Id1;
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
  title: Title2;
}
export interface ViewNode {
  background?: Background1;
  detail_style?: DetailStyle;
  experience_field?: ExperienceField;
  field?: Field;
  fields?: Fields;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label1;
  name_field?: NameField;
  prefix?: Prefix;
  separator?: Separator;
  style: Style3;
  type: Type;
  url_field?: UrlField;
}
export interface Label1 {
  [k: string]: string;
}
export interface Prefix {
  [k: string]: string;
}
export interface Title2 {
  [k: string]: string;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision1;
  factsHash: Factshash;
  packageHash: Packagehash1;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
export interface WorkspaceV7 {
  createdAt: Createdat;
  documentRevision: Documentrevision2;
  formattingAsOf: PartialDate;
  mutationReplay: Mutationreplay;
  preDraft: RichPreDraftV2 | null;
  project: ProjectV6 | null;
  projectId: Projectid3;
  projectRevision: Projectrevision1;
  rulesUsed: Rules1 | null;
  schemaVersion: Schemaversion12;
  sourceObservedAt: PartialDate | null;
  syncRecords: Syncrecords;
  title: Title7;
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
  clientMutationId: Clientmutationid1;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface RichPreDraftV2 {
  facts: WorkingFactsV2;
  importDraft?: ImportDraft | null;
  operations: Operations;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources;
  templateOperations: Templateoperations;
  templatePackage: StoredTemplatePackage | null;
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
  records: Records1;
  relations: Relations1;
  revision: Revision21;
  schemaVersion: Schemaversion4;
  tombstones: Tombstones;
}
export interface BuiltinItemIdentity {
  canonicalFields?: Canonicalfields;
  cellIds: Cellids;
  itemHandle: Itemhandle1;
  periodIds?: Periodids;
  recordId: Recordid;
  semanticSchemaHash: Semanticschemahash;
  semanticType: Semantictype;
}
export interface Canonicalfields {
  [k: string]: CanonicalFieldBinding;
}
export interface CanonicalFieldBinding {
  cellId: Cellid;
  fieldKey: Fieldkey;
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
  cells: Cells;
  copyOfRecordId?: Copyofrecordid;
  id: Id3;
  itemHandle: Itemhandle2;
  observationIds: Observationids1;
  relations: Relations;
  retiredCellIds?: Retiredcellids;
  revision: Revision2;
  schemaVersion: Schemaversion3;
  semanticSchemaHash: Semanticschemahash1;
  semanticType: Semantictype1;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence;
  fieldKey: Fieldkey1;
  id: Id2;
  manualScopeId: Manualscopeid;
  observationIds: Observationids;
  origin: Origin;
  rawInput: Rawinput;
  revision: Revision;
  state: State;
  typedValue: JsonValue;
  userCorrected: Usercorrected;
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
export interface Relation {
  active: Active1;
  id: Id4;
  kind: Kind1;
  revision: Revision1;
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
  status: Status1;
  unresolved: Unresolved;
}
export interface Counts {
  [k: string]: number;
}
export interface ExtractionIssue {
  code: Code;
  page?: Page1;
  section: Section;
  sourceId: Sourceid1;
  unitId: Unitid1;
}
export interface ManualEditScope {
  actionId: Actionid1;
  blockIds: Blockids;
  cellIds: Cellids1;
  id: Id5;
  rawInput: Rawinput1;
}
export interface Observation {
  admission: Admission;
  evidence: Evidence1;
  fieldKey: Fieldkey2;
  id: Id6;
  itemHandle: Itemhandle3;
  ownerRelations: Ownerrelations;
  proposalHash: Proposalhash;
  rawInput: Rawinput2;
  receiptIds: Receiptids;
  typedValue: JsonValue;
}
export interface CandidateRecord {
  evidence: Evidence2;
  id: Id7;
  kind: Kind2;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin1;
  revision: Revision4;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected2;
}
export interface EvidenceSpan {
  sourceId: Sourceid2;
  sourceRevision: Sourcerevision1;
  text: Text2;
  unitId: Unitid2;
  unitRevision: Unitrevision1;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision3;
  status: Status2;
  userCorrected?: Usercorrected1;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence3;
  id: Id8;
  kind: Kind3;
  label: Label2;
  origin: Origin2;
  revision: Revision5;
  userCorrected?: Usercorrected3;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence4;
  id: Id9;
  kind: Kind4;
  origin: Origin3;
  periods: Periods;
  revision: Revision9;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence5;
  id: Id10;
  present: WorkingFieldBool;
  revision: Revision8;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision6;
  status: Status3;
  userCorrected?: Usercorrected4;
  value: PartialDate | null;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision7;
  status: Status4;
  userCorrected?: Usercorrected5;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence6;
  id: Id11;
  jobId: Jobid1;
  kind: Kind5;
  name: WorkingFieldStr;
  origin: Origin4;
  periods: Periods1;
  revision: Revision10;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected7;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence7;
  experience?: WorkingFieldStr;
  id: Id12;
  jobId: Jobid2;
  kind: Kind6;
  origin: Origin5;
  revision: Revision11;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected8;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id13;
  institution: WorkingFieldStr;
  kind: Kind7;
  origin: Origin6;
  qualification: WorkingFieldStr;
  revision: Revision12;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected9;
}
export interface LanguageRecord {
  evidence: Evidence9;
  id: Id14;
  kind: Kind8;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin7;
  revision: Revision13;
  userCorrected?: Usercorrected10;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence10;
  id: Id15;
  issuer: WorkingFieldStr;
  kind: Kind9;
  name: WorkingFieldStr;
  origin: Origin8;
  revision: Revision14;
  userCorrected?: Usercorrected11;
}
export interface ClaimRecord {
  evidence: Evidence11;
  id: Id16;
  jobId: Jobid3;
  kind: Kind10;
  origin: Origin9;
  revision: Revision15;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected12;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence12;
  id: Id17;
  jobId: Jobid4;
  kind: Kind11;
  origin: Origin10;
  revision: Revision16;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected13;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision17;
  status: Status5;
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
  evidence: Evidence13;
  id: Id18;
  jobId: Jobid5;
  kind: Kind12;
  origin: Origin11;
  revision: Revision18;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected15;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision19;
  status: Status6;
  userCorrected?: Usercorrected16;
  value: LeadershipValue | null;
}
export interface LeadershipValue {
  action: Action1;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface UnresolvedRecord {
  category: Category;
  evidence: Evidence14;
  id: Id19;
  kind: Kind13;
  origin: Origin12;
  revision: Revision20;
  status: Status7;
  userCorrected?: Usercorrected17;
}
export interface RecordTombstone {
  actionId: Actionid2;
  orderIndex: Orderindex;
  recordId: Recordid1;
  revision: Revision22;
}
export interface ImportDraft {
  allowTextRewrite?: Allowtextrewrite;
  blocks?: Blocks3;
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
  id: Id20;
  kind?: Kind14;
  listItem?: Listitem;
  modelBlock?: Modelblock;
  reason?: Reason;
  region?: Region2;
  sourceKeys?: Sourcekeys;
  text?: Text3;
  title?: Title3;
}
export interface ImportFact {
  id: Id21;
  record?: Record;
  sourceKeys?: Sourcekeys1;
  text?: Text4;
}
export interface ImportEmployment {
  employer?: Employer;
  kind: Kind15;
  periods?: Periods2;
  role?: Role;
  technologies?: Technologies;
}
export interface ImportPeriod {
  end?: End1;
  present?: Present;
  start?: Start1;
}
export interface ImportSkill {
  display: Display;
  experience?: Experience;
  technical?: Technical1;
}
export interface ImportEducation {
  completion?: Completion;
  institution?: Institution;
  kind: Kind16;
  qualification?: Qualification;
  specialty?: Specialty;
}
export interface ImportTechnology {
  display: Display1;
  experience?: Experience1;
  kind: Kind17;
  technical?: Technical2;
}
export interface ImportLanguage {
  kind: Kind18;
  language?: Language;
  level?: Level;
}
export interface ImportProfile {
  location?: Location;
  name?: Name;
  sourceKeys?: Sourcekeys2;
  title?: Title4;
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
  actionId: Actionid3;
  dependencies: Dependencies;
  errorCode: Errorcode1;
  id: Id23;
  kind: Kind20;
  status: Status8;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id22;
  kind: Kind19;
  revision: Revision23;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id24;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision25;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id25;
  origin: Origin13;
  revision: Revision24;
  text: Text5;
  unitId: Unitid3;
}
export interface SourceUnit {
  disposition: Disposition;
  id: Id26;
  location: SourceLocation;
  order: Order1;
  representedFactIds: Representedfactids;
  revision: Revision26;
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
  style?: Style4;
}
export interface SourceWarning {
  code: Code1;
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
  id: Id31;
  inferenceClosed?: Inferenceclosed;
  issues?: Issues1;
  lastObservedAt: Lastobservedat;
  projectId: Projectid1;
  proposals: Proposals;
  publication: PublicationOutcome;
  receipts: Receipts1;
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
  itemHandle: Itemhandle4;
  key: Key;
  operationId: Operationid;
  periodIds?: Periodids1;
  recordId: Recordid2;
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
  errorCode?: Errorcode2;
  id: Id27;
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
  complete: Complete;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
}
export interface ImportAuthorization {
  authorityHash: Authorityhash;
  authorizedAt: Authorizedat;
  dependencyHash: Dependencyhash;
  id: Id28;
  kind: Kind22;
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
  review?: ModelCapture | null;
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
  recordId: Recordid3;
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
  errorCode: Errorcode3;
  factsHash: Factshash1;
  id: Id29;
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
  id: Id30;
  issuesHash: Issueshash;
  operationId: Operationid2;
  packageHash: Packagehash4;
  sourceHash: Sourcehash;
  startedAt: Startedat1;
}
export interface ImportIssue {
  blockIds: Blockids1;
  category: Category2;
  code: Code2;
  id: Id32;
  importedFingerprint: Importedfingerprint;
  lifecycleId: Lifecycleid;
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
  droppedValues?: Droppedvalues;
  errors: Errors;
  id: Id33;
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
/**
 * A value a repair still stated without any source line (I4): removed from the block and named in its notice.
 */
export interface DroppedValue {
  fieldKey: Fieldkey3;
  pointer: Pointer;
  text: Text7;
}
export interface Lineage1 {
  attemptId: Attemptid2;
  children: Children;
  kind: Kind23;
  parents: Parents;
}
export interface ProposalReply {
  discoveries: Discoveries;
  fields: Fields1;
  lineage: Lineage2;
  payload: JsonValue;
  relations?: Relations2;
  schemaVersion: Schemaversion5;
}
export interface Discovery {
  key: Key1;
  pointer: Pointer1;
  semanticType: Semantictype4;
}
export interface ProposalField {
  effectiveCellIds: Effectivecellids;
  evidence: Evidence15;
  fieldKey: Fieldkey4;
  item: Item;
  pointer: Pointer2;
}
export interface DiscoverySelector {
  key: Key2;
  kind: Kind24;
}
export interface HandleSelector {
  itemHandle: Itemhandle6;
  kind: Kind25;
}
export interface ProposalLineage {
  children: Children1;
  kind: Kind26;
  parents: Parents1;
}
export interface ProposalRelation {
  evidence: Evidence16;
  kind: Kind27;
  relation: Relation1;
  subject: Subject;
  target: Target;
}
export interface RelationDiscoverySelector {
  key: Key3;
  kind: Kind28;
}
export interface ExistingRelationSelector {
  kind: Kind29;
  relationId: Relationid;
}
export interface FieldSidecar {
  effectiveCellIds: Effectivecellids1;
  evidence: Evidence17;
  fieldKey: Fieldkey5;
  itemHandle: Itemhandle7;
  pointer: Pointer3;
}
export interface PublicationOutcome {
  errorCode: Errorcode4;
  intentId: Intentid;
  state: State7;
  workspaceHash: Workspacehash;
}
export interface ReviewReceipt {
  attemptId: Attemptid3;
  completedAt: Completedat;
  expectedChecks: Expectedchecks;
  id: Id34;
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
  evidence: Evidence18;
  reason: Reason1;
  ruleId: Ruleid2;
  targetId: Targetid2;
}
export interface RelationAllocation {
  discoveryAttemptId: Discoveryattemptid1;
  key: Key4;
  kind: Kind30;
  operationId: Operationid3;
  relationId: Relationid1;
  subjectId: Subjectid1;
  targetId: Targetid3;
  taskId: Taskid3;
}
export interface ReviewInputRecord {
  attemptId: Attemptid4;
  id: Id35;
  inputHash: Inputhash2;
  value: ReviewInput;
}
export interface ReviewInput {
  allowTextRewrite: Allowtextrewrite2;
  effectiveCells: Effectivecells;
  evidence?: Evidence19;
  handleMap: Handlemap;
  occurrenceContext: JsonValue;
  occurrenceIndependent: Occurrenceindependent;
  packageHash: Packagehash5;
  policy: ModelCapture;
  proposalHash: Proposalhash2;
  protocol: Protocol;
  relations: Relations3;
  rules: Rules;
  schemaVersion: Schemaversion6;
  semanticContext: Semanticcontext;
  settled?: Settled;
  sourceSpans: Sourcespans;
  sourceTexts: Sourcetexts;
  targets: Targets;
}
export interface EvidenceOption {
  ref: Ref;
  span: SourceSpan;
  text: Text8;
}
export interface Check {
  id: Id36;
  kind: Kind31;
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
/**
 * A check the coordinator settles without the model (D115): a verbatim value's check, or an earlier receipt's
 * result for a value the repair left as it was.
 */
export interface SettledCheck {
  actionable: Actionable1;
  disposition: Disposition2;
  evidence: Evidence20;
  origin: Origin14;
  reason: Reason2;
  ruleId: Ruleid3;
  targetId: Targetid4;
}
export interface Sourcetexts {
  [k: string]: string;
}
export interface TaskInputRecord {
  capturedAt: Capturedat;
  id: Id37;
  inputHash: Inputhash3;
  taskId: Taskid4;
  value: Value2;
}
export interface Value2 {
  [k: string]: JsonValue;
}
export interface TaskResultRecord {
  disposition: Disposition3;
  id: Id38;
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
  blockId: Blockid1;
  dependencies: Dependencies1;
  entry?: EntryScope | null;
  expectedChecks: Expectedchecks1;
  id: Id39;
  inputHash: Inputhash5;
  issueIds: Issueids1;
  kind: Kind32;
  operationId: Operationid4;
  parentTaskId?: Parenttaskid;
  proposalHash: Proposalhash3;
  receiptIds: Receiptids1;
  state: State9;
}
/**
 * The part of a block one entry task extracts (D117): its place in the block's order, its title, its source lines,
 * the outline entries they hold (consecutive ones, joined so the block makes about as many calls as run at once)
 * and whether the outline or its review named them.
 */
export interface EntryScope {
  index: Index1;
  origin: Origin15;
  parts: Parts;
  spans: Spans1;
  title: Title6;
}
/**
 * One entry the outline named (D117): its title and its source lines.
 */
export interface EntryPart {
  spans: Spans;
  title: Title5;
}
export interface StoredTemplatePackage {
  assets: Assets;
  blocks: Blocks4;
  compilerVersion: Compilerversion;
  configHash: Confighash;
  definition: TemplateDefinition;
  id: Id52;
  manifest: CompilationManifest;
  operationVersion: Operationversion;
  originalBase64: Originalbase64;
  originalFormat: Originalformat;
  originalHash: Originalhash;
  packageHash: Packagehash6;
  projectionVersion: Projectionversion;
  recipe: CompiledRecipe;
  revision: Revision28;
  schemaVersion: Schemaversion8;
}
/**
 * An asset of a workspace's captured package. Its bytes stay in memory and in the project's asset files, never in
 * the workspace JSON, its hash or the browser's copy (D104: fonts were a quarter of every 10 MB reply).
 */
export interface StoredAsset {
  bytesBase64?: Bytesbase64;
  id: Id40;
  mimeType: Mimetype1;
  path: Path;
  role: Role1;
  sha256: Sha256;
  size: Size3;
}
export interface CompiledBlock {
  dependencyOrder: Dependencyorder;
  fullSchema: Fullschema;
  id: Id41;
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
  blocks: Blocks5;
  content_definitions: ContentDefinitions;
  fact_types: FactTypes;
  layout: Layout;
  model: ModelInstructions;
  operations: Operations1;
  provenance: Provenance;
  schema_version: SchemaVersion1;
  source: SourcePolicy;
  style: Style1;
  template: TemplateIdentity;
}
export interface AssetDeclaration {
  embedding: Embedding;
  id: Id42;
  mime_type: MimeType;
  path: Path1;
  role: Role2;
}
export interface Block {
  bindings: Bindings;
  checks: Checks;
  content_schema: ContentSchema;
  depends_on: DependsOn;
  effort?: Effort1;
  extract: Extract;
  id: Id43;
  mode: Mode2;
  operation: Operation;
  per_entry?: PerEntry;
  placement: Placement;
  rewrite: Rewrite;
  selectors: Selectors;
  view: View;
  when: Condition | null;
}
export interface Binding {
  field: Field1;
  item_pointer?: ItemPointer;
  pointer: Pointer4;
  relation: BindingRelation | null;
  semantic_type: SemanticType;
}
export interface BindingRelation {
  kind: Kind33;
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
  id: Id44;
  kind: Kind34;
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
  id: Id45;
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
  kind: Kind35;
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
  id: Id46;
  inputs: Inputs;
  kind: Kind36;
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
  id: Id47;
  inputs: Inputs1;
  kind: Kind37;
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
  id: Id48;
  inputs: Inputs2;
  kind: Kind38;
  parameters: SkillsParameters;
  version: Version4;
}
export interface SkillsParameters {
  groups: Groups;
  uncertain_group: UncertainGroup;
}
export interface PeriodOperation {
  depends_on: DependsOn4;
  id: Id49;
  inputs: Inputs3;
  kind: Kind39;
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
  id: Id50;
  inputs: Inputs4;
  kind: Kind40;
  parameters: EmptyParameters;
  version: Version6;
}
export interface EmptyParameters {}
export interface Provenance {
  [k: string]: JsonValue;
}
export interface SourcePolicy {
  retain_original: RetainOriginal;
  retain_unmapped_facts: RetainUnmappedFacts;
}
export interface TemplateIdentity {
  default_locale: DefaultLocale;
  id: Id51;
  name: Name1;
  revision: Revision27;
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
  importHistory?: Importhistory;
  importIssues: Importissues;
  operations: Operations2;
  projectId: Projectid2;
  renders: Renders;
  revision: Revision44;
  schemaVersion: Schemaversion11;
  sources: Sources1;
  templateOperations?: Templateoperations1;
  templatePackage: StoredTemplatePackage;
}
export interface LocalImageAsset {
  height: Height3;
  id: Id53;
  mimeType: Mimetype2;
  path: Path2;
  sha256: Sha2561;
  size: Size4;
  width: Width4;
}
export interface RichDocumentV2 {
  regions: Regions1;
  revision: Revision43;
  schemaVersion: Schemaversion9;
}
export interface TemplateRegion {
  blocks: Blocks6;
  id: Id72;
  revision: Revision42;
  role: Role3;
}
export interface TemplateParagraphBlock {
  children: Children2;
  content: Content13;
  id: Id71;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance12;
  revision: Revision41;
  type: Type17;
}
export interface TemplateHeadingBlock {
  children: Children3;
  content: Content12;
  id: Id70;
  presentation: AuthoredPresentation | null;
  props: HeadingProps;
  provenance: Provenance11;
  revision: Revision40;
  type: Type16;
}
export interface TemplateBulletBlock {
  children: Children4;
  content: Content11;
  id: Id69;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance10;
  revision: Revision39;
  type: Type15;
}
export interface TemplateNumberedBlock {
  children: Children5;
  content: Content10;
  id: Id68;
  presentation: AuthoredPresentation | null;
  props: NumberedProps;
  provenance: Provenance9;
  revision: Revision38;
  type: Type14;
}
export interface TemplateChecklistBlock {
  children: Children6;
  content: Content9;
  id: Id67;
  presentation: AuthoredPresentation | null;
  props: ChecklistProps;
  provenance: Provenance8;
  revision: Revision37;
  type: Type13;
}
export interface TemplateToggleBlock {
  children: Children7;
  content: Content8;
  id: Id66;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance7;
  revision: Revision36;
  type: Type12;
}
export interface TemplateQuoteBlock {
  children: Children8;
  content: Content7;
  id: Id65;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision35;
  type: Type11;
}
export interface TemplateCodeBlock {
  children: Children9;
  content: Content6;
  id: Id64;
  presentation: AuthoredPresentation | null;
  props: CodeProps;
  provenance: Provenance5;
  revision: Revision34;
  type: Type10;
}
export interface TemplateDividerBlock {
  children: Children10;
  content: Content5;
  id: Id63;
  presentation: AuthoredPresentation | null;
  props: EmptyProps;
  provenance: Provenance4;
  revision: Revision33;
  type: Type9;
}
export interface TemplateTableBlock {
  children: Children11;
  content: TemplateTableContent;
  id: Id62;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance3;
  revision: Revision32;
  type: Type8;
}
export interface TemplateImageBlock {
  children: Children12;
  content: Content3;
  id: Id59;
  presentation: AuthoredPresentation | null;
  props: TemplateImageProps;
  provenance: Provenance2;
  revision: Revision30;
  type: Type7;
}
export interface TemplateSectionBlock {
  children: Children13;
  content: Content;
  id: Id54;
  presentation: AuthoredPresentation | null;
  props: SectionProps;
  provenance: Provenance1;
  revision: Revision29;
  type: Type6;
}
export interface PresentedText {
  citations?: Citations;
  presentation?: AuthoredPresentation | null;
  styles: InlineStyles;
  text: Text9;
  type: Type1;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold3;
  code?: Code3;
  italic?: Italic2;
  strike?: Strike;
  textColor?: Textcolor;
  underline?: Underline;
}
export interface PresentedHyperlink {
  content: Content1;
  href: Href;
  presentation?: AuthoredPresentation | null;
  type: Type2;
}
export interface FieldOccurrence {
  bindingId: Bindingid;
  bindingRootId?: Bindingrootid;
  cellId: Cellid1;
  citations?: Citations1;
  complete: Complete1;
  fieldKey: Fieldkey6;
  occurrenceId: Occurrenceid;
  presentation: AuthoredPresentation | null;
  recordId: Recordid4;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text10;
  type: Type3;
}
export interface BoundLink {
  content: Content2;
  href: Href1;
  labelBinding: FieldRef | null;
  presentation: AuthoredPresentation | null;
  type: Type4;
  urlBinding: FieldRef | null;
}
export interface FieldRef {
  cellId: Cellid2;
  fieldKey: Fieldkey7;
  occurrenceId: Occurrenceid1;
  recordId: Recordid5;
}
export interface ManualScopeSpan {
  citations?: Citations2;
  fragmentId: Fragmentid;
  occurrenceId: Occurrenceid2;
  presentation: AuthoredPresentation | null;
  scopeId: Scopeid;
  styles: InlineStyles;
  text: Text11;
  type: Type5;
}
export interface SectionProps {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor1;
  manualOrder?: Manualorder;
  presentation?: Presentation;
  recordId: Recordid6;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence21;
  fieldKeys: Fieldkeys;
  id: Id55;
  kind: Kind41;
  recordId: Recordid7;
}
export interface FieldBinding {
  fieldKey: Fieldkey8;
  id: Id56;
  kind: Kind42;
  recordId: Recordid8;
}
export interface WorkingOwnership {
  id: Id57;
  kind: Kind43;
  recordId: Recordid9;
}
export interface SourceWitness {
  evidence: Evidence22;
  id: Id58;
  kind: Kind44;
}
export interface TemplateImageProps {
  alignment: Alignment3;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height4;
  width: Width5;
}
export interface TemplateTableContent {
  columnWidths: Columnwidths;
  headerCols?: Headercols;
  headerRows: Headerrows;
  rows: Rows;
}
export interface TemplateTableRow {
  cells: Cells1;
  id: Id61;
}
export interface TemplateTableCell {
  alignment?: Alignment4;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content4;
  id: Id60;
  revision: Revision31;
  rowspan?: Rowspan;
}
export interface ParagraphProps {
  alignment?: Alignment5;
  backgroundColor?: Backgroundcolor3;
  textColor?: Textcolor2;
}
export interface EmptyProps {}
export interface CodeProps {
  backgroundColor?: Backgroundcolor4;
  language: Language1;
}
export interface ChecklistProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor5;
  checked: Checked;
  textColor?: Textcolor3;
}
export interface NumberedProps {
  alignment?: Alignment7;
  backgroundColor?: Backgroundcolor6;
  start?: Start2;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment8;
  backgroundColor?: Backgroundcolor7;
  level: Level1;
  textColor?: Textcolor5;
}
export interface ImmutableFactEvidence {
  evidence: Evidence23;
  id: Id73;
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
  schemaVersion: Schemaversion10;
}
export interface TemplateRenderAsset {
  id: Id74;
  path: Path3;
  sha256: Sha2562;
  size: Size5;
}
export interface TemplateRendererIdentity {
  id: Id75;
  sha256: Sha2563;
  version: Version7;
}
export interface SpanCoverage {
  blockIds: Blockids2;
  disposition: Disposition4;
  itemHandle: Itemhandle8;
  reason: Reason3;
  span: SourceSpan;
}
/**
 * A published import's record, kept in the project's history file of this hash (D104).
 */
export interface ImportHistoryRef {
  operationId: Operationid5;
  sha256: Sha2564;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision3;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id76;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface Rules1 {
  markdown: Markdown;
  revision: Revision45;
  sha256: Sha2565;
}
export interface TemplateSyncRecord {
  actionId: Actionid4;
  blockIds: Blockids3;
  capture: ActionCapture | null;
  dependencies: Dependencies3;
  errorCode: Errorcode5;
  factIds: Factids;
  fieldKeys: Fieldkeys1;
  id: Id77;
  instruction?: Instruction;
  kind?: Kind45;
  lifecycleId: Lifecycleid1;
  ownershipConflict: TemplateOwnershipConflict | null;
  proposedSteps?: Proposedsteps;
  ready?: Ready;
  resolutionOf?: TemplateSyncResolution | null;
  rewriteResult?: Rewriteresult;
  rewriteSource?: Rewritesource;
  schemaVersion: Schemaversion13;
  selection?: RichSelection | null;
  status: Status9;
}
export interface ActionCapture {
  actionId: Actionid5;
  actionToken: Actiontoken;
  dependencies: Dependencies2;
  sessionId: Sessionid;
}
export interface TemplateOwnershipConflict {
  beforeOwnerId: Beforeownerid;
  movedOccurrenceIds: Movedoccurrenceids;
  proposedOwnerId: Proposedownerid;
  recordId: Recordid10;
  relationId: Relationid2;
  remainingOccurrenceIds: Remainingoccurrenceids;
}
export interface TemplatePutBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision;
  block: Block1;
  keepChildren?: Keepchildren;
  kind: Kind46;
  parentId: Parentid1;
}
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid2;
  kind: Kind47;
}
export interface MoveBlock {
  afterId: Afterid2;
  beforeRevision: Beforerevision2;
  blockId: Blockid3;
  kind: Kind48;
  parentId: Parentid2;
}
export interface TemplateReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid4;
  cellId: Cellid3;
  content: Content14;
  end: End2;
  field: Field4;
  flankBindings?: Flankbindings;
  kind: Kind51;
  start: Start3;
}
export interface FlankBinding {
  fragmentId: Fragmentid1;
  role: Role4;
  source: Source1;
  sourceEnd: Sourceend;
  sourceStart: Sourcestart;
}
export interface FieldFlankSource {
  bindingId: Bindingid1;
  kind: Kind49;
}
export interface ManualScopeFlankSource {
  fragmentId: Fragmentid2;
  kind: Kind50;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind52;
  record: Record1;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind53;
  recordId: Recordid11;
}
export interface PutExtension {
  beforeRevision: Beforerevision6;
  kind: Kind54;
  record: ExtensionRecord;
}
export interface RemoveExtension {
  beforeRevision: Beforerevision7;
  kind: Kind55;
  recordId: Recordid12;
}
export interface PutRelation {
  beforeRevision: Beforerevision8;
  kind: Kind56;
  relation: Relation;
}
export interface RemoveRelation {
  beforeRevision: Beforerevision9;
  kind: Kind57;
  relationId: Relationid3;
}
export interface PutManualScope {
  kind: Kind58;
  scope: ManualEditScope;
}
export interface SetBuiltinManualScope {
  afterScopeId: Afterscopeid;
  beforeScopeId: Beforescopeid;
  cellId: Cellid4;
  kind: Kind59;
}
export interface SetIssueState {
  actionId: Actionid6;
  afterLifecycleId: Afterlifecycleid;
  afterState: Afterstate;
  beforeLifecycleId: Beforelifecycleid;
  beforeState: Beforestate;
  importedFingerprint: Importedfingerprint1;
  issueId: Issueid;
  kind: Kind60;
}
export interface SetAuthoredAnchors {
  afterBlockIds: Afterblockids;
  beforeBlockIds: Beforeblockids;
  kind: Kind61;
  target: Target1;
}
export interface IssueAnchorTarget {
  beforeLifecycleId: Beforelifecycleid1;
  beforeState: Beforestate1;
  importedFingerprint: Importedfingerprint2;
  issueId: Issueid1;
  kind: Kind62;
}
export interface CoverageAnchorTarget {
  coverageIdentityHash: Coverageidentityhash;
  coverageIndex: Coverageindex;
  coverageSequenceHash: Coveragesequencehash;
  kind: Kind63;
}
export interface RestoreAuthoredBlockPatch {
  afterSemanticHash: Aftersemantichash;
  beforeRevision: Beforerevision10;
  beforeSemanticHash: Beforesemantichash;
  blockId: Blockid5;
  kind: Kind64;
  patch: Patch;
}
export interface PatchSet {
  kind: Kind65;
  pointer: Pointer5;
  valueWire: Valuewire;
}
export interface PatchInsert {
  kind: Kind66;
  pointer: Pointer6;
  valueWire: Valuewire1;
}
export interface PatchRemove {
  kind: Kind67;
  pointer: Pointer7;
}
export interface PatchSpliceText {
  beforeTextHash: Beforetexthash;
  end: End3;
  kind: Kind68;
  pointer: Pointer8;
  start: Start4;
  text: Text12;
}
export interface SetManualScopeDisplays {
  assignments: Assignments;
  kind: Kind71;
  sources: Sources2;
}
export interface ScopeDisplayAssignment {
  address: ScopeDisplayAddress;
  after: After;
  beforeHash: Beforehash;
}
export interface ScopeDisplayAddress {
  blockId: Blockid6;
  cellId: Cellid5;
  field: Field5;
  inlineIndex: Inlineindex;
}
export interface ScopeDisplayBinding {
  fragmentId: Fragmentid3;
  kind: Kind69;
  occurrenceId: Occurrenceid3;
  scopeId: Scopeid1;
}
export interface LiteralDisplayBinding {
  kind: Kind70;
}
export interface ScopeDisplaySource {
  activeCellIds: Activecellids;
  fragments: Fragments;
  occurrenceId: Occurrenceid4;
  scopeHash: Scopehash;
  scopeId: Scopeid2;
}
export interface ScopeDisplayFragment {
  blockId: Blockid7;
  cellId: Cellid6;
  field: Field6;
  fragmentHash: Fragmenthash;
  fragmentId: Fragmentid4;
}
export interface TemplateSyncResolution {
  beforeLifecycleId: Beforelifecycleid2;
  beforeRecordHash: Beforerecordhash;
  syncId: Syncid;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids4;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind72;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid8;
  cellId: Cellid7;
  offset: Offset;
}
export interface RichSyncRecord {
  actionId: Actionid7;
  blockIds: Blockids5;
  dependencies: Dependencies4;
  errorCode: Errorcode6;
  factIds: Factids1;
  fieldKeys: Fieldkeys2;
  id: Id78;
  instruction?: Instruction1;
  kind?: Kind73;
  proposedSteps?: Proposedsteps1;
  ready?: Ready1;
  rewriteResult?: Rewriteresult1;
  rewriteSource?: Rewritesource1;
  selection?: RichSelection | null;
  status: Status10;
}
export interface PutBlock {
  afterId: Afterid3;
  beforeRevision: Beforerevision11;
  block: Block2;
  keepChildren?: Keepchildren1;
  kind: Kind74;
  parentId: Parentid3;
}
export interface ParagraphBlock {
  children: Children14;
  content: Content27;
  id: Id92;
  props: ParagraphProps;
  provenance: Provenance24;
  revision: Revision58;
  type: Type32;
}
export interface HeadingBlock {
  children: Children15;
  content: Content26;
  id: Id91;
  props: HeadingProps;
  provenance: Provenance23;
  revision: Revision57;
  type: Type31;
}
export interface BulletBlock {
  children: Children16;
  content: Content25;
  id: Id90;
  props: ParagraphProps;
  provenance: Provenance22;
  revision: Revision56;
  type: Type30;
}
export interface NumberedBlock {
  children: Children17;
  content: Content24;
  id: Id89;
  props: NumberedProps;
  provenance: Provenance21;
  revision: Revision55;
  type: Type29;
}
export interface ChecklistBlock {
  children: Children18;
  content: Content23;
  id: Id88;
  props: ChecklistProps;
  provenance: Provenance20;
  revision: Revision54;
  type: Type28;
}
export interface ToggleBlock {
  children: Children19;
  content: Content22;
  id: Id87;
  props: ParagraphProps;
  provenance: Provenance19;
  revision: Revision53;
  type: Type27;
}
export interface QuoteBlock {
  children: Children20;
  content: Content21;
  id: Id86;
  props: ParagraphProps;
  provenance: Provenance18;
  revision: Revision52;
  type: Type26;
}
export interface CodeBlock {
  children: Children21;
  content: Content20;
  id: Id85;
  props: CodeProps;
  provenance: Provenance17;
  revision: Revision51;
  type: Type25;
}
export interface DividerBlock {
  children: Children22;
  content: Content19;
  id: Id84;
  props: EmptyProps;
  provenance: Provenance16;
  revision: Revision50;
  type: Type24;
}
export interface TableBlock {
  children: Children23;
  content: TableContent;
  id: Id83;
  props: ParagraphProps;
  provenance: Provenance15;
  revision: Revision49;
  type: Type23;
}
export interface ImageBlock {
  children: Children24;
  content: Content17;
  id: Id80;
  props: ImageProps;
  provenance: Provenance14;
  revision: Revision47;
  type: Type22;
}
export interface SectionBlock {
  children: Children25;
  content: Content15;
  id: Id79;
  props: SectionProps;
  provenance: Provenance13;
  revision: Revision46;
  type: Type21;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text13;
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
  fieldKey: Fieldkey9;
  recordId: Recordid13;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision1;
  text: Text14;
  type: Type20;
}
export interface ImageProps {
  alignment: Alignment9;
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
  id: Id82;
}
export interface TableCell {
  alignment?: Alignment10;
  backgroundColor?: Backgroundcolor8;
  colspan?: Colspan1;
  content: Content18;
  id: Id81;
  revision: Revision48;
  rowspan?: Rowspan1;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision12;
  blockId: Blockid9;
  cellId: Cellid8;
  content: Content28;
  end: End4;
  field: Field7;
  kind: Kind75;
  start: Start5;
}
export interface RichWarning {
  blockIds: Blockids6;
  code: Code4;
  count?: Count;
  evidence: Evidence24;
  id: Id93;
  locations?: Locations;
  recordIds: Recordids;
}
export interface Evidence25 {
  sourceId: Sourceid3;
  sourceRevision: Sourcerevision2;
  unitId: Unitid4;
  unitRevision: Unitrevision2;
}
export interface WarningLocation {
  page?: Page3;
  sourceId: Sourceid4;
}
export interface AssistantChangeProposalV1 {
  appliedRevision: Appliedrevision;
  baseRevision: Baserevision;
  conversationId: Conversationid;
  createdAt: Createdat2;
  expectedActionId?: Expectedactionid;
  id: Id94;
  kind: Kind76;
  ops: Ops;
  preview: Preview;
  projectId: Projectid4;
  runId: Runid1;
  schemaVersion: Schemaversion15;
  state: State10;
  summary: Summary;
  touched: Touched;
  updatedAt: Updatedat1;
}
export interface SetBlockTextOp {
  blockId: Blockid10;
  cellId?: Cellid9;
  field?: Field8;
  marks?: InlineStyles | null;
  op: Op;
  text: Text15;
}
export interface ReplaceTextOp {
  blockId: Blockid11;
  cellId?: Cellid10;
  field?: Field9;
  find: Find;
  op: Op1;
  replace: Replace;
}
export interface InsertBlocksOp {
  afterBlockId?: Afterblockid;
  blocks: Blocks7;
  op: Op2;
  parentId?: Parentid4;
}
export interface NewBlock {
  kind?: Kind77;
  level?: Level2;
  text: Text16;
}
export interface DeleteBlocksOp {
  blockIds: Blockids7;
  op: Op3;
}
export interface MoveBlockOp {
  afterBlockId?: Afterblockid1;
  blockId: Blockid12;
  op: Op4;
  parentId?: Parentid5;
}
export interface FormatBlockOp {
  alignment?: Alignment11;
  backgroundColor?: Backgroundcolor9;
  blockId: Blockid13;
  kind?: Kind78;
  level?: Level3;
  op: Op5;
  textColor?: Textcolor6;
}
export interface UpdateFactOp {
  field: Field10;
  op: Op6;
  recordId: Recordid14;
  value: Value3;
}
export interface CreateFactOp {
  jobId?: Jobid6;
  kind: Kind79;
  op: Op7;
  values?: Values;
}
export interface Values {
  [k: string]: string;
}
export interface DeleteFactOp {
  op: Op8;
  recordId: Recordid15;
}
export interface HistoryOp {
  direction: Direction;
  op: Op9;
}
export interface ActionOp {
  action: Action2;
  op: Op10;
  targetId?: Targetid5;
  value?: Value4;
}
export interface PreviewEntryV1 {
  after: After1;
  before: Before;
  label: Label3;
  target: Target2;
}
export interface Touched {
  [k: string]: string;
}
