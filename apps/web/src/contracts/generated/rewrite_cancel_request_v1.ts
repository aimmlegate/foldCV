export type Editortoken = string;
export type Requestid = string;

export interface RewriteCancelRequestV1 {
  editorToken: Editortoken;
  requestId: Requestid;
}
