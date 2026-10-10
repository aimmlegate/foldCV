export type Path = string;
export type Sha256 = string;
export type Size = number;
export type Assets = AssetRef[];
export type Contentpolicyversion = string;
export type Id = string;
export type Packagesha256 = string;
export type Version = string;

export interface TemplateManifest {
  assets: Assets;
  contentPolicyVersion: Contentpolicyversion;
  id: Id;
  packageSha256: Packagesha256;
  version: Version;
}
export interface AssetRef {
  path: Path;
  sha256: Sha256;
  size: Size;
}
