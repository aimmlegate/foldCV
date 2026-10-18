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
/**
 * @maxItems 100
 */
export type Affected = AgentAnchor[];
export type Affectedcount = number | null;
export type Batchid = string | null;
export type Disposition = "prepared" | "no_change";
export type Preview = string;

export interface AgentPrepareResult {
  affected: Affected;
  affectedCount?: Affectedcount;
  batchId: Batchid;
  disposition: Disposition;
  preview: Preview;
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
