export type Replacements = [SpanReplacement, ...SpanReplacement[]];
export type Fieldid = string;
export type Text = string;

export interface GuiRewriteProposal {
  replacements: Replacements;
}
export interface SpanReplacement {
  fieldId: Fieldid;
  text: Text;
}
