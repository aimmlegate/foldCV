export type Baserevision = number;
export type Markdown = string;

export interface SaveRulesRequest {
  baseRevision: Baserevision;
  markdown: Markdown;
}
