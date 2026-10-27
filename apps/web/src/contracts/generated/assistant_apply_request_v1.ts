export type Allowedits = boolean;
export type Clientmutationid = string;
export type Editortoken = string;

export interface AssistantApplyRequestV1 {
  allowEdits: Allowedits;
  clientMutationId: Clientmutationid;
  editorToken: Editortoken;
}
