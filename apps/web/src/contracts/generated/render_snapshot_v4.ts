export type Artifactavailable = boolean;
export type Documentrevision = number;
export type Path = string;
export type Sha256 = string;
export type Size = number;
export type Id = string;
export type Pdf = null;
export type Projectrevision = number;
export type Renderinputfingerprint = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templateid = string;
export type Templatesha256 = string;
export type Templateversion = string;

export interface RenderSnapshotV4 {
  artifactAvailable: Artifactavailable;
  documentRevision: Documentrevision;
  docx: AssetRef;
  id: Id;
  pdf: Pdf;
  projectRevision: Projectrevision;
  renderInputFingerprint: Renderinputfingerprint;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateId: Templateid;
  templateSha256: Templatesha256;
  templateVersion: Templateversion;
}
export interface AssetRef {
  path: Path;
  sha256: Sha256;
  size: Size;
}
