export type Appliedclientmutationids = string[];
export type Revision = number;

/**
 * The body of a 409 for a stale base: the client drops what was applied and re-issues or reports the rest.
 */
export interface RevisionConflictV1 {
  appliedClientMutationIds: Appliedclientmutationids;
  error: Error;
  revision: Revision;
}
export interface Error {
  [k: string]: unknown;
}
