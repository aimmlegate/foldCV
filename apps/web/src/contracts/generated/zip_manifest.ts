export type Appversion = string;
export type Path = string;
export type Role = "project" | "source_original" | "source_extracted" | "template_asset" | "render" | "checks";
export type Sha256 = string;
export type Uncompressedsize = number;
export type Entries = ZipEntry[];
export type Projectid = string;
export type Rendererversion = string;
export type Schemaversion = 3;

export interface ZipManifest {
  appVersion: Appversion;
  entries: Entries;
  projectId: Projectid;
  rendererVersion: Rendererversion;
  schemaVersion: Schemaversion;
}
export interface ZipEntry {
  path: Path;
  role: Role;
  sha256: Sha256;
  uncompressedSize: Uncompressedsize;
}
