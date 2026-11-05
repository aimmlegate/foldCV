export type Code =
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
export type AgentEvent =
  MessageDelta | ActivityEvent | ToolEvent | ResourceEvent | EditEvent | UsageEvent | RunStateEvent;
export type Conversationid = string;
export type Id = string;
export type Text = string;
export type Projectid = string;
export type Runid = string;
export type Schemaversion = 1;
export type Sequence = number;
export type Timestamp = string;
export type Type = "message.delta";
export type Conversationid1 = string;
export type Id1 = string;
export type Itemid = string;
export type Kind = "summary";
export type Text1 = string;
export type Projectid1 = string;
export type Runid1 = string;
export type Schemaversion1 = 1;
export type Sequence1 = number;
export type Timestamp1 = string;
export type Type1 = "activity.updated";
export type Conversationid2 = string;
export type Id2 = string;
export type Callid = string;
export type Name = string;
export type Projectid2 = string;
export type Runid2 = string;
export type Schemaversion2 = 1;
export type Sequence2 = number;
export type Timestamp2 = string;
export type Type2 = "tool.started" | "tool.completed" | "tool.failed";
export type Conversationid3 = string;
export type Id3 = string;
export type Id4 = string;
export type Projectid3 = string;
export type Runid3 = string;
export type Schemaversion3 = 1;
export type Sequence3 = number;
export type Timestamp3 = string;
export type Type3 = "source.ready" | "finding.ready" | "proposal.ready" | "file.ready";
export type Conversationid4 = string;
export type Id5 = string;
export type Batchid = string;
export type Disposition =
  | "prepared"
  | "offered"
  | "applying"
  | "saved"
  | "stale"
  | "rejected"
  | "cancelled"
  | "save_failed"
  | "outcome_unknown";
export type Projectid4 = string;
export type Runid4 = string;
export type Schemaversion4 = 1;
export type Sequence4 = number;
export type Timestamp4 = string;
export type Type4 = "edit.offered" | "edit.result";
export type Conversationid5 = string;
export type Id6 = string;
export type Cachedinputtokens = number;
export type Inputtokens = number;
export type Outputtokens = number;
export type Totaltokens = number;
export type Projectid5 = string;
export type Runid5 = string;
export type Schemaversion5 = 1;
export type Sequence5 = number;
export type Timestamp5 = string;
export type Type5 = "usage.reported";
export type Conversationid6 = string;
export type Id7 = string;
export type Outcomeunknown = boolean;
export type Savedbatchid = string | null;
export type State =
  "queued" | "running" | "waiting_for_editor" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Projectid6 = string;
export type Runid6 = string;
export type Schemaversion6 = 1;
export type Sequence6 = number;
export type Timestamp6 = string;
export type Type6 = "run.state_changed";
export type Url = string;
/**
 * @maxItems 20
 */
export type Anchors =
  | []
  | [AgentAnchor]
  | [AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor, AgentAnchor]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ]
  | [
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor,
      AgentAnchor
    ];
export type Blockid = string | null;
export type Cellid = string | null;
export type Fingerprint = string | null;
export type Id8 = string;
export type Kind1 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
/**
 * @maxItems 100
 */
export type Dependencies = DependencyStamp[];
export type End = number | null;
export type Fieldkey = string | null;
export type Recordid = string | null;
export type Start = number | null;
export type Text2 = string;
export type Id9 = string;
export type Message = string;
export type Runid7 = string;
export type Severity = "info" | "warning" | "error";
/**
 * @maxItems 20
 */
export type Sourceids =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
export type Id10 = string;
export type Label = string;
/**
 * @maxItems 100
 */
export type Findings = AgentReference[];
export type Id11 = string;
export type Role = "user" | "assistant";
export type Runid8 = string;
/**
 * @maxItems 100
 */
export type Sources = AgentReference[];
export type Text3 = string;
export type Timestamp7 = string;
export type Truncated = boolean;
export type Enabled = boolean;
export type Reasoningeffort = ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Revision1 = number;
export type Schemaversion7 = 1;
export type Selectedagentmodel = string | null;
export type Enabled1 = boolean;
export type Expectedrevision = number;
export type Reasoningeffort1 = ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Selectedagentmodel1 = string | null;
export type Contentsha256 = string;
export type Finalurl = string;
export type Id12 = string;
export type Originalbytes = number;
export type Requestedurl = string;
export type Retrievedat = string;
export type Runid9 = string;
export type Text4 = string;
export type Title = string;
export type Truncated1 = boolean;
export type Documentrevision = number;
export type Editortoken = string;
export type Projectrevision = number;
export type Appversion = string;
/**
 * @minItems 1
 * @maxItems 47
 */
export type Entries = [TemplateArchiveEntry, ...TemplateArchiveEntry[]];
export type Path = string;
export type Role1 =
  | "workspace"
  | "source_original"
  | "render"
  | "user_image"
  | "template_package"
  | "template_asset"
  | "template_history";
export type Sha256 = string;
export type Size = number;
export type Projectid7 = string;
export type Schemaversion8 = 7;
export type Allowedits = boolean;
export type Clientmutationid = string;
export type Editortoken1 = string;
export type Action = "rename" | "formatting_date" | "archive" | "restore" | "delete";
export type Archived = boolean | null;
export type Deleted = boolean;
export type Title1 = string | null;
export type Changedblockids = string[];
export type Clientmutationid1 = string;
export type Documentrevision1 = number;
export type Actionid = string;
export type Kind2 = "edit";
export type Replayed = boolean;
export type Durability = "pending" | "durable" | "failed";
export type Errorcode = string | null;
export type Id13 = string;
export type Stage = "assess_resume" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Startedat = string | null;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Subtitle = string;
export type Title2 = string;
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
export type Addkinds = ("employment" | "education" | "language")[];
export type Addtechnologygroup = boolean;
export type Band = true | null;
/**
 * @minItems 1
 */
