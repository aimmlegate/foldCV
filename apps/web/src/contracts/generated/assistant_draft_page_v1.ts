export type Complete = boolean;
export type Content = string;
export type Contentsha256 = string;
export type Nextcursor = string | null;
export type Offset = number;
export type Protocolversion = 1;
export type Readcredit = false;
export type Schemaversion = 1;
export type Totalcharacters = number;

export interface AssistantDraftPageV1 {
  complete: Complete;
  content: Content;
  contentSha256: Contentsha256;
  nextCursor: Nextcursor;
  offset: Offset;
  protocolVersion?: Protocolversion;
  readCredit?: Readcredit;
  schemaVersion?: Schemaversion;
  totalCharacters: Totalcharacters;
}
