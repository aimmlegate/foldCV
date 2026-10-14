import { BlockNoteSchema, createExtension, defaultBlockSpecs, defaultInlineContentSpecs, parseDefaultProps, type Block, type PartialBlock } from "@blocknote/core";
import { createReactBlockSpec, createReactInlineContentSpec, useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { useEffect, useImperativeHandle, useMemo, useState, type Ref } from "react";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import { SessionHistory, type CellChange, type CellValue } from "./history";
import { RichSaveQueue, type RichBlock } from "./save-queue";
import { saveMutation } from "./api";
import { referenceVariables } from "./template";
import { fromInline, toInline, wireColor } from "./inline";
import { bindingIdentityPlugin } from "./binding-identity";
import { authoredPasteTransaction } from "./paste-links";

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
} }, { parse: element => element.tagName === "H1" ? { ...parseDefaultProps(element), level: 1 }
  : element.tagName === "H2" ? { ...parseDefaultProps(element), level: 2 }
    : element.tagName === "H3" ? { ...parseDefaultProps(element), level: 3 } : undefined,
  render: ({ block, contentRef }) => block.props.level === 1 ? <h1 ref={contentRef} />
  : block.props.level === 2 ? <h2 ref={contentRef} /> : <h3 ref={contentRef} /> });
const pending = createReactBlockSpec({ type: "pendingRich", content: "none", propSchema: { label: { default: "" } } },
  { render: ({ block }) => <div contentEditable={false} className="cv-pending-block">{block.props.label}</div> });
const quote = createReactBlockSpec({ type: "quote", content: "inline", propSchema: {
  textAlignment: { default: "left", values: ["left", "center", "right", "justify"] }, textColor: { default: "default" }, backgroundColor: { default: "default" },
} }, { parse: element => element.tagName === "BLOCKQUOTE" ? parseDefaultProps(element) : undefined,
  render: ({ contentRef }) => <blockquote ref={contentRef} /> });
const code = { ...defaultBlockSpecs.codeBlock, config: { ...defaultBlockSpecs.codeBlock.config,
  propSchema: { ...defaultBlockSpecs.codeBlock.config.propSchema, backgroundColor: { default: "default" } } } };
const schema = BlockNoteSchema.create({ blockSpecs: { paragraph: defaultBlockSpecs.paragraph, heading: heading(),
  bulletListItem: defaultBlockSpecs.bulletListItem, numberedListItem: defaultBlockSpecs.numberedListItem,
  checkListItem: defaultBlockSpecs.checkListItem, toggleListItem: defaultBlockSpecs.toggleListItem,
  quote: quote(), codeBlock: code, divider: defaultBlockSpecs.divider,
  region: region(), section: section(), pendingRich: pending() }, inlineContentSpecs: { ...defaultInlineContentSpecs, factField } });
type EditorBlock = Block<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type InputBlock = PartialBlock<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type Stored = { block: RichBlock; children: string[] };

function toBlock(block: RichBlock): InputBlock {
  const children = block.children.map(toBlock);
  if (block.type !== "code" && block.type !== "divider" && block.type !== "table" && block.type !== "image") {
    const props = { textAlignment: block.props.alignment ?? "left", textColor: block.props.textColor ?? "default", backgroundColor: block.props.backgroundColor ?? "default" };
    if (block.type === "heading") return { id: block.id, type: "heading", props: { ...props, level: block.props.level }, content: toInline(block.content), children };
    if (block.type === "section") return { id: block.id, type: "section", props: { ...props, recordId: block.props.recordId ?? "", presentation: block.props.presentation ?? "standard" }, content: toInline(block.content), children };
    if (block.type === "bullet_list") return { id: block.id, type: "bulletListItem", props, content: toInline(block.content), children };
    if (block.type === "numbered_list") return { id: block.id, type: "numberedListItem", props: block.props.start === null || block.props.start === undefined ? props : { ...props, start: block.props.start }, content: toInline(block.content), children };
    if (block.type === "check_list") return { id: block.id, type: "checkListItem", props: { ...props, checked: block.props.checked }, content: toInline(block.content), children };
    if (block.type === "toggle_list") return { id: block.id, type: "toggleListItem", props, content: toInline(block.content), children };
    if (block.type === "quote") return { id: block.id, type: "quote", props, content: toInline(block.content), children };
    return { id: block.id, type: "paragraph", props, content: toInline(block.content), children };
  }
  if (block.type === "code") return { id: block.id, type: "codeBlock", props: { language: block.props.language, backgroundColor: block.props.backgroundColor ?? "default" }, content: block.content, children };
  if (block.type === "divider") return { id: block.id, type: "divider", children };
  return { id: block.id, type: "pendingRich", props: { label: block.type }, children };
}

