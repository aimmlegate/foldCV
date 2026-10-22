export type Schemaversion = 1;
export type Kind = "set";
export type Pointer = string;
export type Valuewire = string;
export type Kind1 = "insert";
export type Pointer1 = string;
export type Valuewire1 = string;
export type Kind2 = "remove";
export type Pointer2 = string;
export type Beforetexthash = string;
export type End = number;
export type Kind3 = "splice_text";
export type Pointer3 = string;
export type Start = number;
export type Text = string;
/**
 * @maxItems 1000
 */
export type Steps = (PatchSet | PatchInsert | PatchRemove | PatchSpliceText)[];

export interface CanonicalPatchV1 {
  schemaVersion: Schemaversion;
  steps: Steps;
}
export interface PatchSet {
  kind: Kind;
  pointer: Pointer;
  valueWire: Valuewire;
}
export interface PatchInsert {
  kind: Kind1;
  pointer: Pointer1;
  valueWire: Valuewire1;
}
export interface PatchRemove {
  kind: Kind2;
  pointer: Pointer2;
}
export interface PatchSpliceText {
  beforeTextHash: Beforetexthash;
  end: End;
  kind: Kind3;
  pointer: Pointer3;
  start: Start;
  text: Text;
}
