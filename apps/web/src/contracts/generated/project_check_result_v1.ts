export type Blocks = number;
export type Documentrevision = number;
/**
 * @maxItems 50
 */
export type Emptyblocks = string[];
export type Facts = number;
/**
 * @maxItems 50
 */
export type Linkswithouttarget = string[];
export type Blockids = string[];
export type Id = string;
/**
 * @maxItems 50
 */
export type Openimportissues = CheckedImportIssueV1[];
export type Projectrevision = number;
export type Schemaversion = 1;

/**
 * The deterministic resume check over the committed workspace; no model call and no write.
 */
export interface ProjectCheckResultV1 {
  blocks: Blocks;
  documentRevision: Documentrevision;
  emptyBlocks: Emptyblocks;
  facts: Facts;
  linksWithoutTarget: Linkswithouttarget;
  openImportIssues: Openimportissues;
  projectRevision: Projectrevision;
  schemaVersion: Schemaversion;
}
export interface CheckedImportIssueV1 {
  blockIds: Blockids;
  id: Id;
}
