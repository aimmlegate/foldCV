export type Appversion = string;
/**
 * @minItems 1
 * @maxItems 47
 */
export type Entries = [ArchiveEntry, ...ArchiveEntry[]];
export type Path = string;
export type Role = "project" | "workspace" | "source_original" | "template_asset" | "render";
export type Sha256 = string;
export type Uncompressedsize = number;
export type Projectid = string | null;
export type Rendererversion = string | null;
export type Schemaversion = 4;
export type Templateassetsincluded = boolean;
export type Templatepackagesha256 = string | null;

export interface ArchiveManifest {
  appVersion: Appversion;
  entries: Entries;
  projectId: Projectid;
  rendererVersion: Rendererversion;
  schemaVersion: Schemaversion;
  templateAssetsIncluded: Templateassetsincluded;
  templatePackageSha256: Templatepackagesha256;
}
export interface ArchiveEntry {
  path: Path;
  role: Role;
  sha256: Sha256;
  uncompressedSize: Uncompressedsize;
}
