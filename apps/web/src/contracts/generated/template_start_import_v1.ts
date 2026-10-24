export type Allowtextrewrite = boolean;
export type Authorityhash = string;
export type Dependencyhash = string;
export type Adapter = string;
export type Capabilityprofile = string;
export type Capabilityversion = string;
export type Configurationhash = string;
export type Effort = string;
export type Model = string;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Packagehash = string;
export type Callcap = number;
export type Cleanupseconds = 5;
export type Concurrency = 1;
export type Fallbackrepairs = 1;
export type Finalizationseconds = number;
export type Primaryrepairs = 1;
export type Processingseconds = number;
export type Clientrequestid = string;
export type Kind = "start_new_import";
export type Protocol = "template_import_v1";

export interface StartTemplateImportV1 {
  capture: ImportCapture;
  clientRequestId: Clientrequestid;
  kind: Kind;
  protocol: Protocol;
}
export interface ImportCapture {
  allowTextRewrite: Allowtextrewrite;
  authorityHash: Authorityhash;
  dependencyHash: Dependencyhash;
  factRevisions: Factrevisions;
  fallback: ModelCapture | null;
  formattingAsOf: PartialDate;
  packageHash: Packagehash;
  policy: RuntimePolicy;
  primary: ModelCapture;
  sourceHashes: Sourcehashes;
}
export interface Factrevisions {
  [k: string]: number;
}
export interface ModelCapture {
  adapter: Adapter;
  capabilityProfile: Capabilityprofile;
  capabilityVersion: Capabilityversion;
  configurationHash: Configurationhash;
  effort: Effort;
  model: Model;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface RuntimePolicy {
  callCap: Callcap;
  cleanupSeconds: Cleanupseconds;
  concurrency: Concurrency;
  fallbackRepairs: Fallbackrepairs;
  finalizationSeconds: Finalizationseconds;
  primaryRepairs: Primaryrepairs;
  processingSeconds: Processingseconds;
}
export interface Sourcehashes {
  [k: string]: string;
}
