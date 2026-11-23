import { BlockNoteSchema, defaultInlineContentSpecs } from "@blocknote/core";
import { en } from "@blocknote/core/locales";
import { createReactInlineContentSpec } from "@blocknote/react";
import { schema } from "./editor-schema";
import { allowRichCodeStyles, allowRichColors } from "./styles";

// V7 inline identities are for display, selection and input sides only; V7 content is never serialized back from them.
const templateField = createReactInlineContentSpec({ type: "templateField", content: "styled", propSchema: {
  bindingId: { default: "" }, occurrenceId: { default: "" }, recordId: { default: "" }, fieldKey: { default: "" },
  cellId: { default: "" }, complete: { default: true },
} }, { render: ({ inlineContent, contentRef }) => <span className="cv-template-field" data-binding-id={inlineContent.props.bindingId}
  data-record-id={inlineContent.props.recordId} data-field-key={inlineContent.props.fieldKey} ref={contentRef} /> });
const manualScope = createReactInlineContentSpec({ type: "manualScope", content: "styled", propSchema: {
  scopeId: { default: "" }, occurrenceId: { default: "" }, fragmentId: { default: "" },
} }, { render: ({ inlineContent, contentRef }) => <span className="cv-manual-scope" data-scope-id={inlineContent.props.scopeId}
  data-fragment-id={inlineContent.props.fragmentId} ref={contentRef} /> });
const boundLink = createReactInlineContentSpec({ type: "boundLink", content: "styled", propSchema: {
  href: { default: "" }, binding: { default: "label", values: ["label", "url"] }, cellId: { default: "" }, occurrenceId: { default: "" },
} }, { render: ({ inlineContent, contentRef }) => <span className="cv-bound-link" data-href={inlineContent.props.href}
  data-cell-id={inlineContent.props.cellId} ref={contentRef} /> });

/** The shared blocks and style rules with the V7 inline identities. */
export const templateSchema = BlockNoteSchema.create({ blockSpecs: schema.blockSpecs,
  inlineContentSpecs: { ...defaultInlineContentSpecs, templateField, manualScope, boundLink } });
allowRichCodeStyles(templateSchema);
allowRichColors(templateSchema);

/** BlockNote features the session has no operation for: their input rules and shortcuts would only be refused. */
export const disabledExtensions = ["history", "sideMenu", "code-block-keyboard-shortcuts", "check-list-item-shortcuts", "toggle-list-item-shortcuts",
  "bullet-list-item-shortcuts", "numbered-list-item-shortcuts", "divider-block-shortcuts"];

/** BlockNote's English texts with the placeholders of empty blocks replaced: an empty heading says «Заголовок»; other
 * blocks show nothing, and no placeholder names commands that the editor does not have. */
export const templateDictionary = { ...en, placeholders: { ...en.placeholders, default: "", emptyDocument: undefined, heading: "Заголовок",
  bulletListItem: "", numberedListItem: "", checkListItem: "", toggleListItem: "" } };
