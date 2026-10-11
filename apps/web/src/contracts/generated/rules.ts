export type Markdown = string;
export type Revision = number;
export type Sha256 = string;

export interface Rules {
  markdown: Markdown;
  revision: Revision;
  sha256: Sha256;
}
