export type Allowtextrewrite = boolean;
export type Text = string | null;

export interface GuiStartGenerationRequest {
  allowTextRewrite?: Allowtextrewrite;
  text?: Text;
}
