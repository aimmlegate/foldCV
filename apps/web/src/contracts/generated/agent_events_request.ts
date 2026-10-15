export type Aftersequence = number;
export type Epoch = number;
export type Token = string;

export interface AgentEventsRequest {
  afterSequence: Aftersequence;
  owner: AgentOwner;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
}
