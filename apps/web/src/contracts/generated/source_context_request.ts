export type Documentrevision = number;
export type Fieldids = string[];
export type Projectid = string;
export type Dependencyfingerprint = string;
export type Documentrevision1 = number;
export type Projectid1 = string;
/**
 * @minItems 1
 */
export type Spans = [SelectionSpan, ...SelectionSpan[]];
export type Capturedtext = string;
export type Fieldid = string;
export type End = number;
export type Start = number;

export interface SourceContextRequest {
  documentRevision: Documentrevision;
  fieldIds: Fieldids;
  projectId: Projectid;
  selection: Selection | null;
}
export interface Selection {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision1;
  projectId: Projectid1;
  spans: Spans;
}
export interface SelectionSpan {
  capturedText: Capturedtext;
  fieldId: Fieldid;
  range: Range;
}
export interface Range {
  end: End;
  start: Start;
}
