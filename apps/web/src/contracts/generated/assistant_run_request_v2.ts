export type Allowedits = boolean;
export type Allowweb = boolean;
export type Clientrequestid = string;
export type Message = string;
/**
 * @maxItems 100
 */
export type Blockids = string[];
export type Text = string;

export interface AssistantRunRequestV2 {
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  clientRequestId: Clientrequestid;
  message: Message;
  selection?: AssistantSelectionV1 | null;
}
export interface AssistantSelectionV1 {
  blockIds: Blockids;
  text: Text;
}
