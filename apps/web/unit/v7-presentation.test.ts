import assert from "node:assert/strict";
import test from "node:test";
import { Schema, type Node } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { DecorationSet } from "@tiptap/pm/view";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { literalRuns, sheetColumns, templatePresentationPlugin, templateSheet, type TemplateSheet } from "../src/rich/v7-presentation";

test("literal style ranges ignore field keys and reversed bounds", () => {
  assert.deepEqual(literalRuns(undefined), []);
  assert.deepEqual(literalRuns({ "binding-1": "emphasis", "literal@0@4": "emphasis", "literal@4@4": "emphasis",
    "literal@x@2": "emphasis", "literal@8@6": "caption", "literal@2@3": "" }), [{ start: 0, end: 4, style: "emphasis" }]);
  assert.deepEqual(literalRuns({ "literal@10@12": "caption", "literal@1@2": "emphasis" }),
    [{ start: 1, end: 2, style: "emphasis" }, { start: 10, end: 12, style: "caption" }]);
});

test("a layout without a sidebar is one column that stacks the regions and hides the empty sidebar button", () => {
  const header = { id: "header", x: 20, width: 556, flow: "first_page_header" } as const;
  const sidebar = { id: "sidebar", x: 20, width: 130, flow: "independent_column" } as const;
  const main = { id: "main", x: 160, width: 420, flow: "independent_column" } as const;
  assert.deepEqual(sheetColumns([header, sidebar, main]), { "--fcv-left": "20pt", "--fcv-header-left": "0pt", "--fcv-header-width": "556pt",
    "--fcv-columns": "130pt 420pt", "--fcv-gap": "10pt", "--fcv-main-column": "2", "--fcv-sidebar-column": "1", "--fcv-main-row": "2",
    "--fcv-sidebar-empty": "block" });
  assert.deepEqual(sheetColumns([{ ...header, x: 40 }, { ...main, x: 34, width: 528 }]), { "--fcv-left": "34pt", "--fcv-header-left": "6pt",
    "--fcv-header-width": "556pt", "--fcv-columns": "528pt", "--fcv-gap": "0pt", "--fcv-main-column": "1", "--fcv-sidebar-column": "1",
    "--fcv-main-row": "3", "--fcv-sidebar-empty": "none" });
  assert.equal(sheetColumns([header, sidebar]), null, "a layout needs its main column");
});

test("a sidebar right of main is the second column and the sheet starts at main", () => {
  const header = { id: "header", x: 20, width: 556, flow: "first_page_header" } as const;
  const main = { id: "main", x: 20, width: 440, flow: "independent_column" } as const;
  const sidebar = { id: "sidebar", x: 470, width: 110, flow: "independent_column" } as const;
  assert.deepEqual(sheetColumns([header, sidebar, main]), { "--fcv-left": "20pt", "--fcv-header-left": "0pt", "--fcv-header-width": "556pt",
    "--fcv-columns": "440pt 110pt", "--fcv-gap": "10pt", "--fcv-main-column": "1", "--fcv-sidebar-column": "2", "--fcv-main-row": "2",
    "--fcv-sidebar-empty": "block" });
});

test("italic faces are declared italic, so only an upright stand-in gets the browser's slant", () => {
  const faces = { regular: "regular", bold: "bold", italic: "italic", boldItalic: "bold-italic" };
  const asset = (id: string) => ({ id, sha256: id.padEnd(64, "0") });
  const regions = [{ id: "header", x: 20, width: 556 }, { id: "main", x: 20, width: 556 }];
  const response = { workspace: { project: { templatePackage: { assets: Object.values(faces).map(asset) } } }, presentation: { editor: {
    fonts: Object.values(faces), icons: [], blocks: {}, styles: { body: { faces, size: 10, lineHeight: 12, color: "#000", alignment: null } } },
    recipe: { layout: { regions }, style: { page: {}, header: {}, section_band: {}, focus: {}, bullets: {}, colors: {}, footer: { text: "" } } } } } as unknown as TemplateProjectResponseV1;
  const css = templateSheet(response)?.css ?? "";
  for (const id of ["italic", "bold-italic"]) assert.match(css, new RegExp(`fcv-${id.padEnd(24, "0")}"; font-style: italic;`));
  for (const id of ["regular", "bold"]) assert.match(css, new RegExp(`fcv-${id.padEnd(24, "0")}"; src:`));
});

