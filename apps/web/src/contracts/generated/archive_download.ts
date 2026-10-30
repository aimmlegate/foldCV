export type Documentrevision = number;
export type Editortoken = string;
export type Projectrevision = number;

export interface ArchiveDownload {
  documentRevision: Documentrevision;
  editorToken: Editortoken;
  projectRevision: Projectrevision;
}
