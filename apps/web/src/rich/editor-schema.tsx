import { BlockNoteSchema, defaultBlockSpecs, defaultInlineContentSpecs, parseDefaultProps } from "@blocknote/core";
import { createReactBlockSpec, createReactInlineContentSpec } from "@blocknote/react";
import { image } from "./Image";
import { allowRichCodeStyles, allowRichColors } from "./styles";

const region = createReactBlockSpec({ type: "region", content: "none", propSchema: {
  role: { default: "main", values: ["header", "sidebar", "main"] },
} }, { render: () => <div className="cv-region-marker" contentEditable={false} /> });
const section = createReactBlockSpec({ type: "section", content: "inline", propSchema: {
  recordId: { default: "" }, presentation: { default: "standard", values: ["standard", "focus"] }, manualOrder: { default: false },
  textAlignment: { default: "left", values: ["left", "center", "right", "justify"] }, textColor: { default: "default" }, backgroundColor: { default: "default" },
} }, { render: ({ contentRef }) => <h2 className="cv-section-title" ref={contentRef} /> });
const factField = createReactInlineContentSpec({ type: "factField", content: "styled", propSchema: {
  bindingId: { default: "" }, recordId: { default: "" }, fieldKey: { default: "" }, syncedFactRevision: { default: 1 },
  bindingRootId: { default: "" },
} }, { render: ({ inlineContent, contentRef }) => <span data-binding-id={inlineContent.props.bindingId}
  data-record-id={inlineContent.props.recordId} data-field-key={inlineContent.props.fieldKey} ref={contentRef} /> });
const heading = createReactBlockSpec({ type: "heading", content: "inline", propSchema: {
  level: { default: 1, values: [1, 2, 3] }, textAlignment: { default: "left", values: ["left", "center", "right", "justify"] },
  textColor: { default: "default" }, backgroundColor: { default: "default" },
} }, { parse: element => element.tagName === "H1" ? { ...parseDefaultProps(element), level: 1 }
  : element.tagName === "H2" ? { ...parseDefaultProps(element), level: 2 }
    : element.tagName === "H3" ? { ...parseDefaultProps(element), level: 3 } : undefined,
  render: ({ block, contentRef }) => block.props.level === 1 ? <h1 ref={contentRef} />
  : block.props.level === 2 ? <h2 ref={contentRef} /> : <h3 ref={contentRef} /> });
const quote = createReactBlockSpec({ type: "quote", content: "inline", propSchema: {
  textAlignment: { default: "left", values: ["left", "center", "right", "justify"] }, textColor: { default: "default" }, backgroundColor: { default: "default" },
} }, { parse: element => element.tagName === "BLOCKQUOTE" ? parseDefaultProps(element) : undefined,
  render: ({ contentRef }) => <blockquote ref={contentRef} /> });
const code = { ...defaultBlockSpecs.codeBlock, config: { ...defaultBlockSpecs.codeBlock.config,
  propSchema: { ...defaultBlockSpecs.codeBlock.config.propSchema, backgroundColor: { default: "default" } } } };
export const schema = BlockNoteSchema.create({ blockSpecs: { paragraph: defaultBlockSpecs.paragraph, heading: heading(),
  bulletListItem: defaultBlockSpecs.bulletListItem, numberedListItem: defaultBlockSpecs.numberedListItem,
  checkListItem: defaultBlockSpecs.checkListItem, toggleListItem: defaultBlockSpecs.toggleListItem,
  quote: quote(), codeBlock: code, divider: defaultBlockSpecs.divider,
  table: defaultBlockSpecs.table, image: image(), region: region(), section: section() },
  inlineContentSpecs: { ...defaultInlineContentSpecs, factField } });
allowRichCodeStyles(schema);
allowRichColors(schema);
