export type Baserevision = number;
export type Blockid = string;
export type Blockrevision = number;
export type Dependencyhash = string;
export type Code = "NO_SAFE_CONTENT";
export type Retryable = false;
export type Stage = "rewrite";
export type Blockid1 = string;
export type Code1 = "MISSING_REQUIRED" | "QUALIFIER_LOSS" | "ATTRIBUTION_LOSS" | "SOURCE_REVIEW";
export type Factid = string;
export type Message = string;
/**
 * @maxItems 200
 */
export type Issues = RewriteIssue[];
export type Transportversion = 1;

export interface RewritePreflightFailure {
  baseRevision: Baserevision;
  blockId: Blockid;
  blockRevision: Blockrevision;
  dependencyHash: Dependencyhash;
  error: RewritePreflightError;
  issues: Issues;
  transportVersion?: Transportversion;
}
export interface RewritePreflightError {
  code: Code;
  retryable: Retryable;
  stage: Stage;
}
export interface RewriteIssue {
  blockId: Blockid1;
  code: Code1;
  factId: Factid;
  message: Message;
}
