export type Key = string;
/**
 * @maxItems 5
 */
export type Marks =
  | []
  | ["bold" | "italic" | "underline" | "strike" | "code"]
  | ["bold" | "italic" | "underline" | "strike" | "code", "bold" | "italic" | "underline" | "strike" | "code"]
  | [
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code"
    ]
  | [
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code"
    ]
  | [
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code",
      "bold" | "italic" | "underline" | "strike" | "code"
    ];
export type Text = string;
/**
 * @maxItems 100
 */
export type Content = AgentInline[];
export type Kind = "replace_text";
export type Blockid = string;
export type Cellid = string | null;
export type End = number;
export type Field = "content" | "caption";
export type Snapshotid = string;
export type Start = number;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Blocks = [AgentNewBlock, ...AgentNewBlock[]];
/**
 * @maxItems 100
 */
export type Content1 = AgentInline[];
export type Key1 = string;
export type Kind1 = "paragraph" | "bullet_list_item" | "numbered_list_item";
export type Afterid = string | null;
export type Parentid = string;
export type Snapshotid1 = string;
export type Kind2 = "insert_blocks";
/**
 * @minItems 1
 * @maxItems 100
 */
export type Blockids = [string, ...string[]];
export type Kind3 = "delete_blocks";
export type Snapshotid2 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Blockids1 = [string, ...string[]];
export type Kind4 = "move_blocks";
export type Snapshotid3 = string;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Evidence =
  | [AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ]
  | [
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection,
      AgentSourceEvidence | AgentFactEvidence | AgentUserCorrection
    ];
export type Kind5 = "source";
export type Sourceid = string;
export type Unitid = string;
export type Kind6 = "fact";
export type Recordid = string;
export type Kind7 = "user_correction";
export type Quote = string;
export type Fieldkey =
  | "name"
  | "title"
  | "location"
  | "label"
  | "value"
  | "employer"
  | "role"
  | "display"
  | "canonical_id"
  | "institution"
  | "qualification"
  | "specialty"
  | "completion"
  | "language"
  | "level"
  | "issuer"
  | "date"
  | "start"
  | "end"
  | "present";
export type Kind8 = "update_fact";
export type Periodid = string | null;
export type Recordid1 = string;
export type Snapshotid4 = string;
export type Status = "known" | "uncertain";
export type Text1 = string;
export type Value = string | PartialDate | boolean | MetricValue | null;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
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
export type Key2 = string;
export type Kind9 = "create_fact";
export type Ownerrecordid = string | null;
/**
 * @maxItems 20
 */
export type Periods =
  | []
  | [AgentNewPeriod]
  | [AgentNewPeriod, AgentNewPeriod]
  | [AgentNewPeriod, AgentNewPeriod, AgentNewPeriod]
  | [AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod]
  | [AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod]
  | [AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod]
  | [AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod, AgentNewPeriod]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ]
  | [
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod,
      AgentNewPeriod
    ];
export type Recordkind =
  | "candidate"
  | "detail"
  | "employment"
  | "technology"
  | "education"
  | "language"
  | "certification"
  | "claim"
  | "metric";
export type Kind10 = "delete_fact";
export type Recordid2 = string;
export type Snapshotid5 = string;
/**
 * @maxItems 100
 */
export type Operations = (
  | AgentReplaceText
  | AgentInsertBlocks
  | AgentDeleteBlocks
  | AgentMoveBlocks
  | AgentUpdateFact
  | AgentCreateFact
  | AgentDeleteFact
)[];
/**
 * @maxItems 24
 */
export type Snapshotids = string[];

export interface AgentPrepareRequest {
  key: Key;
  operations: Operations;
  snapshotIds: Snapshotids;
}
export interface AgentReplaceText {
  content: Content;
  kind: Kind;
  target: AgentRange;
}
export interface AgentInline {
  marks?: Marks;
  text: Text;
}
export interface AgentRange {
  blockId: Blockid;
  cellId: Cellid;
  end: End;
  field: Field;
  snapshotId: Snapshotid;
  start: Start;
}
export interface AgentInsertBlocks {
  blocks: Blocks;
  destination: AgentBlockAnchor;
  kind: Kind2;
}
export interface AgentNewBlock {
  content: Content1;
  key: Key1;
  kind: Kind1;
}
export interface AgentBlockAnchor {
  afterId: Afterid;
  parentId: Parentid;
  snapshotId: Snapshotid1;
}
export interface AgentDeleteBlocks {
  blockIds: Blockids;
  kind: Kind3;
  snapshotId: Snapshotid2;
}
export interface AgentMoveBlocks {
  blockIds: Blockids1;
  destination: AgentBlockAnchor;
  kind: Kind4;
  snapshotId: Snapshotid3;
}
export interface AgentUpdateFact {
  evidence: Evidence;
  fieldKey: Fieldkey;
  kind: Kind8;
  periodId?: Periodid;
  recordId: Recordid1;
  snapshotId: Snapshotid4;
  value: AgentFactValue;
}
export interface AgentSourceEvidence {
  kind: Kind5;
  sourceId: Sourceid;
  unitId: Unitid;
}
export interface AgentFactEvidence {
  kind: Kind6;
  recordId: Recordid;
}
export interface AgentUserCorrection {
  kind: Kind7;
  quote: Quote;
}
export interface AgentFactValue {
  status: Status;
  text: Text1;
  value: Value;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
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
export interface AgentCreateFact {
  correction: AgentUserCorrection;
  key: Key2;
  kind: Kind9;
  ownerRecordId: Ownerrecordid;
  periods?: Periods;
  recordKind: Recordkind;
  values: Values;
}
export interface AgentNewPeriod {
  end: AgentFactValue;
  present: AgentFactValue;
  start: AgentFactValue;
}
export interface Values {
  [k: string]: AgentFactValue;
}
export interface AgentDeleteFact {
  correction: AgentUserCorrection;
  kind: Kind10;
  recordId: Recordid2;
  snapshotId: Snapshotid5;
}
