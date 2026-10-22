export type Authorityhash = string;
export type Authorizationid = string;
export type Kind = "resume_import";
export type Operationid = string;
export type Protocol = "template_import_v1";

export interface ResumeTemplateImportV1 {
  authorityHash: Authorityhash;
  authorizationId: Authorizationid;
  kind: Kind;
  operationId: Operationid;
  protocol: Protocol;
}
