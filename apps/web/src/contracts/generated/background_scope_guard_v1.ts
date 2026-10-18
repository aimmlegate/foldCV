export type Fingerprint = string;
export type Generation = number;
export type Key = string;
export type Kind = "entity" | "structure" | "query" | "source" | "rules";
/**
 * @maxItems 4096
 */
export type Reads = GenerationStamp[];
export type Schemaversion = 1;
/**
 * @maxItems 4096
 */
export type Writes = GenerationStamp[];

export interface ScopeGuardV1 {
  reads: Reads;
  schemaVersion: Schemaversion;
  writes: Writes;
}
export interface GenerationStamp {
  fingerprint: Fingerprint;
  generation: Generation;
  key: Key;
  kind: Kind;
}
