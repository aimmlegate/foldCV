export type Baserevision = number;
export type Blockid = string;
export type Blockrevision = number;
export type Dependencyhash = string;
export type Factids = string[];
export type Blockid1 = string;
export type Code = "MISSING_REQUIRED" | "QUALIFIER_LOSS" | "ATTRIBUTION_LOSS" | "SOURCE_REVIEW";
export type Factid = string;
export type Message = string;
export type Issues = RewriteIssue[];
export type Replacementtext = string;
export type Transportversion = 1;

export interface RewriteResult {
  baseRevision: Baserevision;
  blockId: Blockid;
  blockRevision: Blockrevision;
  dependencyHash: Dependencyhash;
  factIds: Factids;
  issues: Issues;
  replacementText: Replacementtext;
  transportVersion?: Transportversion;
}
export interface RewriteIssue {
  blockId: Blockid1;
  code: Code;
  factId: Factid;
  message: Message;
}
