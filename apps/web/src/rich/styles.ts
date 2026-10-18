import { createStyleSpec, type StyleSpecs } from "@blocknote/core";
import { wireColor } from "./inline";

export function allowRichColors(schema: { styleSpecs: StyleSpecs }): void {
  for (const [type, kind, property] of [["textColor", "text", "color"], ["backgroundColor", "background", "backgroundColor"]] as const) {
    const spec = createStyleSpec({ type, propSchema: "string" }, {
      render: value => {
        const dom = document.createElement("span"), color = wireColor(value, kind);
        dom.style[property] = color === "default" ? "" : color;
        return { dom, contentDOM: dom };
      },
      parse: element => {
        if (!element.style[property]) return undefined;
        try { return wireColor(element.style[property], kind); } catch { return undefined; }
      },
    });
    schema.styleSpecs = { ...schema.styleSpecs, [type]: { ...spec, implementation: { ...spec.implementation,
      mark: spec.implementation.mark.extend({ renderHTML: ({ mark }) => {
        const value: unknown = mark.attrs["stringValue"];
        if (typeof value !== "string") throw new Error("RICH_COLOR_UNSUPPORTED");
        const color = wireColor(value, kind);
        return ["span", { "data-style-type": type, "data-value": value,
          style: color === "default" ? "" : `${kind === "text" ? "color" : "background-color"}: ${color}` }, 0];
      } }),
    } } };
  }
}

export function allowRichCodeStyles(schema: { styleSpecs: StyleSpecs }): void {
  const code = schema.styleSpecs["code"];
  if (!code) throw new Error("Code style is missing");
  // RichDocument permits code together with emphasis and colors.
  schema.styleSpecs = { ...schema.styleSpecs, code: { ...code, implementation: { ...code.implementation,
    mark: code.implementation.mark.extend({ excludes: "" }),
  } } };
}