export type Blocks2 = [string, ...string[]];
export type Icon = string | null;
export type Links = string[];
export type First = boolean;
export type Gap = number | null;
export type Label1 = string;
export type Last = boolean;
export type Table = string;
export type Style = string;
export type Full = boolean;
export type Icons = boolean;
export type Records = string[];
export type Fonts = string[];
export type Icons1 = string[];
export type Addperiod = boolean;
export type Periods = string[];
export type Alignment1 = ("left" | "center" | "right" | "justify") | null;
export type Color1 = string;
export type Bold1 = string | null;
export type Bolditalic = string | null;
export type Italic1 = string | null;
export type Regular = string | null;
export type Upright = string | null;
export type Lineheight = number;
export type Size2 = number;
export type Technologylines = string[][];
export type Blockid1 = string;
export type Jobid = string | null;
export type Label2 = string;
export type Afterid = string | null;
export type Parentid = string;
export type Records1 = string[];
export type Technologytargets = EditorTechnologyTarget[];
export type Capabilities = string[];
export type AllowMorePages = true;
export type AllowProjectSplit = true;
export type KeepHeadingWithNext = boolean;
export type TruncateContent = false;
export type ReadingOrder = ("header" | "sidebar" | "main")[];
export type Flow = "first_page_header" | "independent_column";
export type Id14 = "header" | "sidebar" | "main";
export type Width = number;
export type X = number;
export type Regions = Region[];
export type Order = number;
export type Region1 = "header" | "sidebar" | "main";
export type Renderinputversion = 1;
export type Schemaversion9 = 1;
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
export type Text5 = string;
export type Color2 = string;
export type FollowHeader = true;
export type Width1 = number;
export type X1 = number;
export type X2 = number;
export type Y = number;
export type Asset = string | null;
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
export type Background1 = string | null;
export type BorderColor = string | null;
export type BorderWidth = number;
export type LabelAlign = "top" | "center";
export type LabelBackground = string | null;
export type LabelStyle = string;
export type LabelWidth = number;
export type PaddingX = number;
export type PaddingY = number;
export type Alignment2 = ("left" | "center" | "right" | "justify") | null;
export type Color3 = string;
export type Font1 = string;
export type LineHeight = number;
export type Size3 = number;
export type FallbackStyle = string | null;
export type Heading = "none" | "plain" | "band";
export type HeadingStyle1 = string | null;
export type Inset = number;
export type ItemGap = number;
export type Mode = "object" | "items";
export type Background2 = string | null;
export type DetailStyle = string | null;
export type ExperienceField = string | null;
export type Field = string | null;
export type Fields = string[];
export type HeaderSlot = ("name" | "profession") | null;
export type ItemField = string | null;
export type LabelStyle1 = string | null;
export type NameField = string | null;
export type PrefixStyle = string | null;
export type Row = {
  [k: string]: string;
} | null;
export type Separator = string;
export type Style3 = string;
export type Type7 = "text" | "join_fields" | "join_items" | "bullets" | "tags" | "period" | "link" | "focus_entry";
export type UrlField = string | null;
export type Nodes = ViewNode[];
export type Row1 = {
  [k: string]: string;
} | null;
export type Table1 = string | null;
export type Schemaversion10 = 1;
export type Documenthash = string;
export type Documentrevision2 = number;
export type Factshash = string;
export type Packagehash1 = string;
export type Presentationhash = string;
export type Projectid8 = string;
export type Projectrevision1 = number;
export type Saveerror = string | null;
export type Saveddocumentrevision = number | null;
export type Savedprojectrevision = number | null;
export type Schemaversion11 = 1;
export type Createdat = string;
export type Documentrevision3 = number;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Changedblockids1 = string[];
export type Clientmutationid2 = string;
export type Requestsha256 = string;
export type Resultingrevision = number;
export type Mutationreplay = RichMutationReplay[];
export type Cellid1 = string;
export type Fieldkey1 = string;
export type Periodid = string | null;
export type Itemhandle1 = string;
export type Recordid1 = string;
export type Semanticschemahash = string;
export type Semantictype = string;
export type Builtinidentities = BuiltinItemIdentity[];
export type Active = boolean;
export type Admissionreceiptids = string[];
export type End1 = number;
export type Slicehash = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Start1 = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = SourceSpan[];
export type Fieldkey2 = string;
export type Id15 = string;
export type Manualscopeid = string | null;
export type Observationids = string[];
export type Origin = "model" | "source" | "human";
export type Rawinput = string;
export type Revision2 = number;
export type State1 = "admitted" | "human_raw" | "pending_manual" | "uncertain";
export type JsonValue = unknown;
export type Usercorrected = boolean;
export type Cells = ExtensionCell[];
export type Copyofrecordid = string | null;
export type Id16 = string;
export type Itemhandle2 = string;
export type Observationids1 = string[];
export type Active1 = boolean;
export type Id17 = string;
export type Kind3 = "owned_by" | "extension_of" | "related_to";
export type Revision3 = number;
export type Subjectid = string;
export type Targetid = string;
export type Relations = Relation[];
export type Revision4 = number;
export type Schemaversion12 = 1;
export type Semanticschemahash1 = string;
export type Semantictype1 = string;
export type Extensions = ExtensionRecord[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status1 = "complete" | "partial";
export type Code1 = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
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
export type Id18 = string;
export type Rawinput1 = string;
export type Manualscopes = ManualEditScope[];
export type Mode1 = "structured" | "digest" | "imported";
export type Admission = "provisional" | "accepted" | "rejected" | "uncertain";
export type Evidence1 = SourceSpan[];
export type Fieldkey3 = string;
export type Id19 = string;
export type Itemhandle3 = string;
export type Ownerrelations = Relation[];
export type Proposalhash = string;
export type Rawinput2 = string;
export type Receiptids = string[];
export type Observations = Observation[];
export type Sourceid2 = string;
export type Sourcerevision1 = number;
export type Text7 = string;
export type Unitid2 = string;
export type Unitrevision1 = number;
export type Evidence2 = EvidenceSpan[];
export type Id20 = string;
export type Kind4 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision5 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected1 = boolean;
export type Value = string | null;
export type Origin1 = "source" | "user";
export type Revision6 = number;
export type Usercorrected2 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence3 = EvidenceSpan[];
export type Id21 = string;
export type Kind5 = "detail";
export type Label4 = string;
export type Origin2 = "source" | "user";
export type Revision7 = number;
export type Usercorrected3 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id22 = string;
export type Kind6 = "employment";
export type Origin3 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision8 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Evidence5 = EvidenceSpan[];
export type Id23 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision9 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected5 = boolean;
export type Value1 = boolean | null;
export type Revision10 = number;
export type Periods1 = WorkingPeriod[];
export type Revision11 = number;
export type Usercorrected6 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id24 = string;
export type Jobid1 = string;
export type Kind7 = "subproject";
export type Origin4 = "source" | "user";
export type Periods2 = WorkingPeriod[];
export type Revision12 = number;
export type Usercorrected7 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id25 = string;
export type Jobid2 = string | null;
export type Kind8 = "technology";
export type Origin5 = "source" | "user";
export type Revision13 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected8 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id26 = string;
export type Kind9 = "education";
export type Origin6 = "source" | "user";
export type Revision14 = number;
export type Usercorrected9 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id27 = string;
export type Kind10 = "language";
export type Origin7 = "source" | "user";
export type Revision15 = number;
export type Usercorrected10 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id28 = string;
export type Kind11 = "certification";
export type Origin8 = "source" | "user";
export type Revision16 = number;
export type Usercorrected11 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id29 = string;
export type Jobid3 = string | null;
export type Kind12 = "claim";
export type Origin9 = "source" | "user";
export type Revision17 = number;
export type Subprojectid1 = string | null;
export type Usercorrected12 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id30 = string;
export type Jobid4 = string | null;
export type Kind13 = "metric";
export type Origin10 = "source" | "user";
export type Revision18 = number;
export type Subprojectid2 = string | null;
export type Usercorrected13 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision19 = number;
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
export type Id31 = string;
export type Jobid5 = string | null;
export type Kind14 = "leadership";
export type Origin11 = "source" | "user";
export type Revision20 = number;
export type Subprojectid3 = string | null;
export type Usercorrected15 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision21 = number;
export type Status6 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Action1 = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence14 = EvidenceSpan[];
export type Id32 = string;
export type Kind15 = "unresolved";
export type Origin12 = "source" | "user";
export type Revision22 = number;
export type Status7 = "unresolved" | "pending" | "conflict";
export type Usercorrected17 = boolean;
export type Records2 = (
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
export type Revision23 = number;
export type Schemaversion13 = 2;
export type Actionid2 = string;
export type Orderindex = number;
export type Recordid2 = string;
export type Revision24 = number;
export type Tombstones = RecordTombstone[];
export type Allowtextrewrite = boolean;
export type Category1 =
  ("identity" | "contacts" | "summary" | "experience" | "education" | "skills" | "languages" | "other") | null;
/**
 * @maxItems 1000
 */
export type Duplicateof = string[];
export type Id33 = string;
export type Kind16 = "paragraph" | "heading" | "section" | "bullet_list" | "duplicate" | "source_only";
export type Listitem = boolean;
export type Modelblock = boolean;
export type Reason = string | null;
export type Region2 = "header" | "sidebar" | "main";
/**
 * @maxItems 1000
 */
export type Sourcekeys = string[];
export type Text8 = string | null;
export type Title4 = string | null;
/**
 * @maxItems 5000
 */
export type Blocks3 = ImportBlock[];
export type Id34 = string;
export type Record = (ImportEmployment | ImportEducation | ImportTechnology | ImportLanguage) | null;
export type Employer = string;
export type Kind17 = "employment";
export type End2 = string;
export type Present = boolean;
export type Start2 = string;
/**
 * @maxItems 40
 */
export type Periods3 = ImportPeriod[];
export type Role2 = string;
export type Display = string;
export type Experience = string;
export type Technical1 = boolean | null;
/**
 * @maxItems 100
 */
export type Technologies = (string | ImportSkill)[];
export type Completion = string;
export type Institution = string;
export type Kind18 = "education";
export type Qualification = string;
export type Specialty = string;
export type Display1 = string;
export type Experience1 = string;
export type Kind19 = "technology";
export type Technical2 = boolean | null;
export type Kind20 = "language";
export type Language = string;
export type Level = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys1 = string[];
export type Text9 = string;
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
export type Name1 = string;
/**
 * @maxItems 1000
 */
export type Sourcekeys2 = string[];
export type Title5 = string;
export type Batchid1 = string;
export type Requestsha2561 = string;
export type Sequence7 = number;
/**
 * @maxItems 128
 */
export type Receipts = ImportReceipt[];
export type Runid10 = string;
export type Sequence8 = number;
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
export type Dependencies1 = DependencyStamp[];
export type Errorcode1 = string | null;
export type Id35 = string;
export type Kind21 =
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
export type Id36 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id37 = string;
export type Origin13 = "user";
export type Revision25 = number;
export type Text10 = string;
export type Unitid3 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision26 = number;
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id38 = string;
export type Column = number | null;
export type Index = number;
export type Kind22 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row2 = number | null;
export type Order1 = number;
export type Representedfactids = string[];
export type Revision27 = number;
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
export type Text11 = string;
export type Units = SourceUnit[];
export type Code2 = string;
export type Page2 = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources1 = Source[];
export type Admittedat = string | null;
export type Discoveryattemptid = string;
export type Discoveryhash = string;
export type Itemhandle4 = string;
export type Key = string;
export type Operationid = string;
export type Recordid3 = string;
export type Semantictype2 = string;
export type Taskid = string;
export type Allocations = HandleAllocation[];
export type Authorizationid = string | null;
export type Evidencehash = string | null;
export type State2 = "pending" | "verified" | "unknown";
export type Witness = string | null;
export type Dispatchedat = string | null;
export type Errorcode2 = string | null;
export type Id39 = string;
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
export type State3 = "reserved" | "dispatch_started" | "returned" | "outcome_unknown" | "reconciled" | "released";
export type Taskid1 = string;
export type Cachedinputtokens1 = number | null;
export type Complete = boolean;
export type Inputtokens1 = number | null;
export type Outputtokens1 = number | null;
export type Attempts = ImportAttempt[];
export type Authorityhash = string;
export type Authorizedat = string;
export type Dependencyhash = string;
export type Id40 = string;
export type Kind23 = "start" | "resume";
export type State4 = "active" | "cancelled";
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
export type Recordid4 = string;
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
export type Id41 = string;
export type Packagehash3 = string;
export type Presentationhash1 = string;
export type Publicationintentid = string | null;
export type Rendererhash = string;
export type State5 = "pending" | "running" | "completed" | "failed";
export type Exportattempts = ExportAttempt[];
export type Authorityhash2 = string;
export type Authorizationid1 = string;
export type Candidatehash = string;
export type Coveragehash = string;
export type Dependencyhash2 = string;
export type Documenthash2 = string;
export type Expiresat1 = string;
export type Factshash2 = string;
export type Id42 = string;
export type Issueshash = string;
export type Operationid2 = string;
export type Packagehash4 = string;
export type Sourcehash = string;
export type Startedat1 = string;
export type Finalizationhistory = FinalizationCandidate[];
export type Id43 = string;
export type Inferenceclosed = boolean;
export type Blockids1 = string[];
export type Category2 = "content_violation" | "uncertain_interpretation" | "check_not_completed";
export type Code3 = string;
export type Id44 = string;
export type Importedfingerprint = string;
export type Lifecycleid = string;
export type Message1 = string;
export type Retiredbyaction = string | null;
export type Reviewinputhash = string | null;
export type Ruleid = string | null;
export type State6 = "active" | "retired";
export type Targetids = string[];
export type Taskid2 = string;
export type Issues1 = ImportIssue[];
export type Lastobservedat = string | null;
export type Projectid9 = string;
export type Admittedcellids = string[];
export type Admittedrelationids = string[];
export type Appliedreceiptid = string | null;
export type Attemptid1 = string;
export type Fieldkey4 = string;
export type Pointer = string;
export type Text12 = string;
export type Droppedvalues = DroppedValue[];
export type Errors = string[];
export type Id45 = string;
export type Inputhash1 = string;
export type Attemptid2 = string;
export type Children = string[];
export type Kind24 = "add" | "split" | "merge";
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
export type Fieldkey5 = string;
export type Item = DiscoverySelector | HandleSelector;
export type Key2 = string;
export type Kind25 = "discovery_key";
export type Itemhandle6 = string;
export type Kind26 = "handle";
export type Pointer2 = string;
export type Fields1 = ProposalField[];
export type Children1 = string[];
export type Kind27 = "add" | "split" | "merge";
export type Parents1 = string[];
export type Lineage2 = ProposalLineage[];
export type Evidence16 = SourceSpan[];
export type Kind28 = "owned_by" | "extension_of" | "related_to";
export type Relation1 = RelationDiscoverySelector | ExistingRelationSelector;
export type Key3 = string;
export type Kind29 = "discovery_key";
export type Kind30 = "relation_id";
export type Relationid = string;
export type Subject = DiscoverySelector | HandleSelector;
export type Target = DiscoverySelector | HandleSelector;
export type Relations2 = ProposalRelation[];
export type Schemaversion14 = 1;
export type Effectivecellids1 = string[];
export type Evidence17 = SourceSpan[];
export type Fieldkey6 = string;
export type Itemhandle7 = string;
export type Pointer3 = string;
export type Resolvedfields = FieldSidecar[];
export type Resolvedrelations = Relation[];
export type State7 = "invalid" | "provisional" | "accepted" | "rejected";
export type Proposals = ProposalRecord[];
export type Errorcode4 = string | null;
export type Intentid = string | null;
export type State8 = "pending" | "saved" | "failed_before_replacement" | "outcome_unknown" | "cancelled";
export type Workspacehash = string | null;
export type Attemptid3 = string;
export type Completedat = string;
export type Ruleid1 = string;
export type Targetid1 = string;
export type Expectedchecks = CheckTarget[];
export type Id46 = string;
export type Actionable = boolean;
export type Disposition2 = "satisfied" | "violation" | "uncertain";
export type Evidence18 = SourceSpan[];
export type Reason1 = string;
export type Ruleid2 = string;
export type Targetid2 = string;
export type Results = ReviewDisposition[];
export type Reviewinputhash1 = string;
export type Receipts1 = ReviewReceipt[];
export type Discoveryattemptid1 = string;
export type Key4 = string;
export type Kind31 = "owned_by" | "extension_of" | "related_to";
export type Operationid3 = string;
export type Relationid1 = string;
export type Subjectid1 = string;
export type Targetid3 = string;
export type Taskid3 = string;
export type Relationallocations = RelationAllocation[];
export type Attemptid4 = string;
export type Id47 = string;
export type Inputhash2 = string;
export type Allowtextrewrite2 = boolean;
export type Effectivecells = ExtensionCell[];
export type Ref = string;
export type Text13 = string;
export type Evidence19 = EvidenceOption[];
export type Handlemap = (HandleAllocation | CapturedItemIdentity)[];
export type Occurrenceindependent = boolean;
export type Packagehash5 = string;
export type Proposalhash2 = string;
export type Protocol = "template_import_v1";
export type Relations3 = Relation[];
export type Id48 = string;
export type Kind32 =
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
export type Schemaversion15 = 1 | 2;
export type Actionable1 = boolean;
export type Disposition3 = "satisfied" | "violation" | "uncertain";
export type Evidence20 = SourceSpan[];
export type Origin14 = "verbatim" | "reused";
export type Reason2 = string;
export type Ruleid3 = string;
export type Targetid4 = string;
export type Settled = SettledCheck[];
export type Sourcespans = SourceSpan[];
export type Targets = CheckTarget[];
export type Reviewinputs = ReviewInputRecord[];
export type Schemaversion16 = 1;
export type State9 =
  "captured" | "processing" | "cleanup_pending" | "finalizing" | "published" | "cancelled" | "failed" | "fenced";
export type Capturedat = string;
export type Id49 = string;
export type Inputhash3 = string;
export type Taskid4 = string;
export type Taskinputs = TaskInputRecord[];
export type Disposition4 = "admitted" | "derived" | "source_fallback" | "empty";
export type Id50 = string;
export type Inputhash4 = string;
export type Issueids = string[];
export type Itemhandles = string[];
export type Sourcespans1 = SourceSpan[];
export type Taskid5 = string;
export type Taskresults = TaskResultRecord[];
export type Allowedhandles = string[];
export type Attemptids = string[];
export type Blockid2 = string;
export type Dependencies2 = string[];
export type Index1 = number;
export type Origin15 = "outline" | "review";
/**
 * @minItems 1
 */
export type Parts = [EntryPart, ...EntryPart[]];
export type Spans = SourceSpan[];
export type Title6 = string;
export type Spans1 = SourceSpan[];
export type Title7 = string;
export type Expectedchecks1 = CheckTarget[];
export type Id51 = string;
export type Inputhash5 = string;
export type Issueids1 = string[];
export type Kind33 = "extract" | "rewrite" | "derive" | "source_copy" | "outline_review";
export type Operationid4 = string;
export type Parenttaskid = string | null;
export type Proposalhash3 = string | null;
export type Receiptids1 = string[];
export type State10 =
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
export type Id52 = string;
export type Mimetype1 = string;
export type Path1 = string;
export type Role3 = "font" | "logo" | "icon" | "catalog";
export type Sha2561 = string;
export type Size4 = number;
export type Assets = StoredAsset[];
export type Dependencyorder = number;
export type Id53 = string;
export type Serveronly = string[];
export type Blocks4 = CompiledBlock[];
export type Compilerversion = string;
export type Confighash = string;
export type Embedding = "allowed" | "not_applicable";
export type Id54 = string;
export type MimeType = string;
export type Path2 = string;
export type Role4 = "font" | "logo" | "icon" | "catalog";
export type Assets1 = AssetDeclaration[];
export type Field1 = string;
export type ItemPointer = string | null;
export type Pointer4 = string;
export type Kind34 = "owned_by" | "extension_of" | "related_to";
export type SubjectPointer = string;
export type SemanticType = string;
export type Bindings = Binding[];
export type Checks = Check[];
export type DependsOn = string[];
export type Effort1 = ("low" | "medium" | "high") | null;
export type Extract = string[];
export type Id55 = string;
export type Mode2 = "model" | "derived" | "source_copy";
export type Operation = string | null;
/**
 * Outline the list first, then extract its entries in parallel groups. A model list without item limits only.
 */
export type PerEntry = boolean;
export type Fields3 = string[];
export type Instructions1 = string[];
export type Id56 = string;
export type Kind35 = "source" | "fact_type" | "block" | "operation";
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
export type Id57 = string;
export type Kind36 = "owned_by" | "extension_of" | "related_to";
export type TargetTypes = string[];
export type Relations4 = RelationDeclaration[];
export type SchemaVersion = string;
export type FactTypes = FactType[];
export type Extract1 = string[];
export type Permission = "allowTextRewrite";
export type Rewrite1 = string[];
export type DependsOn1 = string[];
export type Id58 = string;
export type Inputs = InputRef[];
export type Kind37 = "partition_employment";
export type Compact = string;
export type Detailed = string;
export type Years = number;
export type Version2 = 1;
export type DependsOn2 = string[];
export type Id59 = string;
export type Inputs1 = InputRef[];
export type Kind38 = "select_role_branch";
export type Field3 = string;
export type SemanticType1 = string;
export type Matched = string;
export type Otherwise = string;
export type RoleFamilies = string[];
export type Version3 = 1;
export type DependsOn3 = string[];
export type Id60 = string;
export type Inputs2 = InputRef[];
export type Kind39 = "assign_skills";
export type Groups = string[];
export type UncertainGroup = string;
export type Version4 = 1;
export type DependsOn4 = string[];
export type Id61 = string;
export type Inputs3 = InputRef[];
export type Kind40 = "format_period";
export type Separator1 = string;
export type Version5 = 1;
export type DependsOn5 = string[];
export type Id62 = string;
export type Inputs4 = InputRef[];
export type Kind41 = "preserve_stated_text";
export type Version6 = 1;
export type Operations1 = (
  PartitionOperation | RoleOperation | SkillsOperation | PeriodOperation | PreserveOperation
)[];
export type SchemaVersion1 = 3;
export type RetainOriginal = true;
export type RetainUnmappedFacts = true;
export type DefaultLocale = string;
export type Id63 = string;
export type Name2 = string;
export type Revision28 = string;
export type Id64 = string;
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
export type Revision29 = string;
export type Schemaversion17 = 1;
export type Warnings1 = string[];
export type Height3 = number;
export type Id65 = string;
export type Mimetype2 = "image/png" | "image/jpeg";
export type Path3 = string;
export type Sha2562 = string;
export type Size5 = number;
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
export type Code4 = boolean;
export type Italic2 = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text14 = string;
export type Type8 = "text";
export type Content1 = PresentedText[];
export type Href = string;
export type Type9 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Cellid2 = string | null;
export type Citations1 = SourceSpan[];
export type Complete1 = boolean;
export type Fieldkey7 = string;
export type Occurrenceid = string;
export type Recordid5 = string;
export type Syncedfactrevision = number;
export type Text15 = string;
export type Type10 = "fact_field";
export type Content2 = (PresentedText | FieldOccurrence)[];
export type Href1 = string;
export type Cellid3 = string;
export type Fieldkey8 = string;
export type Occurrenceid1 = string;
export type Recordid6 = string;
export type Type11 = "bound_link";
export type Citations2 = SourceSpan[];
export type Fragmentid = string;
export type Occurrenceid2 = string;
export type Scopeid = string;
export type Text16 = string;
export type Type12 = "manual_scope";
export type Content = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id66 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Icon1 = string | null;
export type Manualorder = boolean;
export type Presentation = "standard" | "focus" | "row";
export type Recordid7 = string | null;
export type Textcolor1 = string;
export type Evidence21 = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id67 = string;
export type Kind42 = "citation";
export type Recordid8 = string;
export type Fieldkey9 = string;
export type Id68 = string;
export type Kind43 = "field_binding";
export type Recordid9 = string;
export type Id69 = string;
export type Kind44 = "working_owner";
export type Recordid10 = string;
/**
 * @minItems 1
 */
export type Evidence22 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id70 = string;
export type Kind45 = "source";
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision30 = number;
export type Type13 = "section";
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
export type Id71 = string;
export type Alignment4 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Height4 = number;
export type Width5 = number;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision31 = number;
export type Type14 = "image";
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
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor2 = string;
export type Colspan = number;
export type Content4 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
export type Id72 = string;
export type Revision32 = number;
export type Rowspan = number;
export type Cells1 = TemplateTableCell[];
export type Id73 = string;
export type Rows = TemplateTableRow[];
export type Id74 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision33 = number;
export type Type15 = "table";
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
export type Id75 = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision34 = number;
export type Type16 = "divider";
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
export type Id76 = string;
export type Backgroundcolor4 = string;
export type Language1 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision35 = number;
export type Type17 = "code";
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
export type Id77 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision36 = number;
export type Type18 = "quote";
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
export type Id78 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision37 = number;
export type Type19 = "toggle_list";
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
export type Id79 = string;
export type Alignment7 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision38 = number;
export type Type20 = "check_list";
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
export type Id80 = string;
export type Alignment8 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start3 = number | null;
export type Textcolor4 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision39 = number;
export type Type21 = "numbered_list";
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
export type Id81 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision40 = number;
export type Type22 = "bullet_list";
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
export type Id82 = string;
export type Alignment9 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level1 = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision41 = number;
export type Type23 = "heading";
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
export type Id83 = string;
export type Provenance12 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision42 = number;
export type Type24 = "paragraph";
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
export type Id84 = string;
export type Revision43 = number;
export type Role5 = "header" | "sidebar" | "main";
export type Revision44 = number;
export type Schemaversion18 = 2;
export type Evidence23 = EvidenceSpan[];
export type Id85 = string;
export type Rawtext5 = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Attemptid5 = string;
export type Id86 = string;
export type Path4 = string;
export type Sha2563 = string;
export type Size6 = number;
export type Assets3 = TemplateRenderAsset[];
export type Documenthash3 = string;
export type Factshash3 = string;
export type Packagehash7 = string;
export type Presentationhash2 = string;
export type Renderinputversion1 = 1;
export type Id87 = string;
export type Sha2564 = string;
export type Version7 = string;
export type Schemaversion19 = 1;
export type Exportinputs = TemplateExportCapture[];
export type Exports = ExportAttempt[];
export type Blockids2 = string[];
export type Disposition5 = "accepted" | "fallback" | "source_only" | "multiple_views";
export type Itemhandle8 = string | null;
export type Reason3 = string | null;
export type Importcoverage = SpanCoverage[];
export type Operationid5 = string;
export type Sha2565 = string;
export type Importhistory = ImportHistoryRef[];
export type Importissues = ImportIssue[];
export type Operations2 = RichOperation[];
export type Projectid10 = string;
export type Documentrevision4 = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id88 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision45 = number;
export type Schemaversion20 = 6;
export type Sources2 = Source[];
export type Templateoperations1 = ImportOperation[];
export type Projectid11 = string;
export type Projectrevision2 = number;
export type Markdown = string;
export type Revision46 = number;
export type Sha2566 = string;
export type Schemaversion21 = 7;
export type Actionid4 = string;
export type Blockids3 = string[];
export type Actionid5 = string;
export type Actiontoken = number;
export type Dependencies3 = DependencyStamp[];
export type Sessionid = string;
export type Dependencies4 = DependencyStamp[];
export type Errorcode5 = string | null;
export type Factids = string[];
export type Fieldkeys1 = string[];
export type Id89 = string;
export type Instruction = string | null;
export type Kind46 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
export type Lifecycleid1 = string;
export type Beforeownerid = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Movedoccurrenceids = [string, ...string[]];
export type Proposedownerid = string;
export type Recordid11 = string;
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
export type Kind47 = "put_block";
export type Parentid1 = string;
export type Beforerevision1 = number;
export type Blockid3 = string;
export type Kind48 = "remove_block";
export type Afterid2 = string | null;
export type Beforerevision2 = number;
export type Blockid4 = string;
export type Kind49 = "move_block";
export type Parentid2 = string;
export type Beforerevision3 = number;
export type Blockid5 = string;
export type Cellid4 = string | null;
export type Content14 = (PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End3 = number;
export type Field4 = "content" | "caption";
export type Flankbindings = FlankBinding[] | null;
export type Fragmentid1 = string;
export type Role6 = "prefix" | "suffix";
export type Source1 = FieldFlankSource | ManualScopeFlankSource;
export type Bindingid1 = string;
export type Kind50 = "field";
export type Fragmentid2 = string;
export type Kind51 = "manual_scope";
export type Sourceend = number;
export type Sourcestart = number;
export type Kind52 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start4 = number;
export type Beforerevision4 = number | null;
export type Kind53 = "put_record";
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
export type Kind54 = "remove_record";
export type Recordid12 = string;
export type Beforerevision6 = number | null;
export type Kind55 = "put_extension";
export type Beforerevision7 = number;
export type Kind56 = "remove_extension";
export type Recordid13 = string;
export type Beforerevision8 = number | null;
export type Kind57 = "put_relation";
export type Beforerevision9 = number;
export type Kind58 = "remove_relation";
export type Relationid3 = string;
export type Kind59 = "put_manual_scope";
export type Afterscopeid = string | null;
export type Beforescopeid = string | null;
export type Cellid5 = string;
export type Kind60 = "set_builtin_manual_scope";
export type Actionid6 = string;
export type Afterlifecycleid = string;
export type Afterstate = "active" | "retired";
export type Beforelifecycleid = string;
export type Beforestate = "active" | "retired";
export type Importedfingerprint1 = string;
export type Issueid = string;
export type Kind61 = "set_issue_state";
export type Afterblockids = string[];
export type Beforeblockids = string[];
export type Kind62 = "set_authored_anchors";
export type Target1 = IssueAnchorTarget | CoverageAnchorTarget;
export type Beforelifecycleid1 = string;
export type Beforestate1 = "active" | "retired";
export type Importedfingerprint2 = string;
export type Issueid1 = string;
export type Kind63 = "issue";
export type Coverageidentityhash = string;
export type Coverageindex = number;
export type Coveragesequencehash = string;
export type Kind64 = "coverage";
export type Aftersemantichash = string;
export type Beforerevision10 = number;
export type Beforesemantichash = string;
export type Blockid6 = string;
export type Kind65 = "restore_authored_block_patch";
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Patch = [
  PatchSet | PatchInsert | PatchRemove | PatchSpliceText,
  ...(PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[]
];
export type Kind66 = "set";
export type Pointer5 = string;
export type Valuewire = string;
export type Kind67 = "insert";
export type Pointer6 = string;
export type Valuewire1 = string;
export type Kind68 = "remove";
export type Pointer7 = string;
export type Beforetexthash = string;
export type End4 = number;
export type Kind69 = "splice_text";
export type Pointer8 = string;
export type Start5 = number;
export type Text17 = string;
export type Blockid7 = string;
export type Cellid6 = string | null;
export type Field5 = "content" | "caption";
export type Inlineindex = number;
export type After = ScopeDisplayBinding | LiteralDisplayBinding;
export type Fragmentid3 = string;
export type Kind70 = "manual_scope";
export type Occurrenceid3 = string;
export type Scopeid1 = string;
export type Kind71 = "literal";
export type Beforehash = string;
/**
 * @maxItems 1000
 */
export type Assignments = ScopeDisplayAssignment[];
export type Kind72 = "set_manual_scope_displays";
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
export type Blockid8 = string;
export type Cellid7 = string | null;
export type Field6 = "content" | "caption";
export type Fragmenthash = string;
export type Fragmentid4 = string;
export type Occurrenceid4 = string;
export type Scopehash = string;
export type Scopeid2 = string;
/**
 * @maxItems 1000
 */
export type Sources3 = ScopeDisplaySource[];
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
export type Schemaversion22 = 2;
export type Blockid9 = string;
export type Cellid8 = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids4 = [string, ...string[]];
export type Kind73 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Status9 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Actionid7 = string;
export type Blockids5 = string[];
export type Dependencies5 = DependencyStamp[];
export type Errorcode6 = string | null;
export type Factids1 = string[];
export type Fieldkeys2 = string[];
export type Id90 = string;
export type Instruction1 = string | null;
export type Kind74 = "completion" | "rewrite" | "reconciliation" | "conflict" | "panel";
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
export type Text18 = string;
export type Type25 = "text";
export type Content16 = StyledText[];
export type Href2 = string;
export type Type26 = "link";
export type Bindingid2 = string;
export type Bindingrootid1 = string | null;
export type Fieldkey10 = string;
export type Recordid14 = string;
export type Syncedfactrevision1 = number;
export type Text19 = string;
export type Type27 = "fact_field";
export type Content15 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id91 = string;
export type Provenance13 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision47 = number;
export type Type28 = "section";
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
export type Id92 = string;
export type Alignment10 = "left" | "center" | "right";
export type Alt1 = string;
export type Assetid1 = string;
export type Caption1 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height5 = number;
export type Width6 = number;
export type Provenance14 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision48 = number;
export type Type29 = "image";
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
export type Alignment11 = "left" | "center" | "right" | "justify";
export type Backgroundcolor8 = string;
export type Colspan1 = number;
export type Content18 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id93 = string;
export type Revision49 = number;
export type Rowspan1 = number;
export type Cells2 = TableCell[];
export type Id94 = string;
export type Id95 = string;
export type Provenance15 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision50 = number;
export type Type30 = "table";
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
export type Id96 = string;
export type Provenance16 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision51 = number;
export type Type31 = "divider";
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
export type Id97 = string;
export type Provenance17 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision52 = number;
export type Type32 = "code";
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
export type Id98 = string;
export type Provenance18 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision53 = number;
export type Type33 = "quote";
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
export type Id99 = string;
export type Provenance19 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision54 = number;
export type Type34 = "toggle_list";
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
export type Id100 = string;
export type Provenance20 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision55 = number;
export type Type35 = "check_list";
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
export type Id101 = string;
export type Provenance21 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision56 = number;
export type Type36 = "numbered_list";
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
export type Id102 = string;
export type Provenance22 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision57 = number;
export type Type37 = "bullet_list";
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
export type Id103 = string;
export type Provenance23 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision58 = number;
export type Type38 = "heading";
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
export type Id104 = string;
export type Provenance24 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision59 = number;
export type Type39 = "paragraph";
export type Keepchildren1 = boolean;
export type Kind75 = "put_block";
export type Parentid3 = string;
export type Beforerevision12 = number;
export type Blockid10 = string;
export type Cellid9 = string | null;
export type Content28 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End5 = number;
export type Field7 = "content" | "caption";
export type Kind76 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start6 = number;
/**
 * @maxItems 1000
 */
export type Proposedsteps1 = (PutBlock | RemoveBlock | MoveBlock | ReplaceInlineRange | PutRecord | RemoveRecord)[];
export type Ready1 = boolean;
export type Rewriteresult1 = string | null;
export type Rewritesource1 = string | null;
export type Status10 = "pending" | "failed" | "conflict" | "applied" | "stale";
export type Syncrecords = (TemplateSyncRecord | RichSyncRecord)[];
export type Title8 = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;
export type Blockids6 = string[];
export type Code5 = string;
export type Count = number;
export type Sourceid3 = string;
export type Sourcerevision2 = number;
export type Unitid4 = string;
export type Unitrevision2 = number;
export type Evidence24 = Evidence25[];
export type Id105 = string;
export type Page3 = number | null;
export type Sourceid4 = string;
export type Locations = WarningLocation[];
export type Recordids = string[];
export type Warnings2 = RichWarning[];
export type Revision60 = number;
export type Schemaversion23 = 1;
export type Appliedrevision = number | null;
export type Baserevision = number;
export type Conversationid7 = string;
export type Createdat2 = string;
export type Expectedactionid = string | null;
export type Id106 = string;
export type Kind77 = "edit" | "history" | "action";
export type Blockid11 = string;
export type Cellid10 = string | null;
export type Field8 = "content" | "caption";
export type Op = "set_block_text";
export type Text20 = string;
export type Blockid12 = string;
export type Cellid11 = string | null;
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
export type Kind78 = "paragraph" | "heading" | "bullet" | "numbered";
export type Level2 = 1 | 2 | 3;
export type Text21 = string;
export type Op2 = "insert_blocks";
export type Parentid4 = string | null;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Blockids7 = [string, ...string[]];
export type Op3 = "delete_blocks";
export type Afterblockid1 = string | null;
export type Blockid13 = string;
export type Op4 = "move_block";
export type Parentid5 = string | null;
export type Alignment12 = ("left" | "center" | "right" | "justify") | null;
export type Backgroundcolor9 = string | null;
export type Blockid14 = string;
export type Kind79 = ("paragraph" | "heading" | "bullet" | "numbered") | null;
export type Level3 = (1 | 2 | 3) | null;
export type Op5 = "format_block";
export type Textcolor6 = string | null;
export type Field10 = string;
export type Op6 = "update_fact";
export type Recordid15 = string;
export type Value3 = string;
export type Jobid6 = string | null;
export type Kind80 = "candidate" | "employment" | "technology" | "education" | "language" | "claim" | "period";
export type Op7 = "create_fact";
export type Targetid5 = string | null;
export type Op8 = "delete_fact";
export type Recordid16 = string;
export type Direction = "undo" | "redo";
export type Op9 = "history";
export type Action2 = "rename" | "formatting_date" | "archive" | "restore" | "delete";
export type Op10 = "action";
export type Targetid6 = string | null;
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
export type Label5 = string;
export type Target2 = string;
/**
 * @maxItems 200
 */
export type Preview = PreviewEntryV1[];
export type Projectid12 = string;
export type Runid11 = string;
export type Schemaversion24 = 1;
export type State11 = "draft" | "applied" | "discarded";
export type Summary = string;
export type Updatedat1 = string;
export type Model1 = string;
export type Provider = string | null;
export type State12 = "unverified" | "verified" | "incompatible";
/**
 * @maxItems 100
 */
export type Models = ModelChoiceV1[];
export type Ready2 = boolean;
/**
 * @maxItems 32
 */
export type Tools = string[];
export type Code6 = string;
/**
 * @maxItems 20
 */
export type Detail =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
export type Webavailable = boolean;
/**
 * @maxItems 100
 */
export type Items = AssistantChangeProposalV1[];
export type Createdat3 = string;
export type Id107 = string;
export type Title9 = string;
export type Updatedat2 = string;
/**
 * @maxItems 100
 */
export type Items1 = AssistantConversationV1[];
/**
 * @maxItems 500
 */
export type Events = AgentEvent[];
export type Next = number;
export type Allowedits1 = boolean;
export type Allowweb = boolean;
export type Baserevision1 = number;
export type Clientrequestid1 = string;
export type Conversationid8 = string;
export type Createdat4 = string;
export type Finishedat = string | null;
export type Id108 = string;
export type Model2 = string;
export type Projectid13 = string;
export type State13 = "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Filename = string;
export type Format = "docx" | "foldcv";
export type Id109 = string;
export type Size7 = number;
export type Url1 = string;
/**
 * @maxItems 10
 */
export type Files =
  | []
  | [AssistantFileV1]
  | [AssistantFileV1, AssistantFileV1]
  | [AssistantFileV1, AssistantFileV1, AssistantFileV1]
  | [AssistantFileV1, AssistantFileV1, AssistantFileV1, AssistantFileV1]
  | [AssistantFileV1, AssistantFileV1, AssistantFileV1, AssistantFileV1, AssistantFileV1]
  | [AssistantFileV1, AssistantFileV1, AssistantFileV1, AssistantFileV1, AssistantFileV1, AssistantFileV1]
  | [
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1
    ]
  | [
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1
    ]
  | [
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1
    ]
  | [
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1,
      AssistantFileV1
    ];
/**
 * @maxItems 200
 */
export type Findings1 = AgentFinding[];
/**
 * @maxItems 200
 */
export type Messages = AgentMessage[];
/**
 * @maxItems 20
 */
export type Runs =
  | []
  | [AssistantRunV1]
  | [AssistantRunV1, AssistantRunV1]
  | [AssistantRunV1, AssistantRunV1, AssistantRunV1]
  | [AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1]
  | [AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1]
  | [AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1]
  | [AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1, AssistantRunV1]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ]
  | [
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1,
      AssistantRunV1
    ];
/**
 * @maxItems 100
 */
export type Sources4 = AgentWebSource[];
export type Allowedits2 = boolean;
export type Allowweb1 = boolean;
export type Clientrequestid2 = string;
export type Message2 = string;
/**
 * @maxItems 100
 */
export type Blockids8 = string[];
export type Text22 = string;
/**
 * @maxItems 20
 */
export type Items2 =
  | []
  | [AssistantSkillV1]
  | [AssistantSkillV1, AssistantSkillV1]
  | [AssistantSkillV1, AssistantSkillV1, AssistantSkillV1]
  | [AssistantSkillV1, AssistantSkillV1, AssistantSkillV1, AssistantSkillV1]
  | [AssistantSkillV1, AssistantSkillV1, AssistantSkillV1, AssistantSkillV1, AssistantSkillV1]
  | [AssistantSkillV1, AssistantSkillV1, AssistantSkillV1, AssistantSkillV1, AssistantSkillV1, AssistantSkillV1]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ]
  | [
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1,
      AssistantSkillV1
    ];
export type Description = string;
export type Id110 = string;
export type Title10 = string;
export type Available = boolean;
export type Downloadedbytes = number;
export type Error =
  | (
      | "unsafe_directory"
      | "busy"
      | "cancelled"
      | "unsupported_platform"
      | "download_failed"
      | "invalid_package"
      | "checksum_failed"
      | "install_failed"
      | "incompatible_release"
    )
  | null;
export type Installed = string | null;
export type Latest = string | null;
export type State14 = "idle" | "downloading" | "verifying" | "extracting" | "ready" | "failed" | "cancelled";
export type Totalbytes = number;
export type Update = boolean;
export type Clientcaptureid = string;
export type Editortoken2 = string;
export type Selection = ClipboardRangeSelection | ClipboardBlocksSelection;
export type Kind81 = "range";
export type Beforerevision13 = number;
export type Blockid15 = string;
export type Cellid12 = string | null;
export type End6 = number;
export type Field11 = "content" | "caption";
export type Insertiontarget = (FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget) | null;
export type Bindingid3 = string;
export type Kind82 = "field";
export type Kind83 = "literal";
export type Fragmentid5 = string;
export type Kind84 = "manual_scope";
export type Start7 = number;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Blocks8 = [BlockTarget, ...BlockTarget[]];
export type Beforerevision14 = number;
export type Blockid16 = string;
export type Kind85 = "blocks";
export type Confirmed = true;
export type Baserevision2 = number;
export type Editortoken3 = string;
export type Clientmutationid3 = string;
/**
 * @minItems 1
 * @maxItems 1
 */
export type Operations3 = [
  | ReplaceText
  | SetMarks
  | SplitBlock
  | MergeBlocks
  | InsertParagraph
  | CopyBlocks
  | CopyFragment
  | PasteInline
  | PasteBlocks
  | MoveBlock1
  | RemoveOccurrences
  | DeleteEntity
  | BuiltinPanel
  | FormatBlocks
  | ResolveTemplateSync
  | SetLinkTarget
];
export type Kind86 = "replace_text";
export type Opid = string;
export type Text23 = string;
export type Kind87 = "set_marks";
export type Opid1 = string;
export type Beforerevision15 = number;
export type Blockid17 = string;
export type Kind88 = "split_block";
export type Offset1 = number;
export type Opid2 = string;
export type Kind89 = "merge_blocks";
export type Leadingid = string;
export type Leadingrevision = number;
export type Opid3 = string;
export type Trailingid = string;
export type Trailingrevision = number;
export type Contextblockid = string;
export type Contextrevision = number;
export type Kind90 = "insert_paragraph";
export type Opid4 = string;
export type Afterid4 = string | null;
export type Parentid6 = string;
export type Text24 = string;
export type Kind91 = "copy_blocks";
export type Opid5 = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Sources5 = [BlockTarget, ...BlockTarget[]];
export type Kind92 = "copy_fragment";
export type Opid6 = string;
export type Kind93 = "paste_inline";
export type Opid7 = string;
export type Source2 = SameProjectClipboard | LiteralPaste;
export type Clipboardcaptureid = string;
export type Kind94 = "same_project";
export type Content29 = (StyledText | Hyperlink)[];
export type Kind95 = "literal";
export type Kind96 = "paste_blocks";
export type Opid8 = string;
export type Beforerevision16 = number;
export type Blockid18 = string;
export type Kind97 = "move_block";
export type Opid9 = string;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Blocks9 = [BlockTarget, ...BlockTarget[]];
export type Kind98 = "remove_occurrences";
export type Opid10 = string;
export type Beforerevision17 = number;
export type Kind99 = "delete_entity";
export type Opid11 = string;
export type Recordid17 = string;
export type Beforerecordid = string | null;
export type Documentrevision5 = number;
export type Factsrevision1 = number;
export type Groupid = string | null;
export type Jobid7 = string | null;
export type Operation2 =
  | "add"
  | "edit"
  | "remove"
  | "add_period"
  | "remove_period"
  | "clear_technologies"
  | "add_to_focus"
  | "remove_from_focus"
  | "move_technology"
  | "move_focus"
  | "set_focus_icon"
  | "add_technology_group";
export type Periodid1 = string | null;
export type Recordid18 = string | null;
export type Recordkind = ("candidate" | "employment" | "technology" | "education" | "language" | "claim") | null;
export type Kind100 = "builtin_panel";
export type Opid12 = string;
export type Contextblockid1 = string;
export type Kind101 = "format_blocks";
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
export type Targets1 = [BlockTarget, ...BlockTarget[]];
export type Beforelifecycleid3 = string;
export type Beforerecordhash1 = string;
export type Kind102 = "resolve_template_sync";
export type Opid14 = string;
export type Syncid1 = string;
export type Beforerevision18 = number;
export type Blockid19 = string;
export type Href3 = string;
export type Kind103 = "set_link_target";
export type Occurrenceid5 = string;
export type Opid15 = string;
export type Schemaversion25 = 1;
export type Editortoken4 = string;
export type Schemaversion26 = 1;
export type Editortoken5 = string;
export type Bytelength = number;
export type Byteref1 = string;
export type Bytesha2561 = string;
export type Code7 = "NO_TEXT" | "IMAGE" | "SHAPE" | "TEXT_BOX" | "UNSUPPORTED_CONTENT";
export type Column2 = number | null;
export type Kind104 = "page" | "paragraph" | "table_cell" | "header" | "footer" | "image" | "pasted";
export type Page4 = number | null;
export type Paragraph = number | null;
export type Part1 = string | null;
export type Row3 = number | null;
export type Table2 = number | null;
/**
 * @maxItems 5000
 */
export type Gaps = ExtractGap[];
export type Part2 = string;
export type Relationshipid = string;
export type Target3 = string;
/**
 * @maxItems 100
 */
export type Links1 = ExtractLink[];
export type Mimetype3 = string;
export type Originalname1 = string;
export type Pagecount = number | null;
export type Parser1 = string;
export type Parserversion1 = string;
export type Sourceid5 = string;
export type Sourcekind = "pdf" | "docx" | "txt" | "markdown" | "paste";
export type Id111 = string;
export type Order2 = number;
export type Text25 = string;
/**
 * @maxItems 5000
 */
export type Units1 = ExtractUnit[];
export type Baserevision3 = number;
export type Clientmutationid4 = string;
export type Direction1 = "undo" | "redo";
export type Editortoken6 = string;
export type Expectedactionid1 = string | null;
export type Allowtextrewrite3 = boolean;
export type Clientrequestid3 = string;
export type Effort2 = ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Kind105 = "start" | "resume" | "cancel";
export type Operationid6 = string | null;
export type Taskid6 = string | null;
export type Automaticanalysis = boolean;
/**
 * @maxItems 2
 */
export type Enabledproviders =
  [] | ["codex_cli" | "claude_cli"] | ["codex_cli" | "claude_cli", "codex_cli" | "claude_cli"];
export type Importminutes = number;
export type Projectmegabytes = number;
export type Rewritereasoningeffort =
  ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Schemaversion27 = 1;
export type Selectedfallbackmodel = string | null;
export type Selectedimportmodel = string | null;
export type Selectedmodel = string | null;
export type Selectedrewritemodel = string | null;
export type Theme = "light" | "dark" | "system";
export type Editortoken7 = string;
export type Schemaversion28 = 1;
export type Elapsed = number;
export type Error1 = string | null;
export type Id112 = string;
export type Kind106 = "import" | "export" | "rewrite";
export type Projectid14 = string;
export type Stage1 = string | null;
export type Startedat2 = string;
export type State15 = "running" | "succeeded" | "failed" | "cancelled";
export type Tasks1 = TaskStatusV1[];
/**
 * @minItems 1
 * @maxItems 100
 */
export type Ops1 = [
  (
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
  ),
  ...(
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
  )[]
];
export type Summary1 = string;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Findings2 =
  | [FindingInputV1]
  | [FindingInputV1, FindingInputV1]
  | [FindingInputV1, FindingInputV1, FindingInputV1]
  | [FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1]
  | [FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1]
  | [FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1]
  | [FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1, FindingInputV1]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ]
  | [
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1,
      FindingInputV1
    ];
export type Message3 = string;
export type Severity1 = "info" | "warning" | "error";
/**
 * @maxItems 20
 */
export type Sourceids1 =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
/**
 * @maxItems 20
 */
export type Targets2 =
  | []
  | [FindingTargetV1]
  | [FindingTargetV1, FindingTargetV1]
  | [FindingTargetV1, FindingTargetV1, FindingTargetV1]
  | [FindingTargetV1, FindingTargetV1, FindingTargetV1, FindingTargetV1]
  | [FindingTargetV1, FindingTargetV1, FindingTargetV1, FindingTargetV1, FindingTargetV1]
  | [FindingTargetV1, FindingTargetV1, FindingTargetV1, FindingTargetV1, FindingTargetV1, FindingTargetV1]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ]
  | [
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1,
      FindingTargetV1
    ];
