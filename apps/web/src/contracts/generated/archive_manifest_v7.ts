export type Appversion = string;
/**
 * @minItems 1
 * @maxItems 47
 */
export type Entries = [TemplateArchiveEntry, ...TemplateArchiveEntry[]];
export type Path = string;
export type Role = "workspace" | "source_original" | "render" | "user_image" | "template_package" | "template_asset";
export type Sha256 = string;
export type Size = number;
export type Projectid = string;
export type Schemaversion = 7;

export interface ArchiveManifestV7 {
  appVersion: Appversion;
  entries: Entries;
  projectId: Projectid;
  schemaVersion: Schemaversion;
}
export interface TemplateArchiveEntry {
  path: Path;
  role: Role;
  sha256: Sha256;
  size: Size;
}
