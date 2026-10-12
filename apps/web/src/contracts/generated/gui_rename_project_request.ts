export type Baserevision = number;
export type Title = string;

export interface GuiRenameProjectRequest {
  baseRevision: Baserevision;
  title: Title;
}
