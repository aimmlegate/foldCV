export type Editortoken = string;
export type Schemaversion = 1;
export type Documenthash = string;
export type Documentrevision = number;
export type Factshash = string;
export type Packagehash = string;
export type Presentationhash = string;
export type Projectid = string;
export type Projectrevision = number;

export interface ExportCommand {
  editorToken: Editortoken;
  schemaVersion: Schemaversion;
  snapshot: TemplateSnapshotIdentity;
}
export interface TemplateSnapshotIdentity {
  documentHash: Documenthash;
  documentRevision: Documentrevision;
  factsHash: Factshash;
  packageHash: Packagehash;
  presentationHash: Presentationhash;
  projectId: Projectid;
  projectRevision: Projectrevision;
}
