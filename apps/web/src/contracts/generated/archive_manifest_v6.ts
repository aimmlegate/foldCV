export type Appversion = string;
/**
 * @minItems 1
 * @maxItems 47
 */
export type Entries = [RichArchiveEntry, ...RichArchiveEntry[]];
export type Path = string;
export type Role = "workspace" | "source_original" | "render" | "user_image";
export type Sha256 = string;
export type Size = number;
export type Projectid = string;
export type Schemaversion = 6;

export interface ArchiveManifestV6 {
  appVersion: Appversion;
  entries: Entries;
  projectId: Projectid;
  schemaVersion: Schemaversion;
}
export interface RichArchiveEntry {
  path: Path;
  role: Role;
  sha256: Sha256;
  size: Size;
}
