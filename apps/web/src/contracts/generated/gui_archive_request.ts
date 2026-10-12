export type Documentrevision = number;
export type Projectrevision = number;

export interface GuiArchiveRequest {
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
}