export type Blockid20 = string | null;
export type Cellid13 = string | null;
export type End7 = number | null;
export type Fieldkey11 = string | null;
export type Recordid19 = string | null;
export type Start8 = number | null;
export type Cleanupstatus = "none" | "pending" | "complete" | "failed";
export type Projectid15 = string;
export type Title11 = string;
export type Tombstoned = boolean;
export type Updatedat3 = string;
export type Entries1 = RegistryEntry[];
export type Schemaversion29 = 1;
export type Baserevision4 = number;
export type Editortoken8 = string;
export type Title12 = string;
export type Appliedclientmutationids = string[];
export type Revision61 = number;
export type Editortoken9 = string;
export type Requestid = string;
export type Editortoken10 = string;
export type Instruction2 = string;
export type Requestid1 = string;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Regions2 = [RichRegion, RichRegion, RichRegion];
export type Blocks10 = (
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
export type Id113 = string;
export type Revision62 = number;
export type Role7 = "header" | "sidebar" | "main";
export type Revision63 = number;
export type Schemaversion30 = 1;
export type Markdown1 = string;
export type Clarify = string;
export type Shorten = string;
export type Revision64 = number;
export type Sha2567 = string;
export type Code8 =
  | "RULES_PRESETS_REQUIRED"
  | "RULES_STALE"
  | "RULES_TOO_LARGE"
  | "RULES_PRESET_TOO_LONG"
  | "RULES_INVALID_TEXT"
  | "RULES_LOAD_FAILED"
  | "RULES_SAVE_FAILED"
  | "RULES_UNSAFE_STORAGE";
export type Retryable = false;
export type Stage2 = "rules";
export type Requiredheadings = ("## Preset: shorten" | "## Preset: clarify")[];
export type Automaticanalysis1 = boolean;
export type Model3 = string | null;
export type Importminutes1 = number;
export type Projectmegabytes1 = number;
export type Baserevision5 = number;
export type Markdown2 = string;
export type Clipboardcaptureid1 = string;
export type Projectid16 = string;
export type Schemaversion31 = 1;
export type Selection1 = ClipboardRangeSelection | ClipboardBlocksSelection;
export type Bytesbase641 = string;
export type Id114 = string;
export type Mimetype4 = string;
export type Path5 = string;
export type Role8 = "font" | "logo" | "icon" | "catalog";
export type Sha2568 = string;
export type Size8 = number;
export type Assets4 = CapturedAsset[];
export type Blocks11 = CompiledBlock[];
export type Compilerversion1 = string;
export type Confighash1 = string;
export type Id115 = string;
export type Operationversion1 = string;
export type Originalbase641 = string;
export type Originalformat1 = "yaml" | "json";
export type Originalhash1 = string;
export type Packagehash8 = string;
export type Projectionversion1 = string;
export type Revision65 = string;
export type Schemaversion32 = 1;
export type Assets5 = TemplateRenderAsset[];
export type Documenthash4 = string;
export type Factshash4 = string;
export type Packagehash9 = string;
export type Presentationhash3 = string;
export type Renderinputversion2 = 1;
export type Schemaversion33 = 1;
export type Requestid2 = string;
export type Schemaversion34 = 1;
export type Source3 = string;
export type Text26 = string;
export type Mode3 = "structured" | "digest" | "imported";
export type Records3 = (
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
export type Revision66 = number;
export type Tombstones1 = RecordTombstone[];

export interface FoldCVContracts {
  agent_error: AgentError;
  agent_event: AgentEvent;
  agent_fetch_request: AgentFetchRequest;
  agent_finding: AgentFinding;
  agent_message: AgentMessage;
  agent_settings: AgentSettings;
  agent_settings_request: AgentSettingsRequest;
  agent_web_source: AgentWebSource;
  archive_download: ArchiveDownload;
  archive_manifest_v7: ArchiveManifestV7;
  assistant_apply_request_v1: AssistantApplyRequestV1;
  assistant_apply_result_v1: AssistantApplyResultV1;
  assistant_capabilities_v1: AssistantCapabilitiesV1;
  assistant_change_proposal_list_v1: AssistantChangeProposalListV1;
  assistant_change_proposal_v1: AssistantChangeProposalV1;
  assistant_conversation_list_v1: AssistantConversationListV1;
  assistant_conversation_v1: AssistantConversationV1;
  assistant_error_v1: AssistantErrorV1;
  assistant_events_v1: AssistantEventsV1;
  assistant_file_v1: AssistantFileV1;
  assistant_messages_v1: AssistantMessagesV1;
  assistant_run_request_v2: AssistantRunRequestV2;
  assistant_run_v1: AssistantRunV1;
  assistant_skill_list_v1: AssistantSkillListV1;
  cli_installation_payload: CliInstallationPayload;
  clipboard_capture_request_v1: ClipboardCaptureRequestV1;
  delete_request_v1: DeleteRequestV1;
  edit_request_v1: EditRequestV1;
  edit_result_v1: EditResultV1;
  export_command: ExportCommand;
  export_retry: ExportRetry;
  extract_result: ExtractResult;
  history_request_v1: HistoryRequestV1;
  history_state_v1: HistoryStateV1;
  import_command: ImportCommand;
  preferences: Preferences;
  project_open_result_v1: ProjectOpenResultV1;
  propose_changes_v1: ProposeChangesV1;
  publish_findings_v1: PublishFindingsV1;
  registry: Registry;
  rename_request_v1: RenameRequestV1;
  revision_conflict_v1: RevisionConflictV1;
  rewrite_cancel_request_v1: RewriteCancelRequestV1;
  rewrite_preview_request_v1: RewritePreviewRequestV1;
  rich_document_v1: RichDocumentV1;
  rich_document_v2: RichDocumentV2;
  rich_panel_request: RichPanelRequest;
  rules: Rules1;
  rules_settings: RulesSettings;
  rules_settings_error: RulesSettingsError;
  save_analysis_preference: SaveAnalysisPreference;
  save_import_model_preference: SaveImportModelPreference;
  save_limits_preference: SaveLimitsPreference;
  save_rules_request: SaveRulesRequest;
  task_status_v1: TaskStatusV1;
  template_clipboard_capture_v1: TemplateClipboardCaptureV1;
  template_definition: TemplateDefinition;
  template_edit_preparation_v1: TemplateEditPreparationV1;
  template_import_v1: ImportOperation;
  template_package: TemplatePackage;
  template_project_response_v1: TemplateProjectResponseV1;
  template_render_request_v1: TemplateRenderRequestV1;
  template_rewrite_preview_v1: TemplateRewritePreviewV1;
  template_snapshot_identity: TemplateSnapshotIdentity;
  working_facts: WorkingFacts;
  workspace_v7: WorkspaceV7;
}
export interface AgentError {
  code: Code;
}
export interface MessageDelta {
  conversationId: Conversationid;
  id: Id;
  payload: MessageDeltaPayload;
  projectId: Projectid;
  runId: Runid;
  schemaVersion: Schemaversion;
  sequence: Sequence;
  timestamp: Timestamp;
  type: Type;
}
export interface MessageDeltaPayload {
  text: Text;
}
export interface ActivityEvent {
  conversationId: Conversationid1;
  id: Id1;
  payload: ActivityPayload;
  projectId: Projectid1;
  runId: Runid1;
  schemaVersion: Schemaversion1;
  sequence: Sequence1;
  timestamp: Timestamp1;
  type: Type1;
}
export interface ActivityPayload {
  itemId: Itemid;
  kind: Kind;
  text: Text1;
}
export interface ToolEvent {
  conversationId: Conversationid2;
  id: Id2;
  payload: ToolPayload;
  projectId: Projectid2;
  runId: Runid2;
  schemaVersion: Schemaversion2;
  sequence: Sequence2;
  timestamp: Timestamp2;
  type: Type2;
}
export interface ToolPayload {
  callId: Callid;
  error: AgentError | null;
  name: Name;
}
export interface ResourceEvent {
  conversationId: Conversationid3;
  id: Id3;
  payload: ResourcePayload;
  projectId: Projectid3;
  runId: Runid3;
  schemaVersion: Schemaversion3;
  sequence: Sequence3;
  timestamp: Timestamp3;
  type: Type3;
}
export interface ResourcePayload {
  id: Id4;
}
export interface EditEvent {
  conversationId: Conversationid4;
  id: Id5;
  payload: EditPayload;
  projectId: Projectid4;
  runId: Runid4;
  schemaVersion: Schemaversion4;
  sequence: Sequence4;
  timestamp: Timestamp4;
  type: Type4;
}
export interface EditPayload {
  batchId: Batchid;
  disposition: Disposition;
  error: AgentError | null;
}
export interface UsageEvent {
  conversationId: Conversationid5;
  id: Id6;
  payload: AgentUsage;
  projectId: Projectid5;
  runId: Runid5;
  schemaVersion: Schemaversion5;
  sequence: Sequence5;
  timestamp: Timestamp5;
  type: Type5;
}
export interface AgentUsage {
  cachedInputTokens: Cachedinputtokens;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
  totalTokens: Totaltokens;
}
export interface RunStateEvent {
  conversationId: Conversationid6;
  id: Id7;
  payload: RunStatePayload;
  projectId: Projectid6;
  runId: Runid6;
  schemaVersion: Schemaversion6;
  sequence: Sequence6;
  timestamp: Timestamp6;
  type: Type6;
}
export interface RunStatePayload {
  error: AgentError | null;
  outcomeUnknown: Outcomeunknown;
  savedBatchId: Savedbatchid;
  state: State;
}
export interface AgentFetchRequest {
  url: Url;
}
export interface AgentFinding {
  anchors: Anchors;
  id: Id9;
  message: Message;
  runId: Runid7;
  severity: Severity;
  sourceIds: Sourceids;
}
export interface AgentAnchor {
  blockId: Blockid;
  cellId: Cellid;
  dependencies: Dependencies;
  end: End;
  fieldKey: Fieldkey;
  recordId: Recordid;
  start: Start;
  text: Text2;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id8;
  kind: Kind1;
  revision: Revision;
}
export interface AgentMessage {
  error: AgentError | null;
  findings: Findings;
  id: Id11;
  role: Role;
  runId: Runid8;
  sources: Sources;
  text: Text3;
  timestamp: Timestamp7;
  truncated: Truncated;
}
export interface AgentReference {
  id: Id10;
  label: Label;
}
export interface AgentSettings {
  enabled: Enabled;
  reasoningEffort?: Reasoningeffort;
  revision: Revision1;
  schemaVersion: Schemaversion7;
  selectedAgentModel: Selectedagentmodel;
}
export interface AgentSettingsRequest {
  enabled: Enabled1;
  expectedRevision: Expectedrevision;
  reasoningEffort?: Reasoningeffort1;
  selectedAgentModel: Selectedagentmodel1;
}
export interface AgentWebSource {
  contentSha256: Contentsha256;
  finalUrl: Finalurl;
  id: Id12;
  originalBytes: Originalbytes;
  requestedUrl: Requestedurl;
  retrievedAt: Retrievedat;
  runId: Runid9;
  text: Text4;
  title: Title;
  truncated: Truncated1;
}
export interface ArchiveDownload {
  documentRevision: Documentrevision;
  editorToken: Editortoken;
  projectRevision: Projectrevision;
}
export interface ArchiveManifestV7 {
  appVersion: Appversion;
  entries: Entries;
  projectId: Projectid7;
  schemaVersion: Schemaversion8;
}
export interface TemplateArchiveEntry {
  path: Path;
  role: Role1;
  sha256: Sha256;
  size: Size;
}
export interface AssistantApplyRequestV1 {
  allowEdits: Allowedits;
  clientMutationId: Clientmutationid;
  editorToken: Editortoken1;
}
export interface AssistantApplyResultV1 {
  action: AssistantActionResultV1 | null;
  edit: EditResultV1 | null;
  proposal: AssistantChangeProposalV1;
}
export interface AssistantActionResultV1 {
  action: Action;
  archived: Archived;
  deleted: Deleted;
  title: Title1;
}
export interface EditResultV1 {
  changedBlockIds: Changedblockids;
  clientMutationId: Clientmutationid1;
  createdBlocks: Createdblocks;
  createdIds: Createdids;
  documentRevision: Documentrevision1;
  history: HistoryStateV1;
  replayed: Replayed;
  response: TemplateProjectResponseV1;
  revision: Revision60;
  schemaVersion: Schemaversion23;
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
  kind: Kind2;
}
export interface TemplateProjectResponseV1 {
  durability: Durability;
  generation: RichGenerationState | null;
  identity: ResumeIdentity | null;
  presentation: TemplatePresentationV1 | null;
  saveError: Saveerror;
  savedDocumentRevision: Saveddocumentrevision;
  savedProjectRevision: Savedprojectrevision;
  schemaVersion: Schemaversion11;
  snapshot: TemplateSnapshotIdentity | null;
  workspace: WorkspaceV7;
}
export interface RichGenerationState {
  errorCode: Errorcode;
  id: Id13;
  stage: Stage;
  startedAt?: Startedat;
  status: Status;
}
export interface ResumeIdentity {
  subtitle: Subtitle;
  title: Title2;
}
export interface TemplatePresentationV1 {
  blocks: Blocks;
  editor?: EditorPlanV1 | null;
  recipe: CompiledRecipe;
  schemaVersion: Schemaversion10;
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
  size: Size1;
}
/**
 * Python's presentation decisions for the mounted editor; the editor only applies them.
 */
export interface EditorPlanV1 {
  addKinds?: Addkinds;
  addTechnologyGroup?: Addtechnologygroup;
  blocks: Blocks1;
  focusPanel?: EditorFocusPanel | null;
  fonts: Fonts;
  iconFiles?: Iconfiles;
  icons: Icons1;
  jobs?: Jobs;
  styles: Styles;
  technologyLines?: Technologylines;
  technologyTargets?: Technologytargets;
  unshownFields?: Unshownfields;
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
  row?: EditorRow | null;
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
 * A table row (D143): its table style, its label, and whether it opens or closes the table it shares with its
 * neighbours.
 */
export interface EditorRow {
  first: First;
  gap?: Gap;
  label: Label1;
  last: Last;
  table: Table;
}
/**
 * The facts panel can add, remove and move Focus rows, set their years and choose their icons.
 */
export interface EditorFocusPanel {
  full?: Full;
  icons?: Icons;
  records: Records;
}
export interface Iconfiles {
  [k: string]: string;
}
export interface Jobs {
  [k: string]: EditorJob;
}
/**
 * One job in the facts panel.
 */
export interface EditorJob {
  addPeriod?: Addperiod;
  periods: Periods;
}
export interface Styles {
  [k: string]: EditorStyle;
}
export interface EditorStyle {
  alignment: Alignment1;
  color: Color1;
  faces: EditorFaces;
  lineHeight: Lineheight;
  size: Size2;
}
export interface EditorFaces {
  bold: Bold1;
  boldItalic: Bolditalic;
  italic: Italic1;
  regular: Regular;
  upright?: Upright;
}
/**
 * Where the facts panel adds a technology: a line of one scope, a job section that has none yet, or a group view
 * the document no longer shows (block id view:<view id>).
 */
export interface EditorTechnologyTarget {
  blockId: Blockid1;
  jobId: Jobid;
  label: Label2;
  placement: EditorPlacement;
  records?: Records1;
}
/**
 * A block's parent block or region and the sibling before it, as a panel placement context names them.
 */
export interface EditorPlacement {
  afterId: Afterid;
  parentId: Parentid;
}
export interface Unshownfields {
  [k: string]: string[];
}
export interface CompiledRecipe {
  capabilities: Capabilities;
  layout: Layout;
  placements: Placements;
  renderInputVersion: Renderinputversion;
  schemaVersion: Schemaversion9;
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
  id: Id14;
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
  tables?: Tables;
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
export interface Fonts1 {
  [k: string]: string;
}
export interface Footer {
  baseline_y: BaselineY;
  center_x: CenterX;
  repeat: Repeat;
  style: Style2;
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
  color: Color2;
  follow_header: FollowHeader;
  width: Width1;
  x1: X1;
  x2: X2;
  y: Y;
}
export interface Logo {
  asset?: Asset;
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
export interface Tables {
  [k: string]: TableStyle;
}
/**
 * A key-value table (D143): a label column of `label_width` points and the row's content beside it. A label width
 * of 0 is one column of framed or shaded rows; a border width of 0 draws no lines.
 */
export interface TableStyle {
  background?: Background1;
  border_color?: BorderColor;
  border_width: BorderWidth;
  label_align?: LabelAlign;
  label_background?: LabelBackground;
  label_style: LabelStyle;
  label_width: LabelWidth;
  padding_x: PaddingX;
  padding_y: PaddingY;
}
export interface Text6 {
  [k: string]: TextStyle;
}
export interface TextStyle {
  alignment?: Alignment2;
  color: Color3;
  font: Font1;
  line_height: LineHeight;
  size: Size3;
}
export interface Views {
  [k: string]: View;
}
export interface View {
  fallback_style?: FallbackStyle;
  heading: Heading;
  heading_style?: HeadingStyle1;
  inset: Inset;
  item_gap: ItemGap;
  mode: Mode;
  nodes: Nodes;
  row?: Row1;
  table?: Table1;
  title: Title3;
}
export interface ViewNode {
  background?: Background2;
  detail_style?: DetailStyle;
  experience_field?: ExperienceField;
  field?: Field;
  fields?: Fields;
  header_slot?: HeaderSlot;
  item_field?: ItemField;
  label?: Label3;
  label_style?: LabelStyle1;
  name_field?: NameField;
  prefix?: Prefix;
  prefix_style?: PrefixStyle;
  row?: Row;
  separator?: Separator;
  style: Style3;
  type: Type7;
  url_field?: UrlField;
}
export interface Label3 {
  [k: string]: string;
}
export interface Prefix {
  [k: string]: string;
}
export interface Title3 {
  [k: string]: string;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision2;
  factsHash: Factshash;
  packageHash: Packagehash1;
  presentationHash: Presentationhash;
  projectId: Projectid8;
  projectRevision: Projectrevision1;
}
export interface WorkspaceV7 {
  createdAt: Createdat;
  documentRevision: Documentrevision3;
  formattingAsOf: PartialDate;
  mutationReplay: Mutationreplay;
  preDraft: RichPreDraftV2 | null;
  project: ProjectV6 | null;
  projectId: Projectid11;
  projectRevision: Projectrevision2;
  rulesUsed: Rules1 | null;
  schemaVersion: Schemaversion21;
  sourceObservedAt: PartialDate | null;
  syncRecords: Syncrecords;
  title: Title8;
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
  changedBlockIds?: Changedblockids1;
  clientMutationId: Clientmutationid2;
  createdBlocks?: Createdblocks1;
  createdIds?: Createdids1;
  requestSha256: Requestsha256;
  resultingRevision: Resultingrevision;
}
export interface Createdblocks1 {
  [k: string]: string[];
}
export interface Createdids1 {
  [k: string]: {
    [k: string]: string;
  };
}
export interface RichPreDraftV2 {
  facts: WorkingFactsV2;
  importDraft?: ImportDraft | null;
  operations: Operations;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources1;
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
  records: Records2;
  relations: Relations1;
  revision: Revision23;
  schemaVersion: Schemaversion13;
  tombstones: Tombstones;
}
export interface BuiltinItemIdentity {
  canonicalFields?: Canonicalfields;
  cellIds: Cellids;
  itemHandle: Itemhandle1;
  periodIds?: Periodids;
  recordId: Recordid1;
  semanticSchemaHash: Semanticschemahash;
  semanticType: Semantictype;
}
export interface Canonicalfields {
  [k: string]: CanonicalFieldBinding;
}
export interface CanonicalFieldBinding {
  cellId: Cellid1;
  fieldKey: Fieldkey1;
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
  id: Id16;
  itemHandle: Itemhandle2;
  observationIds: Observationids1;
  relations: Relations;
  retiredCellIds?: Retiredcellids;
  revision: Revision4;
  schemaVersion: Schemaversion12;
  semanticSchemaHash: Semanticschemahash1;
  semanticType: Semantictype1;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence;
  fieldKey: Fieldkey2;
  id: Id15;
  manualScopeId: Manualscopeid;
  observationIds: Observationids;
  origin: Origin;
  rawInput: Rawinput;
  revision: Revision2;
  state: State1;
  typedValue: JsonValue;
  userCorrected: Usercorrected;
}
export interface SourceSpan {
  end: End1;
  sliceHash: Slicehash;
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  start: Start1;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface Relation {
  active: Active1;
  id: Id17;
  kind: Kind3;
  revision: Revision3;
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
  code: Code1;
  page?: Page1;
  section: Section;
  sourceId: Sourceid1;
  unitId: Unitid1;
}
export interface ManualEditScope {
  actionId: Actionid1;
  blockIds: Blockids;
  cellIds: Cellids1;
  id: Id18;
  rawInput: Rawinput1;
}
export interface Observation {
  admission: Admission;
  evidence: Evidence1;
  fieldKey: Fieldkey3;
  id: Id19;
  itemHandle: Itemhandle3;
  ownerRelations: Ownerrelations;
  proposalHash: Proposalhash;
  rawInput: Rawinput2;
  receiptIds: Receiptids;
  typedValue: JsonValue;
}
export interface CandidateRecord {
  evidence: Evidence2;
  id: Id20;
  kind: Kind4;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin1;
  revision: Revision6;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected2;
}
export interface EvidenceSpan {
  sourceId: Sourceid2;
  sourceRevision: Sourcerevision1;
  text: Text7;
  unitId: Unitid2;
  unitRevision: Unitrevision1;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision5;
  status: Status2;
  userCorrected?: Usercorrected1;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence3;
  id: Id21;
  kind: Kind5;
  label: Label4;
  origin: Origin2;
  revision: Revision7;
  userCorrected?: Usercorrected3;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence4;
  id: Id22;
  kind: Kind6;
  origin: Origin3;
  periods: Periods1;
  revision: Revision11;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence5;
  id: Id23;
  present: WorkingFieldBool;
  revision: Revision10;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision8;
  status: Status3;
  userCorrected?: Usercorrected4;
  value: PartialDate | null;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision9;
  status: Status4;
  userCorrected?: Usercorrected5;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence6;
  id: Id24;
  jobId: Jobid1;
  kind: Kind7;
  name: WorkingFieldStr;
  origin: Origin4;
  periods: Periods2;
  revision: Revision12;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected7;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence7;
  experience?: WorkingFieldStr;
  id: Id25;
  jobId: Jobid2;
  kind: Kind8;
  origin: Origin5;
  revision: Revision13;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected8;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id26;
  institution: WorkingFieldStr;
  kind: Kind9;
  origin: Origin6;
  qualification: WorkingFieldStr;
  revision: Revision14;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected9;
}
export interface LanguageRecord {
  evidence: Evidence9;
  id: Id27;
  kind: Kind10;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin7;
  revision: Revision15;
  userCorrected?: Usercorrected10;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence10;
  id: Id28;
  issuer: WorkingFieldStr;
  kind: Kind11;
  name: WorkingFieldStr;
  origin: Origin8;
  revision: Revision16;
  userCorrected?: Usercorrected11;
}
export interface ClaimRecord {
  evidence: Evidence11;
  id: Id29;
  jobId: Jobid3;
  kind: Kind12;
  origin: Origin9;
  revision: Revision17;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected12;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence12;
  id: Id30;
  jobId: Jobid4;
  kind: Kind13;
  origin: Origin10;
  revision: Revision18;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected13;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision19;
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
  id: Id31;
  jobId: Jobid5;
  kind: Kind14;
  origin: Origin11;
  revision: Revision20;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected15;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision21;
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
  id: Id32;
  kind: Kind15;
  origin: Origin12;
  revision: Revision22;
  status: Status7;
  userCorrected?: Usercorrected17;
}
export interface RecordTombstone {
  actionId: Actionid2;
  orderIndex: Orderindex;
  recordId: Recordid2;
  revision: Revision24;
}
export interface ImportDraft {
  allowTextRewrite?: Allowtextrewrite;
  blocks?: Blocks3;
  facts?: Facts;
  finished?: Finished;
  issues?: Issues;
  profile?: ImportProfile;
  receipts?: Receipts;
  runId: Runid10;
  sequence?: Sequence8;
  skillSha256: Skillsha256;
  sourceSha256: Sourcesha256;
  technologyGroups?: Technologygroups;
  version?: Version;
}
export interface ImportBlock {
  category?: Category1;
  duplicateOf?: Duplicateof;
  id: Id33;
  kind?: Kind16;
  listItem?: Listitem;
  modelBlock?: Modelblock;
  reason?: Reason;
  region?: Region2;
  sourceKeys?: Sourcekeys;
  text?: Text8;
  title?: Title4;
}
export interface ImportFact {
  id: Id34;
  record?: Record;
  sourceKeys?: Sourcekeys1;
  text?: Text9;
}
export interface ImportEmployment {
  employer?: Employer;
  kind: Kind17;
  periods?: Periods3;
  role?: Role2;
  technologies?: Technologies;
}
export interface ImportPeriod {
  end?: End2;
  present?: Present;
  start?: Start2;
}
export interface ImportSkill {
  display: Display;
  experience?: Experience;
  technical?: Technical1;
}
export interface ImportEducation {
  completion?: Completion;
  institution?: Institution;
  kind: Kind18;
  qualification?: Qualification;
  specialty?: Specialty;
}
export interface ImportTechnology {
  display: Display1;
  experience?: Experience1;
  kind: Kind19;
  technical?: Technical2;
}
export interface ImportLanguage {
  kind: Kind20;
  language?: Language;
  level?: Level;
}
export interface ImportProfile {
  location?: Location;
  name?: Name1;
  sourceKeys?: Sourcekeys2;
  title?: Title5;
}
export interface ImportReceipt {
  batchId: Batchid1;
  requestSha256: Requestsha2561;
  sequence: Sequence7;
}
export interface ImportTechnologyGroup {
  heading: Heading1;
  region?: Region3;
  sourceKeys?: Sourcekeys3;
  technologies: Technologies1;
}
export interface RichOperation {
  actionId: Actionid3;
  dependencies: Dependencies1;
  errorCode: Errorcode1;
  id: Id35;
  kind: Kind21;
  status: Status8;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id36;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision26;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id37;
  origin: Origin13;
  revision: Revision25;
  text: Text10;
  unitId: Unitid3;
}
export interface SourceUnit {
  disposition: Disposition1;
  id: Id38;
  location: SourceLocation;
  order: Order1;
  representedFactIds: Representedfactids;
  revision: Revision27;
  structure?: SourceStructure | null;
  text: Text11;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind22;
  row: Row2;
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
  id: Id43;
  inferenceClosed?: Inferenceclosed;
  issues?: Issues1;
  lastObservedAt: Lastobservedat;
  projectId: Projectid9;
  proposals: Proposals;
  publication: PublicationOutcome;
  receipts: Receipts1;
  relationAllocations?: Relationallocations;
  reviewInputs: Reviewinputs;
  schemaVersion: Schemaversion16;
  state: State9;
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
  recordId: Recordid3;
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
  id: Id39;
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
  state: State3;
  taskId: Taskid1;
  usage: ObservedUsage;
}
export interface CleanupOutcome {
  evidenceHash: Evidencehash;
  state: State2;
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
  cachedInputTokens: Cachedinputtokens1;
  complete: Complete;
  inputTokens: Inputtokens1;
  outputTokens: Outputtokens1;
}
export interface ImportAuthorization {
  authorityHash: Authorityhash;
  authorizedAt: Authorizedat;
  dependencyHash: Dependencyhash;
  id: Id40;
  kind: Kind23;
  state: State4;
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
  recordId: Recordid4;
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
  id: Id41;
  packageHash: Packagehash3;
  presentationHash: Presentationhash1;
  publicationIntentId: Publicationintentid;
  rendererHash: Rendererhash;
  state: State5;
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
  id: Id42;
  issuesHash: Issueshash;
  operationId: Operationid2;
  packageHash: Packagehash4;
  sourceHash: Sourcehash;
  startedAt: Startedat1;
}
export interface ImportIssue {
  blockIds: Blockids1;
  category: Category2;
  code: Code3;
  id: Id44;
  importedFingerprint: Importedfingerprint;
  lifecycleId: Lifecycleid;
  message: Message1;
  retiredByAction: Retiredbyaction;
  reviewInputHash: Reviewinputhash;
  ruleId: Ruleid;
  state: State6;
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
  id: Id45;
  inputHash: Inputhash1;
  lineage: Lineage;
  proposalHash: Proposalhash1;
  rawReturn: Rawreturn1;
  rawReturnHash: Rawreturnhash1;
  reply: ProposalReply | null;
  resolvedFields: Resolvedfields;
  resolvedRelations?: Resolvedrelations;
  state: State7;
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
  fieldKey: Fieldkey4;
  pointer: Pointer;
  text: Text12;
}
export interface Lineage1 {
  attemptId: Attemptid2;
  children: Children;
  kind: Kind24;
  parents: Parents;
}
export interface ProposalReply {
  discoveries: Discoveries;
  fields: Fields1;
  lineage: Lineage2;
  payload: JsonValue;
  relations?: Relations2;
  schemaVersion: Schemaversion14;
}
export interface Discovery {
  key: Key1;
  pointer: Pointer1;
  semanticType: Semantictype4;
}
export interface ProposalField {
  effectiveCellIds: Effectivecellids;
  evidence: Evidence15;
  fieldKey: Fieldkey5;
  item: Item;
  pointer: Pointer2;
}
export interface DiscoverySelector {
  key: Key2;
  kind: Kind25;
}
export interface HandleSelector {
  itemHandle: Itemhandle6;
  kind: Kind26;
}
export interface ProposalLineage {
  children: Children1;
  kind: Kind27;
  parents: Parents1;
}
export interface ProposalRelation {
  evidence: Evidence16;
  kind: Kind28;
  relation: Relation1;
  subject: Subject;
  target: Target;
}
export interface RelationDiscoverySelector {
  key: Key3;
  kind: Kind29;
}
export interface ExistingRelationSelector {
  kind: Kind30;
  relationId: Relationid;
}
export interface FieldSidecar {
  effectiveCellIds: Effectivecellids1;
  evidence: Evidence17;
  fieldKey: Fieldkey6;
  itemHandle: Itemhandle7;
  pointer: Pointer3;
}
export interface PublicationOutcome {
  errorCode: Errorcode4;
  intentId: Intentid;
  state: State8;
  workspaceHash: Workspacehash;
}
export interface ReviewReceipt {
  attemptId: Attemptid3;
  completedAt: Completedat;
  expectedChecks: Expectedchecks;
  id: Id46;
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
  evidence: Evidence18;
  reason: Reason1;
  ruleId: Ruleid2;
  targetId: Targetid2;
}
export interface RelationAllocation {
  discoveryAttemptId: Discoveryattemptid1;
  key: Key4;
  kind: Kind31;
  operationId: Operationid3;
  relationId: Relationid1;
  subjectId: Subjectid1;
  targetId: Targetid3;
  taskId: Taskid3;
}
export interface ReviewInputRecord {
  attemptId: Attemptid4;
  id: Id47;
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
  schemaVersion: Schemaversion15;
  semanticContext: Semanticcontext;
  settled?: Settled;
  sourceSpans: Sourcespans;
  sourceTexts: Sourcetexts;
  targets: Targets;
}
export interface EvidenceOption {
  ref: Ref;
  span: SourceSpan;
  text: Text13;
}
export interface Check {
  id: Id48;
  kind: Kind32;
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
  disposition: Disposition3;
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
  id: Id49;
  inputHash: Inputhash3;
  taskId: Taskid4;
  value: Value2;
}
export interface Value2 {
  [k: string]: JsonValue;
}
export interface TaskResultRecord {
  disposition: Disposition4;
  id: Id50;
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
  blockId: Blockid2;
  dependencies: Dependencies2;
  entry?: EntryScope | null;
  expectedChecks: Expectedchecks1;
  id: Id51;
  inputHash: Inputhash5;
  issueIds: Issueids1;
  kind: Kind33;
  operationId: Operationid4;
  parentTaskId?: Parenttaskid;
  proposalHash: Proposalhash3;
  receiptIds: Receiptids1;
  state: State10;
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
  title: Title7;
}
/**
 * One entry the outline named (D117): its title and its source lines.
 */
export interface EntryPart {
  spans: Spans;
  title: Title6;
}
export interface StoredTemplatePackage {
  assets: Assets;
  blocks: Blocks4;
  compilerVersion: Compilerversion;
  configHash: Confighash;
  definition: TemplateDefinition;
  id: Id64;
  manifest: CompilationManifest;
  operationVersion: Operationversion;
  originalBase64: Originalbase64;
  originalFormat: Originalformat;
  originalHash: Originalhash;
  packageHash: Packagehash6;
  projectionVersion: Projectionversion;
  recipe: CompiledRecipe;
  revision: Revision29;
  schemaVersion: Schemaversion17;
}
/**
 * An asset of a workspace's captured package. Its bytes stay in memory and in the project's asset files, never in
 * the workspace JSON, its hash or the browser's copy (D104: fonts were a quarter of every 10 MB reply).
 */
export interface StoredAsset {
  bytesBase64?: Bytesbase64;
  id: Id52;
  mimeType: Mimetype1;
  path: Path1;
  role: Role3;
  sha256: Sha2561;
  size: Size4;
}
export interface CompiledBlock {
  dependencyOrder: Dependencyorder;
  fullSchema: Fullschema;
  id: Id53;
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
  id: Id54;
  mime_type: MimeType;
  path: Path2;
  role: Role4;
}
export interface Block {
  bindings: Bindings;
  checks: Checks;
  content_schema: ContentSchema;
  depends_on: DependsOn;
  effort?: Effort1;
  extract: Extract;
  id: Id55;
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
  kind: Kind34;
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
  id: Id56;
  kind: Kind35;
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
  id: Id57;
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
  kind: Kind36;
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
  id: Id58;
  inputs: Inputs;
  kind: Kind37;
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
  id: Id59;
  inputs: Inputs1;
  kind: Kind38;
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
  id: Id60;
  inputs: Inputs2;
  kind: Kind39;
  parameters: SkillsParameters;
  version: Version4;
}
export interface SkillsParameters {
  groups: Groups;
  uncertain_group: UncertainGroup;
}
export interface PeriodOperation {
  depends_on: DependsOn4;
  id: Id61;
  inputs: Inputs3;
  kind: Kind40;
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
  id: Id62;
  inputs: Inputs4;
  kind: Kind41;
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
  id: Id63;
  name: Name2;
  revision: Revision28;
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
  projectId: Projectid10;
  renders: Renders;
  revision: Revision45;
  schemaVersion: Schemaversion20;
  sources: Sources2;
  templateOperations?: Templateoperations1;
  templatePackage: StoredTemplatePackage;
}
export interface LocalImageAsset {
  height: Height3;
  id: Id65;
  mimeType: Mimetype2;
  path: Path3;
  sha256: Sha2562;
  size: Size5;
  width: Width4;
}
export interface RichDocumentV2 {
  regions: Regions1;
  revision: Revision44;
  schemaVersion: Schemaversion18;
}
export interface TemplateRegion {
  blocks: Blocks6;
  id: Id84;
  revision: Revision43;
  role: Role5;
}
export interface TemplateParagraphBlock {
  children: Children2;
  content: Content13;
  id: Id83;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance12;
  revision: Revision42;
  type: Type24;
}
export interface TemplateHeadingBlock {
  children: Children3;
  content: Content12;
  id: Id82;
  presentation: AuthoredPresentation | null;
  props: HeadingProps;
  provenance: Provenance11;
  revision: Revision41;
  type: Type23;
}
export interface TemplateBulletBlock {
  children: Children4;
  content: Content11;
  id: Id81;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance10;
  revision: Revision40;
  type: Type22;
}
export interface TemplateNumberedBlock {
  children: Children5;
  content: Content10;
  id: Id80;
  presentation: AuthoredPresentation | null;
  props: NumberedProps;
  provenance: Provenance9;
  revision: Revision39;
  type: Type21;
}
export interface TemplateChecklistBlock {
  children: Children6;
  content: Content9;
  id: Id79;
  presentation: AuthoredPresentation | null;
  props: ChecklistProps;
  provenance: Provenance8;
  revision: Revision38;
  type: Type20;
}
export interface TemplateToggleBlock {
  children: Children7;
  content: Content8;
  id: Id78;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance7;
  revision: Revision37;
  type: Type19;
}
export interface TemplateQuoteBlock {
  children: Children8;
  content: Content7;
  id: Id77;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision36;
  type: Type18;
}
export interface TemplateCodeBlock {
  children: Children9;
  content: Content6;
  id: Id76;
  presentation: AuthoredPresentation | null;
  props: CodeProps;
  provenance: Provenance5;
  revision: Revision35;
  type: Type17;
}
export interface TemplateDividerBlock {
  children: Children10;
  content: Content5;
  id: Id75;
  presentation: AuthoredPresentation | null;
  props: EmptyProps;
  provenance: Provenance4;
  revision: Revision34;
  type: Type16;
}
export interface TemplateTableBlock {
  children: Children11;
  content: TemplateTableContent;
  id: Id74;
  presentation: AuthoredPresentation | null;
  props: ParagraphProps;
  provenance: Provenance3;
  revision: Revision33;
  type: Type15;
}
export interface TemplateImageBlock {
  children: Children12;
  content: Content3;
  id: Id71;
  presentation: AuthoredPresentation | null;
  props: TemplateImageProps;
  provenance: Provenance2;
  revision: Revision31;
  type: Type14;
}
export interface TemplateSectionBlock {
  children: Children13;
  content: Content;
  id: Id66;
  presentation: AuthoredPresentation | null;
  props: SectionProps;
  provenance: Provenance1;
  revision: Revision30;
  type: Type13;
}
export interface PresentedText {
  citations?: Citations;
  presentation?: AuthoredPresentation | null;
  styles: InlineStyles;
  text: Text14;
  type: Type8;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold3;
  code?: Code4;
  italic?: Italic2;
  strike?: Strike;
  textColor?: Textcolor;
  underline?: Underline;
}
export interface PresentedHyperlink {
  content: Content1;
  href: Href;
  presentation?: AuthoredPresentation | null;
  type: Type9;
}
export interface FieldOccurrence {
  bindingId: Bindingid;
  bindingRootId?: Bindingrootid;
  cellId: Cellid2;
  citations?: Citations1;
  complete: Complete1;
  fieldKey: Fieldkey7;
  occurrenceId: Occurrenceid;
  presentation: AuthoredPresentation | null;
  recordId: Recordid5;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text15;
  type: Type10;
}
export interface BoundLink {
  content: Content2;
  href: Href1;
  labelBinding: FieldRef | null;
  presentation: AuthoredPresentation | null;
  type: Type11;
  urlBinding: FieldRef | null;
}
export interface FieldRef {
  cellId: Cellid3;
  fieldKey: Fieldkey8;
  occurrenceId: Occurrenceid1;
  recordId: Recordid6;
}
export interface ManualScopeSpan {
  citations?: Citations2;
  fragmentId: Fragmentid;
  occurrenceId: Occurrenceid2;
  presentation: AuthoredPresentation | null;
  scopeId: Scopeid;
  styles: InlineStyles;
  text: Text16;
  type: Type12;
}
export interface SectionProps {
  alignment?: Alignment3;
  backgroundColor?: Backgroundcolor1;
  icon?: Icon1;
  manualOrder?: Manualorder;
  presentation?: Presentation;
  recordId: Recordid7;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence21;
  fieldKeys: Fieldkeys;
  id: Id67;
  kind: Kind42;
  recordId: Recordid8;
}
export interface FieldBinding {
  fieldKey: Fieldkey9;
  id: Id68;
  kind: Kind43;
  recordId: Recordid9;
}
export interface WorkingOwnership {
  id: Id69;
  kind: Kind44;
  recordId: Recordid10;
}
export interface SourceWitness {
  evidence: Evidence22;
  id: Id70;
  kind: Kind45;
}
export interface TemplateImageProps {
  alignment: Alignment4;
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
  id: Id73;
}
export interface TemplateTableCell {
  alignment?: Alignment5;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content4;
  id: Id72;
  revision: Revision32;
  rowspan?: Rowspan;
}
export interface ParagraphProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor3;
  textColor?: Textcolor2;
}
export interface EmptyProps {}
export interface CodeProps {
  backgroundColor?: Backgroundcolor4;
  language: Language1;
}
export interface ChecklistProps {
  alignment?: Alignment7;
  backgroundColor?: Backgroundcolor5;
  checked: Checked;
  textColor?: Textcolor3;
}
export interface NumberedProps {
  alignment?: Alignment8;
  backgroundColor?: Backgroundcolor6;
  start?: Start3;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment9;
  backgroundColor?: Backgroundcolor7;
  level: Level1;
  textColor?: Textcolor5;
}
export interface ImmutableFactEvidence {
  evidence: Evidence23;
  id: Id85;
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
  schemaVersion: Schemaversion19;
}
export interface TemplateRenderAsset {
  id: Id86;
  path: Path4;
  sha256: Sha2563;
  size: Size6;
}
export interface TemplateRendererIdentity {
  id: Id87;
  sha256: Sha2564;
  version: Version7;
}
export interface SpanCoverage {
  blockIds: Blockids2;
  disposition: Disposition5;
  itemHandle: Itemhandle8;
  reason: Reason3;
  span: SourceSpan;
}
/**
 * A published import's record, kept in the project's history file of this hash (D104).
 */
export interface ImportHistoryRef {
  operationId: Operationid5;
  sha256: Sha2565;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision4;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id88;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface Rules1 {
  markdown: Markdown;
  revision: Revision46;
  sha256: Sha2566;
}
export interface TemplateSyncRecord {
  actionId: Actionid4;
  blockIds: Blockids3;
  capture: ActionCapture | null;
  dependencies: Dependencies4;
  errorCode: Errorcode5;
  factIds: Factids;
  fieldKeys: Fieldkeys1;
  id: Id89;
  instruction?: Instruction;
  kind?: Kind46;
  lifecycleId: Lifecycleid1;
  ownershipConflict: TemplateOwnershipConflict | null;
  proposedSteps?: Proposedsteps;
  ready?: Ready;
  resolutionOf?: TemplateSyncResolution | null;
  rewriteResult?: Rewriteresult;
  rewriteSource?: Rewritesource;
  schemaVersion: Schemaversion22;
  selection?: RichSelection | null;
  status: Status9;
}
export interface ActionCapture {
  actionId: Actionid5;
  actionToken: Actiontoken;
  dependencies: Dependencies3;
  sessionId: Sessionid;
}
export interface TemplateOwnershipConflict {
  beforeOwnerId: Beforeownerid;
  movedOccurrenceIds: Movedoccurrenceids;
  proposedOwnerId: Proposedownerid;
  recordId: Recordid11;
  relationId: Relationid2;
  remainingOccurrenceIds: Remainingoccurrenceids;
}
export interface TemplatePutBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision;
  block: Block1;
  keepChildren?: Keepchildren;
  kind: Kind47;
  parentId: Parentid1;
}
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid3;
  kind: Kind48;
}
export interface MoveBlock {
  afterId: Afterid2;
  beforeRevision: Beforerevision2;
  blockId: Blockid4;
  kind: Kind49;
  parentId: Parentid2;
}
export interface TemplateReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid5;
  cellId: Cellid4;
  content: Content14;
  end: End3;
  field: Field4;
  flankBindings?: Flankbindings;
  kind: Kind52;
  start: Start4;
}
export interface FlankBinding {
  fragmentId: Fragmentid1;
  role: Role6;
  source: Source1;
  sourceEnd: Sourceend;
  sourceStart: Sourcestart;
}
export interface FieldFlankSource {
  bindingId: Bindingid1;
  kind: Kind50;
}
export interface ManualScopeFlankSource {
  fragmentId: Fragmentid2;
  kind: Kind51;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind53;
  record: Record1;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind54;
  recordId: Recordid12;
}
export interface PutExtension {
  beforeRevision: Beforerevision6;
  kind: Kind55;
  record: ExtensionRecord;
}
export interface RemoveExtension {
  beforeRevision: Beforerevision7;
  kind: Kind56;
  recordId: Recordid13;
}
export interface PutRelation {
  beforeRevision: Beforerevision8;
  kind: Kind57;
  relation: Relation;
}
export interface RemoveRelation {
  beforeRevision: Beforerevision9;
  kind: Kind58;
  relationId: Relationid3;
}
export interface PutManualScope {
  kind: Kind59;
  scope: ManualEditScope;
}
export interface SetBuiltinManualScope {
  afterScopeId: Afterscopeid;
  beforeScopeId: Beforescopeid;
  cellId: Cellid5;
  kind: Kind60;
}
export interface SetIssueState {
  actionId: Actionid6;
  afterLifecycleId: Afterlifecycleid;
  afterState: Afterstate;
  beforeLifecycleId: Beforelifecycleid;
  beforeState: Beforestate;
  importedFingerprint: Importedfingerprint1;
  issueId: Issueid;
  kind: Kind61;
}
export interface SetAuthoredAnchors {
  afterBlockIds: Afterblockids;
  beforeBlockIds: Beforeblockids;
  kind: Kind62;
  target: Target1;
}
export interface IssueAnchorTarget {
  beforeLifecycleId: Beforelifecycleid1;
  beforeState: Beforestate1;
  importedFingerprint: Importedfingerprint2;
  issueId: Issueid1;
  kind: Kind63;
}
export interface CoverageAnchorTarget {
  coverageIdentityHash: Coverageidentityhash;
  coverageIndex: Coverageindex;
  coverageSequenceHash: Coveragesequencehash;
  kind: Kind64;
}
export interface RestoreAuthoredBlockPatch {
  afterSemanticHash: Aftersemantichash;
  beforeRevision: Beforerevision10;
  beforeSemanticHash: Beforesemantichash;
  blockId: Blockid6;
  kind: Kind65;
  patch: Patch;
}
export interface PatchSet {
  kind: Kind66;
  pointer: Pointer5;
  valueWire: Valuewire;
}
export interface PatchInsert {
  kind: Kind67;
  pointer: Pointer6;
  valueWire: Valuewire1;
}
export interface PatchRemove {
  kind: Kind68;
  pointer: Pointer7;
}
export interface PatchSpliceText {
  beforeTextHash: Beforetexthash;
  end: End4;
  kind: Kind69;
  pointer: Pointer8;
  start: Start5;
  text: Text17;
}
export interface SetManualScopeDisplays {
  assignments: Assignments;
  kind: Kind72;
  sources: Sources3;
}
export interface ScopeDisplayAssignment {
  address: ScopeDisplayAddress;
  after: After;
  beforeHash: Beforehash;
}
export interface ScopeDisplayAddress {
  blockId: Blockid7;
  cellId: Cellid6;
  field: Field5;
  inlineIndex: Inlineindex;
}
export interface ScopeDisplayBinding {
  fragmentId: Fragmentid3;
  kind: Kind70;
  occurrenceId: Occurrenceid3;
  scopeId: Scopeid1;
}
export interface LiteralDisplayBinding {
  kind: Kind71;
}
export interface ScopeDisplaySource {
  activeCellIds: Activecellids;
  fragments: Fragments;
  occurrenceId: Occurrenceid4;
  scopeHash: Scopehash;
  scopeId: Scopeid2;
}
export interface ScopeDisplayFragment {
  blockId: Blockid8;
  cellId: Cellid7;
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
  kind: Kind73;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid9;
  cellId: Cellid8;
  offset: Offset;
}
export interface RichSyncRecord {
  actionId: Actionid7;
  blockIds: Blockids5;
  dependencies: Dependencies5;
  errorCode: Errorcode6;
  factIds: Factids1;
  fieldKeys: Fieldkeys2;
  id: Id90;
  instruction?: Instruction1;
  kind?: Kind74;
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
  kind: Kind75;
  parentId: Parentid3;
}
export interface ParagraphBlock {
  children: Children14;
  content: Content27;
  id: Id104;
  props: ParagraphProps;
  provenance: Provenance24;
  revision: Revision59;
  type: Type39;
}
export interface HeadingBlock {
  children: Children15;
  content: Content26;
  id: Id103;
  props: HeadingProps;
  provenance: Provenance23;
  revision: Revision58;
  type: Type38;
}
export interface BulletBlock {
  children: Children16;
  content: Content25;
  id: Id102;
  props: ParagraphProps;
  provenance: Provenance22;
  revision: Revision57;
  type: Type37;
}
export interface NumberedBlock {
  children: Children17;
  content: Content24;
  id: Id101;
  props: NumberedProps;
  provenance: Provenance21;
  revision: Revision56;
  type: Type36;
}
export interface ChecklistBlock {
  children: Children18;
  content: Content23;
  id: Id100;
  props: ChecklistProps;
  provenance: Provenance20;
  revision: Revision55;
  type: Type35;
}
export interface ToggleBlock {
  children: Children19;
  content: Content22;
  id: Id99;
  props: ParagraphProps;
  provenance: Provenance19;
  revision: Revision54;
  type: Type34;
}
export interface QuoteBlock {
  children: Children20;
  content: Content21;
  id: Id98;
  props: ParagraphProps;
  provenance: Provenance18;
  revision: Revision53;
  type: Type33;
}
export interface CodeBlock {
  children: Children21;
  content: Content20;
  id: Id97;
  props: CodeProps;
  provenance: Provenance17;
  revision: Revision52;
  type: Type32;
}
export interface DividerBlock {
  children: Children22;
  content: Content19;
  id: Id96;
  props: EmptyProps;
  provenance: Provenance16;
  revision: Revision51;
  type: Type31;
}
export interface TableBlock {
  children: Children23;
  content: TableContent;
  id: Id95;
  props: ParagraphProps;
  provenance: Provenance15;
  revision: Revision50;
  type: Type30;
}
export interface ImageBlock {
  children: Children24;
  content: Content17;
  id: Id92;
  props: ImageProps;
  provenance: Provenance14;
  revision: Revision48;
  type: Type29;
}
export interface SectionBlock {
  children: Children25;
  content: Content15;
  id: Id91;
  props: SectionProps;
  provenance: Provenance13;
  revision: Revision47;
  type: Type28;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text18;
  type: Type25;
}
export interface Hyperlink {
  content: Content16;
  href: Href2;
  type: Type26;
}
export interface FactFieldSpan {
  bindingId: Bindingid2;
  bindingRootId?: Bindingrootid1;
  fieldKey: Fieldkey10;
  recordId: Recordid14;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision1;
  text: Text19;
  type: Type27;
}
export interface ImageProps {
  alignment: Alignment10;
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
  id: Id94;
}
export interface TableCell {
  alignment?: Alignment11;
  backgroundColor?: Backgroundcolor8;
  colspan?: Colspan1;
  content: Content18;
  id: Id93;
  revision: Revision49;
  rowspan?: Rowspan1;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision12;
  blockId: Blockid10;
  cellId: Cellid9;
  content: Content28;
  end: End5;
  field: Field7;
  kind: Kind76;
  start: Start6;
}
export interface RichWarning {
  blockIds: Blockids6;
  code: Code5;
  count?: Count;
  evidence: Evidence24;
  id: Id105;
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
  conversationId: Conversationid7;
  createdAt: Createdat2;
  expectedActionId?: Expectedactionid;
  id: Id106;
  kind: Kind77;
  ops: Ops;
  preview: Preview;
  projectId: Projectid12;
  runId: Runid11;
  schemaVersion: Schemaversion24;
  state: State11;
  summary: Summary;
  touched: Touched;
  updatedAt: Updatedat1;
}
export interface SetBlockTextOp {
  blockId: Blockid11;
  cellId?: Cellid10;
  field?: Field8;
  marks?: InlineStyles | null;
  op: Op;
  text: Text20;
}
export interface ReplaceTextOp {
  blockId: Blockid12;
  cellId?: Cellid11;
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
  kind?: Kind78;
  level?: Level2;
  text: Text21;
}
export interface DeleteBlocksOp {
  blockIds: Blockids7;
  op: Op3;
}
export interface MoveBlockOp {
  afterBlockId?: Afterblockid1;
  blockId: Blockid13;
  op: Op4;
  parentId?: Parentid5;
}
export interface FormatBlockOp {
  alignment?: Alignment12;
  backgroundColor?: Backgroundcolor9;
  blockId: Blockid14;
  kind?: Kind79;
  level?: Level3;
  op: Op5;
  textColor?: Textcolor6;
}
export interface UpdateFactOp {
  field: Field10;
  op: Op6;
  recordId: Recordid15;
  value: Value3;
}
export interface CreateFactOp {
  jobId?: Jobid6;
  kind: Kind80;
  op: Op7;
  targetId?: Targetid5;
  values?: Values;
}
export interface Values {
  [k: string]: string;
}
export interface DeleteFactOp {
  op: Op8;
  recordId: Recordid16;
}
export interface HistoryOp {
  direction: Direction;
  op: Op9;
}
export interface ActionOp {
  action: Action2;
  op: Op10;
  targetId?: Targetid6;
  value?: Value4;
}
export interface PreviewEntryV1 {
  after: After1;
  before: Before;
  label: Label5;
  target: Target2;
}
export interface Touched {
  [k: string]: string;
}
export interface AssistantCapabilitiesV1 {
  models: Models;
  ready: Ready2;
  tools: Tools;
  unavailable: AssistantErrorV1 | null;
  webAvailable: Webavailable;
}
export interface ModelChoiceV1 {
  model: Model1;
  provider?: Provider;
  state: State12;
}
export interface AssistantErrorV1 {
  code: Code6;
  detail?: Detail;
}
export interface AssistantChangeProposalListV1 {
  items: Items;
}
export interface AssistantConversationListV1 {
  items: Items1;
}
export interface AssistantConversationV1 {
  createdAt: Createdat3;
  id: Id107;
  title: Title9;
  updatedAt: Updatedat2;
}
export interface AssistantEventsV1 {
  events: Events;
  next: Next;
  run: AssistantRunV1;
}
export interface AssistantRunV1 {
  allowEdits: Allowedits1;
  allowWeb: Allowweb;
  baseRevision: Baserevision1;
  clientRequestId: Clientrequestid1;
  conversationId: Conversationid8;
  createdAt: Createdat4;
  error: AssistantErrorV1 | null;
  finishedAt: Finishedat;
  id: Id108;
  model: Model2;
  projectId: Projectid13;
  state: State13;
  usage: AgentUsage | null;
}
export interface AssistantFileV1 {
  filename: Filename;
  format: Format;
  id: Id109;
  size: Size7;
  url: Url1;
}
export interface AssistantMessagesV1 {
  conversation: AssistantConversationV1;
  files?: Files;
  findings: Findings1;
  messages: Messages;
  runs: Runs;
  sources: Sources4;
}
export interface AssistantRunRequestV2 {
  allowEdits: Allowedits2;
  allowWeb: Allowweb1;
  clientRequestId: Clientrequestid2;
  message: Message2;
  selection?: AssistantSelectionV1 | null;
}
export interface AssistantSelectionV1 {
  blockIds: Blockids8;
  text: Text22;
}
export interface AssistantSkillListV1 {
  items: Items2;
}
export interface AssistantSkillV1 {
  description: Description;
  id: Id110;
  title: Title10;
}
export interface CliInstallationPayload {
  available: Available;
  downloadedBytes: Downloadedbytes;
  error: Error;
  installed: Installed;
  latest: Latest;
  state: State14;
  totalBytes: Totalbytes;
  update: Update;
}
export interface ClipboardCaptureRequestV1 {
  clientCaptureId: Clientcaptureid;
  editorToken: Editortoken2;
  selection: Selection;
  snapshot: TemplateSnapshotIdentity;
}
export interface ClipboardRangeSelection {
  kind: Kind81;
  range: AuthoredRange;
}
export interface AuthoredRange {
  beforeRevision: Beforerevision13;
  blockId: Blockid15;
  cellId: Cellid12;
  end: End6;
  field: Field11;
  insertionTarget?: Insertiontarget;
  start: Start7;
}
export interface FieldInsertionTarget {
  bindingId: Bindingid3;
  kind: Kind82;
}
export interface LiteralInsertionTarget {
  kind: Kind83;
}
export interface ManualScopeInsertionTarget {
  fragmentId: Fragmentid5;
  kind: Kind84;
}
export interface ClipboardBlocksSelection {
  blocks: Blocks8;
  kind: Kind85;
}
export interface BlockTarget {
  beforeRevision: Beforerevision14;
  blockId: Blockid16;
}
export interface DeleteRequestV1 {
  confirmed: Confirmed;
}
export interface EditRequestV1 {
  baseRevision: Baserevision2;
  editorToken: Editortoken3;
  preparation: TemplateEditPreparationV1;
}
export interface TemplateEditPreparationV1 {
  capture: ActionCapture;
  clientMutationId: Clientmutationid3;
  operations: Operations3;
  schemaVersion: Schemaversion25;
  snapshot: TemplateSnapshotIdentity;
}
export interface ReplaceText {
  kind: Kind86;
  opId: Opid;
  range: AuthoredRange;
  styles: InlineStyles;
  text: Text23;
}
export interface SetMarks {
  kind: Kind87;
  opId: Opid1;
  range: AuthoredRange;
  styles: InlineStyles;
}
export interface SplitBlock {
  beforeRevision: Beforerevision15;
  blockId: Blockid17;
  kind: Kind88;
  offset: Offset1;
  opId: Opid2;
}
export interface MergeBlocks {
  kind: Kind89;
  leadingId: Leadingid;
  leadingRevision: Leadingrevision;
  opId: Opid3;
  trailingId: Trailingid;
  trailingRevision: Trailingrevision;
}
export interface InsertParagraph {
  contextBlockId: Contextblockid;
  contextRevision: Contextrevision;
  kind: Kind90;
  opId: Opid4;
  placement: AuthoredPlacement;
  text: Text24;
}
export interface AuthoredPlacement {
  afterId: Afterid4;
  parentId: Parentid6;
}
export interface CopyBlocks {
  kind: Kind91;
  opId: Opid5;
  placement: AuthoredPlacement;
  sources: Sources5;
}
export interface CopyFragment {
  kind: Kind92;
  opId: Opid6;
  placement: AuthoredPlacement;
  source: AuthoredRange;
}
export interface PasteInline {
  destination: AuthoredRange;
  kind: Kind93;
  opId: Opid7;
  source: Source2;
}
export interface SameProjectClipboard {
  clipboardCaptureId: Clipboardcaptureid;
  kind: Kind94;
}
export interface LiteralPaste {
  content: Content29;
  kind: Kind95;
}
export interface PasteBlocks {
  kind: Kind96;
  opId: Opid8;
  placement: AuthoredPlacement;
  source: SameProjectClipboard;
}
export interface MoveBlock1 {
  beforeRevision: Beforerevision16;
  blockId: Blockid18;
  kind: Kind97;
  opId: Opid9;
  placement: AuthoredPlacement;
}
export interface RemoveOccurrences {
  blocks: Blocks9;
  kind: Kind98;
  opId: Opid10;
}
export interface DeleteEntity {
  beforeRevision: Beforerevision17;
  kind: Kind99;
  opId: Opid11;
  recordId: Recordid17;
}
export interface BuiltinPanel {
  command: RichPanelRequest;
  kind: Kind100;
  opId: Opid12;
  placementContext?: PanelPlacementContext | null;
}
export interface RichPanelRequest {
  beforeRecordId?: Beforerecordid;
  capture: ActionCapture;
  documentRevision: Documentrevision5;
  factsRevision: Factsrevision1;
  groupId?: Groupid;
  jobId?: Jobid7;
  operation: Operation2;
  periodId?: Periodid1;
  recordId?: Recordid18;
  recordKind?: Recordkind;
  values?: Values1;
}
export interface Values1 {
  [k: string]: string;
}
export interface PanelPlacementContext {
  contextBlockId: Contextblockid1;
  placement: AuthoredPlacement;
}
export interface FormatBlocks {
  kind: Kind101;
  opId: Opid13;
  patch: BlockFormatPatch;
  targets: Targets1;
}
export interface ResolveTemplateSync {
  beforeLifecycleId: Beforelifecycleid3;
  beforeRecordHash: Beforerecordhash1;
  kind: Kind102;
  opId: Opid14;
  syncId: Syncid1;
}
/**
 * A bound link's URL: its URL cell and target change together; the label stays its own cell.
 */
export interface SetLinkTarget {
  beforeRevision: Beforerevision18;
  blockId: Blockid19;
  href: Href3;
  kind: Kind103;
  occurrenceId: Occurrenceid5;
  opId: Opid15;
}
export interface ExportCommand {
  editorToken: Editortoken4;
  schemaVersion: Schemaversion26;
  snapshot: TemplateSnapshotIdentity;
}
export interface ExportRetry {
  editorToken: Editortoken5;
}
export interface ExtractResult {
  byteLength: Bytelength;
  byteRef: Byteref1;
  byteSha256: Bytesha2561;
  gaps: Gaps;
  links: Links1;
  mimeType: Mimetype3;
  originalName: Originalname1;
  pageCount?: Pagecount;
  parser: Parser1;
  parserVersion: Parserversion1;
  sourceId: Sourceid5;
  sourceKind: Sourcekind;
  units: Units1;
}
export interface ExtractGap {
  code: Code7;
  location: ExtractLocation;
}
export interface ExtractLocation {
  column?: Column2;
  kind: Kind104;
  page?: Page4;
  paragraph?: Paragraph;
  part?: Part1;
  row?: Row3;
  table?: Table2;
}
export interface ExtractLink {
  part: Part2;
  relationshipId: Relationshipid;
  target: Target3;
}
export interface ExtractUnit {
  id: Id111;
  location: ExtractLocation;
  order: Order2;
  structure?: SourceStructure | null;
  text: Text25;
}
export interface HistoryRequestV1 {
  baseRevision: Baserevision3;
  clientMutationId: Clientmutationid4;
  direction: Direction1;
  editorToken: Editortoken6;
  expectedActionId: Expectedactionid1;
}
export interface ImportCommand {
  allowTextRewrite?: Allowtextrewrite3;
  clientRequestId?: Clientrequestid3;
  effort?: Effort2;
  kind: Kind105;
  operationId?: Operationid6;
  taskId?: Taskid6;
}
export interface Preferences {
  automaticAnalysis: Automaticanalysis;
  enabledProviders?: Enabledproviders;
  importMinutes?: Importminutes;
  projectMegabytes?: Projectmegabytes;
  rewriteReasoningEffort?: Rewritereasoningeffort;
  schemaVersion: Schemaversion27;
  selectedFallbackModel?: Selectedfallbackmodel;
  selectedImportModel?: Selectedimportmodel;
  selectedModel: Selectedmodel;
  selectedRewriteModel?: Selectedrewritemodel;
  theme: Theme;
}
export interface ProjectOpenResultV1 {
  editorToken: Editortoken7;
  history: HistoryStateV1;
  response: TemplateProjectResponseV1;
  schemaVersion: Schemaversion28;
  tasks: Tasks1;
}
export interface TaskStatusV1 {
  detail: Detail1;
  elapsed: Elapsed;
  error: Error1;
  id: Id112;
  kind: Kind106;
  projectId: Projectid14;
  stage: Stage1;
  startedAt: Startedat2;
  state: State15;
}
export interface Detail1 {
  [k: string]: unknown;
}
export interface ProposeChangesV1 {
  ops: Ops1;
  summary: Summary1;
}
export interface PublishFindingsV1 {
  findings: Findings2;
}
export interface FindingInputV1 {
  message: Message3;
  severity?: Severity1;
  sourceIds?: Sourceids1;
  targets?: Targets2;
}
export interface FindingTargetV1 {
  blockId?: Blockid20;
  cellId?: Cellid13;
  end?: End7;
  fieldKey?: Fieldkey11;
  recordId?: Recordid19;
  start?: Start8;
}
export interface Registry {
  entries: Entries1;
  schemaVersion: Schemaversion29;
}
export interface RegistryEntry {
  cleanupStatus: Cleanupstatus;
  projectId: Projectid15;
  title: Title11;
  tombstoned: Tombstoned;
  updatedAt: Updatedat3;
}
export interface RenameRequestV1 {
  baseRevision: Baserevision4;
  editorToken: Editortoken8;
  title: Title12;
}
/**
 * The body of a 409 for a stale base: the client drops what was applied and re-issues or reports the rest.
 */
export interface RevisionConflictV1 {
  appliedClientMutationIds: Appliedclientmutationids;
  error: Error2;
  revision: Revision61;
}
export interface Error2 {
  [k: string]: unknown;
}
export interface RewriteCancelRequestV1 {
  editorToken: Editortoken9;
  requestId: Requestid;
}
export interface RewritePreviewRequestV1 {
  editorToken: Editortoken10;
  instruction: Instruction2;
  range: AuthoredRange;
  requestId: Requestid1;
  snapshot: TemplateSnapshotIdentity;
}
export interface RichDocumentV1 {
  regions: Regions2;
  revision: Revision63;
  schemaVersion: Schemaversion30;
}
export interface RichRegion {
  blocks: Blocks10;
  id: Id113;
  revision: Revision62;
  role: Role7;
}
export interface RulesSettings {
  markdown: Markdown1;
  presets: RulePresets;
  revision: Revision64;
  sha256: Sha2567;
}
export interface RulePresets {
  clarify: Clarify;
  shorten: Shorten;
}
export interface RulesSettingsError {
  error: RulesErrorPayload;
  requiredHeadings: Requiredheadings;
}
export interface RulesErrorPayload {
  code: Code8;
  retryable: Retryable;
  stage: Stage2;
}
export interface SaveAnalysisPreference {
  automaticAnalysis: Automaticanalysis1;
}
export interface SaveImportModelPreference {
  model: Model3;
}
export interface SaveLimitsPreference {
  importMinutes: Importminutes1;
  projectMegabytes: Projectmegabytes1;
}
export interface SaveRulesRequest {
  baseRevision: Baserevision5;
  markdown: Markdown2;
}
export interface TemplateClipboardCaptureV1 {
  clipboardCaptureId: Clipboardcaptureid1;
  projectId: Projectid16;
  schemaVersion: Schemaversion31;
  selection: Selection1;
  sourceSnapshot: TemplateSnapshotIdentity;
}
export interface TemplatePackage {
  assets: Assets4;
  blocks: Blocks11;
  compilerVersion: Compilerversion1;
  configHash: Confighash1;
  definition: TemplateDefinition;
  id: Id115;
  manifest: CompilationManifest;
  operationVersion: Operationversion1;
  originalBase64: Originalbase641;
  originalFormat: Originalformat1;
  originalHash: Originalhash1;
  packageHash: Packagehash8;
  projectionVersion: Projectionversion1;
  recipe: CompiledRecipe;
  revision: Revision65;
  schemaVersion: Schemaversion32;
}
export interface CapturedAsset {
  bytesBase64: Bytesbase641;
  id: Id114;
  mimeType: Mimetype4;
  path: Path5;
  role: Role8;
  sha256: Sha2568;
  size: Size8;
}
export interface TemplateRenderRequestV1 {
  assets: Assets5;
  document: RichDocumentV2;
  documentHash: Documenthash4;
  facts: WorkingFactsV2;
  factsHash: Factshash4;
  package: TemplatePackage;
  packageHash: Packagehash9;
  presentationHash: Presentationhash3;
  renderInputVersion: Renderinputversion2;
  renderer: TemplateRendererIdentity;
  schemaVersion: Schemaversion33;
}
/**
 * A rewrite preview: the selected source and the model's text; the document changes only through Apply.
 */
export interface TemplateRewritePreviewV1 {
  range: AuthoredRange;
  requestId: Requestid2;
  schemaVersion: Schemaversion34;
  snapshot: TemplateSnapshotIdentity;
  source: Source3;
  text: Text26;
}
export interface WorkingFacts {
  extraction?: ExtractionReport | null;
  mode?: Mode3;
  records: Records3;
  revision: Revision66;
  tombstones: Tombstones1;
}
