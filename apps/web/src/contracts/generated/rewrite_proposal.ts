export type Blockid = string;
/**
 * @minItems 1
 * @maxItems 200
 */
export type Factids = [string, ...string[]];
export type Instructionversion = 1;
export type Replacementtext = string;

export interface RewriteProposal {
  blockId: Blockid;
  factIds: Factids;
  instructionVersion?: Instructionversion;
  replacementText: Replacementtext;
}
