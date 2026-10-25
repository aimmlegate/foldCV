export type Allowedits = boolean;
export type Allowweb = boolean;
export type Message = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Scope = "resume" | "selection" | "project" | "chat";

export interface AssistantMessageCheckV1 {
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  message: Message;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  scope?: Scope;
}
