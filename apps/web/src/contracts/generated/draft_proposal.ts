export type Blocks = [DraftBlock, ...DraftBlock[]];
export type Blockid = string;
/**
 * @minItems 1
 * @maxItems 200
 */
export type Factids = [string, ...string[]];
export type Text = string;
export type Instructionversion = 1;

export interface DraftProposal {
  blocks: Blocks;
  instructionVersion?: Instructionversion;
}
export interface DraftBlock {
  blockId: Blockid;
  factIds: Factids;
  text: Text;
}
