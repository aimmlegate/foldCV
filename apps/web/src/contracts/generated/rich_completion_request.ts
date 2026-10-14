export type Blockids = string[];
export type Actionid = string;
export type Actiontoken = number;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
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
  kind: Kind;
  revision: Revision;
}
export interface FieldReference {
  fieldKey: Fieldkey;
  recordId: Recordid;
  rootId: Rootid;
}
