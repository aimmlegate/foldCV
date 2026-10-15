export type Expiresat = string;
export type Epoch = number;
export type Token = string;
export type Projectid = string;
export type Sessionid = string;

export interface AgentLease {
  expiresAt: Expiresat;
  owner: AgentOwner;
  projectId: Projectid;
  sessionId: Sessionid;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
}
