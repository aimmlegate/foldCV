export type Clientrequestid = string;
export type Command =
  FixedProcessingCommand | FixedCompletionCommand | FixedRewriteCommand | FixedPanelCommand | FixedRetryCommand;
export type Allowtextrewrite = boolean;
export type Kind = "processing";
export type Kind1 = "completion";
/**
 * @maxItems 100
 */
export type Blockids = string[];
export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind2 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Dependencies = DependencyStamp[];
export type Sessionid = string;
export type Interpret = boolean;
/**
 * @maxItems 100
 */
export type Movedids = string[];
export type Fieldkey = string;
export type Recordid = string;
export type Rootid = string;
/**
 * @maxItems 100
 */
export type Removedfields = FieldReference[];
/**
 * @maxItems 100
 */
export type Removedrecordids = string[];
export type Kind3 = "rewrite";
export type Instruction = string;
export type Previewonly = boolean;
export type Blockid = string;
export type Cellid = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids1 = [string, ...string[]];
export type Kind4 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type Kind5 = "panel";
/**
 * @minItems 1
 * @maxItems 100
 */
export type Recordids = [string, ...string[]];
export type Kind6 = "retry" | "resolve";
export type Syncid = string;
export type Lineage = string;
export type Requestepoch = number;
export type Schemaversion = 1;

export interface JobFixedRequestV1 {
  clientRequestId: Clientrequestid;
  command: Command;
  lineage: Lineage;
  requestEpoch: Requestepoch;
  schemaVersion: Schemaversion;
}
export interface FixedProcessingCommand {
  allowTextRewrite?: Allowtextrewrite;
  kind: Kind;
}
export interface FixedCompletionCommand {
  kind: Kind1;
  request: RichCompletionRequest;
}
export interface RichCompletionRequest {
  blockIds: Blockids;
  capture: ActionCapture;
  interpret?: Interpret;
  movedIds: Movedids;
  removedFields: Removedfields;
  removedRecordIds?: Removedrecordids;
}
export interface ActionCapture {
  actionId: Actionid;
  actionToken: Actiontoken;
  dependencies: Dependencies;
  sessionId: Sessionid;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind2;
  revision: Revision;
}
export interface FieldReference {
  fieldKey: Fieldkey;
  recordId: Recordid;
  rootId: Rootid;
}
export interface FixedRewriteCommand {
  kind: Kind3;
  request: RichRewriteRequest;
}
export interface RichRewriteRequest {
  instruction: Instruction;
  previewOnly?: Previewonly;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids1;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind4;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid;
  cellId: Cellid;
  offset: Offset;
}
export interface FixedPanelCommand {
  kind: Kind5;
  request: RichPanelSyncRequest;
}
export interface RichPanelSyncRequest {
  capture: ActionCapture;
  recordIds: Recordids;
}
export interface FixedRetryCommand {
  capture: ActionCapture;
  kind: Kind6;
  syncId: Syncid;
}
