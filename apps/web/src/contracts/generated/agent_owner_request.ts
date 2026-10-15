export type Epoch = number;
export type Token = string;

export interface AgentOwnerRequest {
  owner: AgentOwner;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
}
