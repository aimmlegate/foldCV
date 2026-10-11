export type Baserevision = number;
export type Blockid = string;
/**
 * @minItems 1
 * @maxItems 200
 */
export type Factids = [string, ...string[]];
export type Text = string;
export type Blocks = DraftBlock[];
export type Blockid1 = string;
export type Code = "MISSING_REQUIRED" | "QUALIFIER_LOSS" | "ATTRIBUTION_LOSS" | "SOURCE_REVIEW";
export type Factid = string;
export type Message = string;
export type Issues = DraftIssue[];
export type Sourcefingerprint = string;
export type Transportversion = 1;

export interface DraftResult {
  baseRevision: Baserevision;
  blocks: Blocks;
  issues: Issues;
  sourceFingerprint: Sourcefingerprint;
  transportVersion?: Transportversion;
}
export interface DraftBlock {
  blockId: Blockid;
  factIds: Factids;
  text: Text;
}
export interface DraftIssue {
  blockId: Blockid1;
  code: Code;
  factId: Factid;
  message: Message;
}
