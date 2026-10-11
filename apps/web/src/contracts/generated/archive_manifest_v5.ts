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
export type Projectid = string;
export type Schemaversion = 5;

export interface ArchiveManifestV5 {
  appVersion: Appversion;
  entries: Entries;
  projectId: Projectid;
  schemaVersion: Schemaversion;
}
export interface ArchiveEntry {
  path: Path;
  role: Role;
  sha256: Sha256;
  uncompressedSize: Uncompressedsize;
}
