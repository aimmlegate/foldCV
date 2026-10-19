import { useMemo } from "react";
import { BlockNoteSchema, defaultBlockSpecs, defaultProps, parseDefaultProps, type Block, type PartialBlock } from "@blocknote/core";
import { createReactBlockSpec, useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";

const heading = createReactBlockSpec({ type: "heading", content: "inline", propSchema: {
  ...defaultProps, level: { default: 1, values: [1, 2, 3, 4, 5, 6] },
} }, {
  parse: element => {
    const level = Number(element.tagName[1]);
    return /^H[1-6]$/.test(element.tagName) && (level === 1 || level === 2 || level === 3 || level === 4 || level === 5 || level === 6)
      ? { ...parseDefaultProps(element), level } : undefined;
  },
  render: ({ block, contentRef }) => {
    const Tag = `h${block.props.level}` as const;
    return <Tag ref={contentRef} />;
  },
});
const schema = BlockNoteSchema.create({ blockSpecs: { ...defaultBlockSpecs, heading: heading() } });
type PreviewBlock = Block<typeof schema.blockSchema>;
type InputBlock = PartialBlock<typeof schema.blockSchema>;

function localContent(blocks: PreviewBlock[]): InputBlock[] {
  return blocks.map(block => {
    if (block.type === "image" || block.type === "video" || block.type === "audio" || block.type === "file") {
      // Original Markdown must not fetch remote media just by being opened.
      return { type: "paragraph", content: [block.props.caption || block.props.name, block.props.url].filter(Boolean).join("\n") };
    }
    return { ...block, children: localContent(block.children) };
  });
}

export function TextOriginal({ text, markdown }: { text: string; markdown: boolean }) {
  const parser = useCreateBlockNote({ schema });
  const content = useMemo<InputBlock[]>(() => {
    if (!markdown) return [{ type: "paragraph", content: text }];
    try {
      const blocks = localContent(parser.tryParseMarkdownToBlocks(text));
      return blocks.length ? blocks : [{ type: "paragraph", content: text }];
    } catch { return [{ type: "paragraph", content: text }]; }
  }, [parser, text, markdown]);
  const editor = useCreateBlockNote({ schema, initialContent: content }, [content]);
  return <div className="source-text-preview" aria-label={markdown ? "Оригинал Markdown" : "Оригинал текста"}>
    <BlockNoteView editor={editor} editable={false} theme="light" formattingToolbar={false} linkToolbar={false}
      sideMenu={false} slashMenu={false} filePanel={false} tableHandles={false} emojiPicker={false} comments={false} />
  </div>;
}
