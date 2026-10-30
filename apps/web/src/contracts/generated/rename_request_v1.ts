export type Baserevision = number;
export type Editortoken = string;
export type Title = string;

export interface RenameRequestV1 {
  baseRevision: Baserevision;
  editorToken: Editortoken;
  title: Title;
}
