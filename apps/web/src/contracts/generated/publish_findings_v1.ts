export type Findings =
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
export type Message = string;
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
/**
 * @maxItems 20
 */
export type Targets =
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
export type Blockid = string | null;
export type Cellid = string | null;
export type End = number | null;
export type Fieldkey = string | null;
export type Recordid = string | null;
export type Start = number | null;

export interface PublishFindingsV1 {
  findings: Findings;
}
export interface FindingInputV1 {
  message: Message;
  severity?: Severity;
  sourceIds?: Sourceids;
  targets?: Targets;
}
export interface FindingTargetV1 {
  blockId?: Blockid;
  cellId?: Cellid;
  end?: End;
  fieldKey?: Fieldkey;
  recordId?: Recordid;
  start?: Start;
}