export type RichEditorHandle = { flush: () => Promise<RichProjectResponse>; undo: () => void; redo: () => void };
export function RichEditor({ initial, acknowledge, onStatus, ref }: { initial: RichProjectResponse;
  acknowledge: (response: RichProjectResponse) => void; onStatus: (status: string) => void; ref: Ref<RichEditorHandle> }) {
  const project = initial.workspace.project;
  if (!project) throw new Error("Document is missing");
  const [, refresh] = useState(0);
  const [selecting, setSelecting] = useState(false);
  const bridge = useMemo(() => ({ session: crypto.randomUUID(), group: 0, composing: false, observing: false, replaying: false,
    kind: "typing" as RichMutation["kind"],
    lastTypingAt: 0, history: null as SessionHistory | null, queue: null as RichSaveQueue | null,
    fragments: new Map<string, string>(), projectionError: null as string | null,
    current: new Map<string, CellValue>(), values: new Map<string, Stored>(), original: new Map<string, RichBlock>(),
    undo: () => {}, redo: () => {}, complete: () => {}, timer: null as ReturnType<typeof setTimeout> | null }), []);
  const extension = useMemo(() => createExtension({ key: "foldcv-rich-session", runsBefore: ["link"], prosemirrorPlugins: [bindingIdentityPlugin(), new Plugin({
    key: new PluginKey("foldcv-rich-session"), filterTransaction: transaction => {
      if (!transaction.docChanged) return true;
      const root = transaction.doc.firstChild;
      if (!root || root.childCount !== 3) return false;
      return ["header", "sidebar", "main"].every((id, index) => {
        const item = root.child(index); const value: unknown = item.attrs["id"];
        return value === id && item.firstChild?.type.name === "region";
      });
    }, props: { handlePaste: (view, _event, slice) => {
      const tr = authoredPasteTransaction(view.state, slice);
      if (!tr) return false;
      bridge.group++; view.dispatch(tr); return true;
    }, handleKeyDown: (_view, event) => {
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
  const editor = useCreateBlockNote({ schema, disableExtensions: ["history"], extensions: [extension], links: {
    onClick: event => {
      event.preventDefault();
      const anchor = event.target instanceof Element ? event.target.closest("a") : null;
      if ((event.metaKey || event.ctrlKey) && anchor instanceof HTMLAnchorElement) window.open(anchor.href, "_blank", "noopener,noreferrer");
      return false;
    },
  }, initialContent:
    project.document.regions.map(region => ({ id: region.id, type: "region", props: { role: region.role }, children: region.blocks.map(toBlock) })) }, []);

  useEffect(() => editor.onSelectionChange(() => {
    setSelecting(editor.transact(tr => !tr.selection.empty));
  }), [editor]);

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
      const identity = { id: block.id, revision: old?.revision ?? 1, provenance: old?.provenance ?? [], children: block.children.map(serialize) };
      if (block.type === "divider") return { ...identity, type: "divider", props: {}, content: null };
      if (block.type === "codeBlock") return { ...identity, type: "code", props: { language: block.props.language,
        backgroundColor: wireColor(block.props.backgroundColor, "background") }, content: block.content.map(span => span.text).join("") };
      const common = { ...identity, content: fromInline(block.content, (binding, part) => {
        const key = `${binding}:${part}`;
        let id = bridge.fragments.get(key);
        if (!id) { id = crypto.randomUUID(); bridge.fragments.set(key, id); }
        return id;
      }) };
      const props = { alignment: block.props.textAlignment, textColor: wireColor(block.props.textColor, "text"), backgroundColor: wireColor(block.props.backgroundColor, "background") };
      if (block.type === "heading") return { ...common, type: "heading", props: { ...props, level: block.props.level } };
      if (block.type === "section") return { ...common, type: "section", props: { ...props, recordId: block.props.recordId || null, presentation: block.props.presentation } };
      if (block.type === "bulletListItem") return { ...common, type: "bullet_list", props };
      if (block.type === "numberedListItem") return { ...common, type: "numbered_list", props: { ...props, start: block.props.start ?? null } };
      if (block.type === "checkListItem") return { ...common, type: "check_list", props: { ...props, checked: block.props.checked } };
      if (block.type === "toggleListItem") return { ...common, type: "toggle_list", props };
      if (block.type === "quote") return { ...common, type: "quote", props };
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
      queue.update(document(), history.currentActionId ?? `${bridge.session}:typing`, bridge.kind); schedule(); refresh(value => value + 1);
    });
    bridge.history = history;
    bridge.undo = () => { if (bridge.composing || bridge.projectionError) return; bridge.kind = "undo"; try { history.undo(); } finally { bridge.kind = "typing"; } };
    bridge.redo = () => { if (bridge.composing || bridge.projectionError) return; bridge.kind = "redo"; try { history.redo(); } finally { bridge.kind = "typing"; } };
    function observe() {
      if (bridge.replaying) return;
      let next: Map<string, CellValue>;
      try { next = cells(document()); bridge.projectionError = null; }
      catch (error) { bridge.projectionError = error instanceof Error ? error.message : "RICH_CONTENT_UNSUPPORTED"; onStatus(bridge.projectionError); return; }
      const changes: CellChange[] = [];
      for (const key of new Set([...next.keys(), ...bridge.current.keys()])) {
        const before = history.read(key), after = next.get(key) ?? null;
        if (before !== after) changes.push({ key, before, after });
      }
      const now = performance.now();
      if (!bridge.composing && now - bridge.lastTypingAt > 500) bridge.group++;
      bridge.lastTypingAt = now; bridge.observing = true;
      try {
        const structure = changes.some(change => {
          if (change.key.startsWith("region:") || !change.before || !change.after) return true;
          const before = bridge.values.get(change.before), after = bridge.values.get(change.after);
          if (!before || !after) return true;
          const text = (block: RichBlock): string => typeof block.content === "string" ? block.content
            : Array.isArray(block.content) ? block.content.map(span => span.type === "link" ? span.content.map(part => part.text).join("") : span.text).join("") : "";
          return before.block.type !== after.block.type || JSON.stringify(before.block.props) !== JSON.stringify(after.block.props)
            || JSON.stringify(before.children) !== JSON.stringify(after.children) || text(before.block) === text(after.block);
        });
        const kind = bridge.composing ? "composition" : structure ? "structure" : "typing";
        bridge.kind = kind;
        const id = history.commit(kind, changes, kind === "typing" || kind === "composition" ? `typing:${bridge.group}` : null);
        if (id) queue.update(document(), id, kind);
      } finally { bridge.observing = false; bridge.kind = "typing"; }
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
    if (bridge.projectionError) throw new Error(bridge.projectionError);
    await bridge.queue.flush(); return bridge.queue.baseline;
  }, undo: bridge.undo, redo: bridge.redo }), [bridge, bridge.history?.position]);
  return <div className="cv-document" style={{ ...referenceVariables, color: "#171717" }} data-project-id={initial.workspace.projectId}>
    <BlockNoteView editor={editor} theme="light" linkToolbar={!selecting} />
  </div>;
}
