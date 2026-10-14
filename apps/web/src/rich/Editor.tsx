import { BlockNoteSchema, createExtension, defaultBlockSpecs, defaultInlineContentSpecs, type Block, type PartialBlock } from "@blocknote/core";
import { createReactBlockSpec, createReactInlineContentSpec, useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { useEffect, useImperativeHandle, useMemo, useState, type Ref } from "react";
import type { RichDocumentV1, Content, InlineStyles } from "../contracts/generated/rich_document_v1";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import { SessionHistory, type CellChange, type CellValue } from "./history";
import { RichSaveQueue, type RichBlock } from "./save-queue";
import { saveMutation } from "./api";
import { referenceVariables } from "./template";

const region = createReactBlockSpec({ type: "region", content: "none", propSchema: {
  role: { default: "main", values: ["header", "sidebar", "main"] },
} }, { render: () => <div className="cv-region-marker" contentEditable={false} /> });
const section = createReactBlockSpec({ type: "section", content: "inline", propSchema: {
  recordId: { default: "" }, presentation: { default: "standard", values: ["standard", "focus"] },
  textAlignment: { default: "left", values: ["left", "center", "right", "justify"] }, textColor: { default: "default" }, backgroundColor: { default: "default" },
} }, { render: ({ contentRef }) => <h2 className="cv-section-title" ref={contentRef} /> });
const factField = createReactInlineContentSpec({ type: "factField", content: "styled", propSchema: {
  bindingId: { default: "" }, recordId: { default: "" }, fieldKey: { default: "" }, syncedFactRevision: { default: 1 },
} }, { render: ({ inlineContent, contentRef }) => <span data-binding-id={inlineContent.props.bindingId}
  data-record-id={inlineContent.props.recordId} data-field-key={inlineContent.props.fieldKey} ref={contentRef} /> });
const heading = createReactBlockSpec({ type: "heading", content: "inline", propSchema: {
  level: { default: 1, values: [1, 2, 3] }, textAlignment: { default: "left", values: ["left", "center", "right", "justify"] },
  textColor: { default: "default" }, backgroundColor: { default: "default" },
} }, { render: ({ block, contentRef }) => block.props.level === 1 ? <h1 ref={contentRef} />
  : block.props.level === 2 ? <h2 ref={contentRef} /> : <h3 ref={contentRef} /> });
const pending = createReactBlockSpec({ type: "pendingRich", content: "none", propSchema: { label: { default: "" } } },
  { render: ({ block }) => <div contentEditable={false} className="cv-pending-block">{block.props.label}</div> });
const schema = BlockNoteSchema.create({ blockSpecs: { paragraph: defaultBlockSpecs.paragraph, heading: heading(),
  region: region(), section: section(), pendingRich: pending() }, inlineContentSpecs: { ...defaultInlineContentSpecs, factField } });
type EditorBlock = Block<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type InputBlock = PartialBlock<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type EditorInline = Extract<EditorBlock, { type: "paragraph" }>["content"][number];
type Stored = { block: RichBlock; children: string[] };

function styles(value: InlineStyles) { return { bold: value.bold ?? false, italic: value.italic ?? false,
  underline: value.underline ?? false, strike: value.strike ?? false, code: value.code ?? false,
  textColor: value.textColor ?? "default", backgroundColor: value.backgroundColor ?? "default" }; }
function toInline(content: Content): EditorInline[] {
  return content.map(span => span.type === "link" ? { type: "link", href: span.href,
    content: span.content.map(child => ({ type: "text", text: child.text, styles: styles(child.styles) })) }
    : span.type === "fact_field" ? { type: "factField", props: { bindingId: span.bindingId, recordId: span.recordId,
      fieldKey: span.fieldKey, syncedFactRevision: span.syncedFactRevision }, content: [{ type: "text", text: span.text, styles: styles(span.styles) }] }
      : { type: "text", text: span.text, styles: styles(span.styles) });
}
function fromStyles(value: Extract<EditorInline, { type: "text" }>["styles"]): InlineStyles {
  return { bold: value.bold ?? false, italic: value.italic ?? false, underline: value.underline ?? false,
    strike: value.strike ?? false, code: value.code ?? false, textColor: value.textColor ?? "default", backgroundColor: value.backgroundColor ?? "default" };
}
function fromInline(content: EditorInline[]): Content {
  return content.map(span => span.type === "link" ? { type: "link", href: span.href,
    content: span.content.map(child => ({ type: "text", text: child.text, styles: fromStyles(child.styles) })) }
    : span.type === "factField" ? { type: "fact_field", bindingId: span.props.bindingId, recordId: span.props.recordId,
      fieldKey: span.props.fieldKey, syncedFactRevision: span.props.syncedFactRevision,
      text: span.content.map(child => child.text).join(""), styles: fromStyles(span.content[0]?.styles ?? {}) }
      : { type: "text", text: span.text, styles: fromStyles(span.styles) });
}
function toBlock(block: RichBlock): InputBlock {
  const children = block.children.map(toBlock);
  if (block.type === "paragraph" || block.type === "heading" || block.type === "section") {
    const props = { textAlignment: block.props.alignment ?? "left", textColor: block.props.textColor ?? "default", backgroundColor: block.props.backgroundColor ?? "default" };
    if (block.type === "heading") return { id: block.id, type: "heading", props: { ...props, level: block.props.level }, content: toInline(block.content), children };
    if (block.type === "section") return { id: block.id, type: "section", props: { ...props, recordId: block.props.recordId ?? "", presentation: block.props.presentation ?? "standard" }, content: toInline(block.content), children };
    return { id: block.id, type: "paragraph", props, content: toInline(block.content), children };
  }
  return { id: block.id, type: "pendingRich", props: { label: block.type }, children };
}

export type RichEditorHandle = { flush: () => Promise<RichProjectResponse>; undo: () => void; redo: () => void };
export function RichEditor({ initial, acknowledge, onStatus, ref }: { initial: RichProjectResponse;
  acknowledge: (response: RichProjectResponse) => void; onStatus: (status: string) => void; ref: Ref<RichEditorHandle> }) {
  const project = initial.workspace.project;
  if (!project) throw new Error("Document is missing");
  const [, refresh] = useState(0);
  const bridge = useMemo(() => ({ session: crypto.randomUUID(), group: 0, composing: false, observing: false, replaying: false,
    lastTypingAt: 0, history: null as SessionHistory | null, queue: null as RichSaveQueue | null,
    current: new Map<string, CellValue>(), values: new Map<string, Stored>(), original: new Map<string, RichBlock>(),
    undo: () => {}, redo: () => {}, complete: () => {}, timer: null as ReturnType<typeof setTimeout> | null }), []);
  const extension = useMemo(() => createExtension({ key: "foldcv-rich-session", prosemirrorPlugins: [new Plugin({
    key: new PluginKey("foldcv-rich-session"), filterTransaction: transaction => {
      if (!transaction.docChanged) return true;
      const root = transaction.doc.firstChild;
      if (!root || root.childCount !== 3) return false;
      return ["header", "sidebar", "main"].every((id, index) => {
        const item = root.child(index); const value: unknown = item.attrs["id"];
        return value === id && item.firstChild?.type.name === "region";
      });
    }, props: { handleKeyDown: (_view, event) => {
      if (!(event.metaKey || event.ctrlKey) || !["z", "y"].includes(event.key.toLowerCase())) return false;
      event.preventDefault(); if (!bridge.composing) { bridge.group++; if (event.shiftKey || event.key.toLowerCase() === "y") bridge.redo(); else bridge.undo(); } return true;
    }, handleDOMEvents: {
      compositionstart: () => { bridge.group++; bridge.composing = true; return false; },
      compositionend: () => { queueMicrotask(() => { bridge.composing = false; bridge.complete(); bridge.group++; }); return false; },
      blur: () => { if (!bridge.composing) bridge.group++; return false; },
      beforeinput: (_view, event) => {
        if (!(event instanceof InputEvent) || !["historyUndo", "historyRedo"].includes(event.inputType)) return false;
        event.preventDefault(); if (!bridge.composing) { if (event.inputType === "historyUndo") bridge.undo(); else bridge.redo(); } return true;
      },
    } },
  })] }), [bridge]);
  const editor = useCreateBlockNote({ schema, disableExtensions: ["history"], extensions: [extension], initialContent:
    project.document.regions.map(region => ({ id: region.id, type: "region", props: { role: region.role }, children: region.blocks.map(toBlock) })) }, []);

  useEffect(() => {
    const originalDocument = project.document;
    for (const region of originalDocument.regions) {
      const remember = (block: RichBlock) => { bridge.original.set(block.id, block); block.children.forEach(remember); };
      region.blocks.forEach(remember);
    }
    function serialize(block: EditorBlock): RichBlock {
      const old = bridge.original.get(block.id);
      if (block.type === "region") throw new Error("Region is not a content block");
      if (block.type === "pendingRich") {
        if (!old) throw new Error("Unknown pending block");
        return { ...old, children: block.children.map(serialize) };
      }
      const common = { id: block.id, revision: old?.revision ?? 1, provenance: old?.provenance ?? [], children: block.children.map(serialize), content: fromInline(block.content) };
      const props = { alignment: block.props.textAlignment, textColor: block.props.textColor, backgroundColor: block.props.backgroundColor };
      if (block.type === "heading") return { ...common, type: "heading", props: { ...props, level: block.props.level } };
      if (block.type === "section") return { ...common, type: "section", props: { ...props, recordId: block.props.recordId || null, presentation: block.props.presentation } };
      return { ...common, type: "paragraph", props };
    }
    function document(): RichDocumentV1 {
      const regions = originalDocument.regions.map(region => {
        const block = editor.getBlock(region.id);
        if (!block || block.type !== "region") throw new Error("Region is missing");
        return { ...region, blocks: block.children.map(serialize) };
      });
      const header = regions[0], sidebar = regions[1], main = regions[2];
      if (!header || !sidebar || !main) throw new Error("Region is missing");
      return { schemaVersion: 1, revision: originalDocument.revision, regions: [header, sidebar, main] };
    }
    function cells(document: RichDocumentV1) {
      const values = new Map<string, CellValue>();
      const visit = (block: RichBlock) => {
        const stored: Stored = { block: { ...block, children: [], revision: 1 }, children: block.children.map(child => child.id) };
        const json = JSON.stringify(stored); bridge.values.set(json, stored); values.set(`block:${block.id}`, json); block.children.forEach(visit);
      };
      document.regions.forEach(region => { values.set(`region:${region.id}`, JSON.stringify(region.blocks.map(block => block.id))); region.blocks.forEach(visit); });
      return values;
    }
    bridge.current = cells(document());
    const queue = new RichSaveQueue(initial, bridge.session, saveMutation, acknowledge);
    bridge.queue = queue;
    function schedule() {
      onStatus("Изменения сохраняются…");
      if (bridge.timer) clearTimeout(bridge.timer);
      if (bridge.composing) return;
      bridge.timer = setTimeout(() => { void queue.flush().then(() => onStatus("Сохранено")).catch(error => onStatus(error instanceof Error ? error.message : "Не удалось сохранить")); }, 400);
    }
    function rebuild(id: string): RichBlock {
      const value = bridge.current.get(`block:${id}`), stored = value ? bridge.values.get(value) : undefined;
      if (!stored) throw new Error("History block is missing");
      return { ...stored.block, children: stored.children.map(rebuild) };
    }
    const history = new SessionHistory(bridge.session, bridge.current, changes => {
      for (const change of changes) bridge.current.set(change.key, change.after);
      if (!bridge.observing) {
        bridge.replaying = true;
        try {
          editor.transact(() => originalDocument.regions.forEach(region => {
            const value = bridge.current.get(`region:${region.id}`);
            const ids: unknown = value ? JSON.parse(value) : [];
            if (!Array.isArray(ids) || !ids.every((id: unknown) => typeof id === "string")) throw new Error("History region is invalid");
            const children = ids.map((id: string) => toBlock(rebuild(id)));
            editor.updateBlock(region.id, { children });
          }));
        } finally { bridge.replaying = false; }
      }
      queue.update(document(), history.currentActionId ?? `${bridge.session}:typing`); schedule(); refresh(value => value + 1);
    });
    bridge.history = history;
    bridge.undo = () => { history.undo(); };
    bridge.redo = () => { history.redo(); };
    function observe() {
      if (bridge.replaying) return;
      const next = cells(document());
      const changes: CellChange[] = [];
      for (const key of new Set([...next.keys(), ...bridge.current.keys()])) {
        const before = history.read(key), after = next.get(key) ?? null;
        if (before !== after) changes.push({ key, before, after });
      }
      const now = performance.now();
      if (!bridge.composing && now - bridge.lastTypingAt > 500) bridge.group++;
      bridge.lastTypingAt = now; bridge.observing = true;
      try {
        const id = history.commit(bridge.composing ? "composition" : "typing", changes, `typing:${bridge.group}`);
        if (id) queue.update(document(), id);
      } finally { bridge.observing = false; }
    }
    const stop = editor.onChange(observe);
    bridge.complete = () => { observe(); schedule(); };
    // Only initial normalization is queued; acknowledgments never replace the editor.
    queue.update(document(), `${bridge.session}:initial`);
    return () => { stop(); history.close(); queue.close(); if (bridge.timer) clearTimeout(bridge.timer); };
  }, [editor, bridge]);
  useImperativeHandle(ref, () => ({ flush: async () => {
    if (bridge.composing) throw new Error("Завершите ввод текста");
    if (!bridge.queue) throw new Error("Редактор ещё открывается");
    await bridge.queue.flush(); return bridge.queue.baseline;
  }, undo: bridge.undo, redo: bridge.redo }), [bridge, bridge.history?.position]);
  return <div className="cv-document" style={{ ...referenceVariables, color: "#171717" }} data-project-id={initial.workspace.projectId}>
    <BlockNoteView editor={editor} theme={document.documentElement.dataset.theme === "dark" ? "dark" : "light"} />
  </div>;
}
