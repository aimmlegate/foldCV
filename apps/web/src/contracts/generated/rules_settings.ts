export type Markdown = string;
export type Clarify = string;
export type Shorten = string;
export type Revision = number;
export type Sha256 = string;

export interface RulesSettings {
  markdown: Markdown;
  presets: RulePresets;
  revision: Revision;
  sha256: Sha256;
}
export interface RulePresets {
  clarify: Clarify;
  shorten: Shorten;
}