test("table styles become sheet rules and an italic base font falls back to its slanted upright face", () => {
  const faces = { regular: "bold-italic", bold: "bold-italic", italic: "bold-italic", boldItalic: "bold-italic", upright: "bold" };
  const asset = (id: string) => ({ id, sha256: id.padEnd(64, "0") });
  const regions = [{ id: "header", x: 20, width: 556 }, { id: "main", x: 20, width: 556 }];
  const tables = { card: { label_width: 110, label_style: "body", label_align: "center", label_background: "box", border_width: 0.75,
    border_color: "line", padding_x: 4.5, padding_y: 4 }, box: { label_width: 0, label_style: "body", background: "box", border_width: 0, padding_x: 6, padding_y: 4 } };
  const response = { workspace: { project: { templatePackage: { assets: ["bold-italic", "bold"].map(asset) } } }, presentation: { editor: {
    fonts: ["bold-italic", "bold"], icons: [], blocks: {}, styles: { section: { faces, size: 14, lineHeight: 18, color: "#000", alignment: null } } },
    recipe: { layout: { regions }, style: { page: {}, header: {}, section_band: {}, focus: {}, bullets: {}, colors: { box: "#F3F3F3", line: "#CCCCCC" }, tables, footer: { text: "" } } } } } as unknown as TemplateProjectResponseV1;
  const sheet = templateSheet(response);
  assert.ok(sheet);
  assert.deepEqual([...sheet.tables], [["card", "t0"], ["box", "t1"]]);
  assert.match(sheet.css, /\[data-fcv-table="t0"\] \{ --fcv-row-label-width: 110pt; --fcv-row-label-display: flex; --fcv-row-border: 0\.75pt solid #CCCCCC; --fcv-row-label-fill: #F3F3F3; --fcv-row-fill: transparent; --fcv-row-pad-x: 4\.5pt; --fcv-row-pad-y: 4pt; --fcv-row-label-align: center; \}/);
  assert.match(sheet.css, /\[data-fcv-table="t1"\] \{ --fcv-row-label-width: 0pt; --fcv-row-label-display: none; --fcv-row-border: 0; --fcv-row-label-fill: transparent; --fcv-row-fill: #F3F3F3;/);
  assert.match(sheet.css, /font-family: var\(--fcv-regular\), "fcv-bold00000000000000000000", sans-serif; font-style: italic; font-size: 14pt;/);
});

test("a footer email shows with the template's footer look, and print reaches its bottom (D145)", () => {
  const regions = [{ id: "header", x: 20, width: 556 }, { id: "main", x: 20, width: 556 }];
  const sheet = (text: string) => templateSheet({ workspace: { project: { templatePackage: { assets: [{ id: "regular", sha256: "r".padEnd(64, "0") }] } } },
    presentation: { editor: { fonts: ["regular"], icons: [], blocks: {}, styles: {} }, recipe: { layout: { regions }, style: { page: {}, header: {}, section_band: {},
      focus: {}, bullets: {}, colors: { ink: "#111111" }, fonts: { body: "regular" },
      text: { footer: { font: "body", size: 12, line_height: 15, color: "ink" } },
      footer: { text, center_x: 275.65, baseline_y: 803, style: "footer", repeat: "every_page" } } } } } as unknown as TemplateProjectResponseV1);
  assert.equal(sheet("   ")?.footer, null, "an empty footer text shows nothing");
  const footer = sheet(" hr@example.com ")?.footer;
  assert.ok(footer);
  assert.equal(footer.text, "hr@example.com");
  // The text's top: the baseline less 0.8 of the size and half the leading; the line ends one line height below.
  assert.deepEqual(footer.style, { fontFamily: `"fcv-${"r".padEnd(24, "0")}", sans-serif`, fontSize: "12pt", lineHeight: "15pt", color: "#111111",
    "--fcv-footer-top": "791.9pt", "--fcv-footer-x": "275.65pt" });
  assert.ok(Math.abs(footer.bottom - 806.9) < 1e-9);
});

test("a row section is decorated with its table, label and edges, and an item inside it keeps no gap", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
    blockContainer: { content: "(region | section | paragraph) blockGroup?", attrs: { id: { default: "block" } } },
    region: { attrs: { role: { default: "main" } } }, section: { content: "inline*" }, paragraph: { content: "inline*" }, text: { group: "inline" },
  } });
  const container = (id: string, content: Node, children?: Node[]) => schema.node("blockContainer", { id }, [content, ...(children ? [schema.node("blockGroup", null, children)] : [])]);
  const paragraph = (id: string, text: string) => container(id, schema.node("paragraph", null, schema.text(text)));
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [container("main", schema.node("region", { role: "main" }), [
    container("row-1", schema.node("section"), [container("item", schema.node("section"), [paragraph("line", "Python")])]),
    container("row-2", schema.node("section"), [paragraph("line-2", "Docker")]),
    container("entry", schema.node("section"), [paragraph("company", "Example Labs")]),
  ])]));
  const ref = { viewKey: "skills", nodeIndex: null }, entry = (row?: object) => ({ style: "label", ...(row ? { row } : {}) });
  const sheet = { styles: new Map([["label", "s0"], ["body", "s1"]]), icons: new Map(), tables: new Map([["skills", "t0"]]), presentation: {
    editor: { blocks: { "row-1": entry({ table: "skills", label: "Языки", first: true, last: false }), item: { style: "label" }, line: { style: "label" },
      "row-2": entry({ table: "skills", label: "Инфра \"x\"", first: false, last: true, gap: 8 }), "line-2": { style: "label" }, entry: { style: "label" }, company: { style: "body" } },
      styles: { label: { alignment: null }, body: { alignment: "center" } } },
    blocks: Object.fromEntries(["row-1", "item", "line", "row-2", "line-2", "entry", "company"].map(id => [id, ref])),
    recipe: { views: { skills: { inset: 3, item_gap: 8 } }, style: { focus: { text_x: 0 } } } } } as unknown as TemplateSheet;
  const plugin = templatePresentationPlugin(() => sheet), state = EditorState.create({ schema, doc, plugins: [plugin] });
  const shown = plugin.props.decorations?.call(plugin, state);
  assert.ok(shown instanceof DecorationSet);
  const attributes = new Map<string, Record<string, string>>();
  for (const decoration of shown.find()) {
    const id: unknown = state.doc.nodeAt(decoration.from)?.attrs["id"];
    const spec: unknown = Reflect.get(decoration, "type");
    const attrs: unknown = typeof spec === "object" && spec !== null ? Reflect.get(spec, "attrs") : undefined;
    if (typeof id === "string" && typeof attrs === "object" && attrs !== null) attributes.set(id, Object.fromEntries(Object.entries(attrs).map(([key, value]) => [key, String(value)])));
  }
  assert.deepEqual(attributes.get("row-1"), { "data-fcv-style": "s0", "data-fcv-item": "true", "data-fcv-row": "true", "data-fcv-table": "t0",
    "data-fcv-row-first": "true", style: '--fcv-row-label: "Языки"' });
  assert.deepEqual(attributes.get("row-2"), { "data-fcv-style": "s0", "data-fcv-item": "true", "data-fcv-row": "true", "data-fcv-table": "t0",
    "data-fcv-row-last": "true", "data-fcv-gap": "true", style: '--fcv-row-label: "Инфра \\"x\\""; --fcv-item-gap: 8pt' });
  // The item inside the first row keeps no gap of its own; an entry outside a table keeps the view's gap and its lines their inset.
  assert.deepEqual(attributes.get("item"), { "data-fcv-style": "s0", "data-fcv-item": "true" });
  assert.deepEqual(attributes.get("entry"), { "data-fcv-style": "s0", "data-fcv-item": "true", "data-fcv-gap": "true", style: "--fcv-item-gap: 8pt" });
  assert.deepEqual(attributes.get("company"), { "data-fcv-style": "s1", "data-fcv-align": "center", "data-fcv-inset": "true", style: "--fcv-inset: 3pt" });
});
