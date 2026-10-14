export type Uncertain = string[];
export type Blockid = string;
export type Cellid = string | null;
export type Text = string;
/**
 * @maxItems 100
 */
export type Updates = NarrativeUpdate[];

export interface RichPanelProposal {
  uncertain?: Uncertain;
  updates: Updates;
}
export interface NarrativeUpdate {
  blockId: Blockid;
  cellId?: Cellid;
  text: Text;
}
