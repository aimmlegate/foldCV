import type { StyleSpecs } from "@blocknote/core";

export function allowRichCodeStyles(schema: { styleSpecs: StyleSpecs }): void {
  const code = schema.styleSpecs["code"];
  if (!code) throw new Error("Code style is missing");
  // RichDocument permits code together with emphasis and colors.
  schema.styleSpecs = { ...schema.styleSpecs, code: { ...code, implementation: { ...code.implementation,
    mark: code.implementation.mark.extend({ excludes: "" }),
  } } };
}
