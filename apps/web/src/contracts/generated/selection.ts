export type Dependencyfingerprint = string;
export type Documentrevision = number;
export type Projectid = string;
/**
 * @minItems 1
 */
export type Spans = [SelectionSpan, ...SelectionSpan[]];
export type Capturedtext = string;
export type Fieldid = string;
export type End = number;
export type Start = number;

export interface Selection {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision;
  projectId: Projectid;
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
