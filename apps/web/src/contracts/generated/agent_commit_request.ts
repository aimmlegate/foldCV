export type Epoch = number;
export type Token = string;
export type Requestsha256 = string;
export type Ticket = string;

export interface AgentCommitRequest {
  owner: AgentOwner;
  requestSha256: Requestsha256;
  ticket: Ticket;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
}
