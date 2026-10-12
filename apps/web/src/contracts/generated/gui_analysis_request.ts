export type Action = "invalidate" | "retry";
/**
 * @maxItems 500
 */
export type Fieldids = string[];

export interface GuiAnalysisRequest {
  action: Action;
  fieldIds?: Fieldids;
}
