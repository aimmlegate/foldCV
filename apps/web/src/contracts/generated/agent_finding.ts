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
export type Id = string;
export type Kind =
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
export type Text = string;
export type Id1 = string;
export type Message = string;
export type Runid = string;
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

export interface AgentFinding {
  anchors: Anchors;
  id: Id1;
  message: Message;
  runId: Runid;
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
  text: Text;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind;
  revision: Revision;
}
