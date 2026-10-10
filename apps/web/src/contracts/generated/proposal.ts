export type Baseblockrevision = number;
export type Blockid = string;
export type Dependencyhash = string;
export type Evidencefactids = string[];
export type Findings = string[];
export type Id = string;
export type Kind = "draft_prose" | "rewrite_prose";
export type Operationid = string;
export type Replacementtext = string;

export interface Proposal {
  baseBlockRevision: Baseblockrevision;
  blockId: Blockid;
  dependencyHash: Dependencyhash;
  evidenceFactIds: Evidencefactids;
  findings: Findings;
  id: Id;
  kind: Kind;
  operationId: Operationid;
  replacementText: Replacementtext;
}
