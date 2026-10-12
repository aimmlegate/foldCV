export type Clientrequestid = string;
export type Documentrevision = number;
export type Projectrevision = number;

export interface GuiExportRequest {
  clientRequestId: Clientrequestid;
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
}
