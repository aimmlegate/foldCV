export type Findings =
  | []
  | [AgentFindingInput]
  | [AgentFindingInput, AgentFindingInput]
  | [AgentFindingInput, AgentFindingInput, AgentFindingInput]
  | [AgentFindingInput, AgentFindingInput, AgentFindingInput, AgentFindingInput]
  | [AgentFindingInput, AgentFindingInput, AgentFindingInput, AgentFindingInput, AgentFindingInput]
  | [AgentFindingInput, AgentFindingInput, AgentFindingInput, AgentFindingInput, AgentFindingInput, AgentFindingInput]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
    ]
  | [
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput,
      AgentFindingInput
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
  | [AgentFindingTarget]
  | [AgentFindingTarget, AgentFindingTarget]
  | [AgentFindingTarget, AgentFindingTarget, AgentFindingTarget]
  | [AgentFindingTarget, AgentFindingTarget, AgentFindingTarget, AgentFindingTarget]
  | [AgentFindingTarget, AgentFindingTarget, AgentFindingTarget, AgentFindingTarget, AgentFindingTarget]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ]
  | [
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget,
      AgentFindingTarget
    ];
export type Blockid = string | null;
export type Cellid = string | null;
export type End = number | null;
export type Fieldkey = string | null;
export type Recordid = string | null;
export type Snapshotid = string;
export type Start = number | null;

export interface AgentPublishFindings {
  findings: Findings;
}
export interface AgentFindingInput {
  message: Message;
  severity: Severity;
  sourceIds: Sourceids;
  targets: Targets;
}
export interface AgentFindingTarget {
  blockId: Blockid;
  cellId: Cellid;
  end: End;
  fieldKey: Fieldkey;
  recordId: Recordid;
  snapshotId: Snapshotid;
  start: Start;
}
