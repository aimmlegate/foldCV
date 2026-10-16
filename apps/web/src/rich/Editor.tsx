import { BlockNoteSchema, createExtension, defaultBlockSpecs, defaultInlineContentSpecs, parseDefaultProps, type Block, type PartialBlock } from "@blocknote/core";
import { createReactBlockSpec, createReactInlineContentSpec, useCreateBlockNote, SuggestionMenuController, getDefaultReactSlashMenuItems, FormattingToolbarController, SideMenuController } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { AllSelection, TextSelection, Plugin, PluginKey } from "@tiptap/pm/state";
import type { SelectionBookmark } from "@tiptap/pm/state";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { Extension } from "@tiptap/core";
import { createContext, useCallback, useContext, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode, type Ref } from "react";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { ImageSessionRequest } from "../contracts/generated/image_session_request";
import { documentCells, type StoredBlock } from "./document-cells";
import { factCells, factsFromCells } from "./fact-cells";
import { RichSynchronization, selectionChecksum, type PanelCommand } from "./synchronization";
import { PreparedEditorBridge, type PreparedApi } from "../assistant/editor-bridge";
import { anchorCurrent } from "../assistant/presentation";
import type { AgentFinding } from "../contracts/generated/agent_finding";
import { Timeline, type TimelineControls } from "./Timeline";
import { dateAnchors, type DateAnchor } from "./date-edit";
import { presentationPlugin, type PresentationBlocks } from "./presentation";
import { presentationLogos } from "./presentation-assets";
import type { TimelineReport } from "../contracts/generated/timeline_report";
import type { DateCascadeProposal } from "../contracts/generated/date_cascade_proposal";
import { selectedRange } from "./selection";
import type { RichSelection } from "../contracts/generated/rich_selection";
import type { RichCompletionRequest } from "../contracts/generated/rich_completion_request";
import { SessionHistory, type CellChange, type CellValue } from "./history";
import { RichSaveQueue, type RichBlock } from "./save-queue";
import { saveMutation, projectRequest, imageSource, uploadImage, validateImageSession, readTimeline } from "./api";
import { fromInline, toInline, wireColor } from "./inline";
import { bindingIdentityPlugin } from "./binding-identity";
import { authoredPasteTransaction } from "./paste-links";
import { tableIdentityAttributes, tableIdentityPlugin, readTableIdentities, restoreTableIdentities, type TableRowIdentity } from "./table-identity";
import { toTable, fromTable } from "./table";
import { image, ImageActions } from "./Image";
import { structureIdentityAttributes, structureIdentityPlugin, readBlockSources } from "./structure-identity";
import { copyBlock, moveBlock, mergeBlocks } from "./structure";
import { deleteAcrossRegions, pastedRegionsPlugin, flattenPastedRegions } from "./regions";
import { BlockSideMenu, SelectionToolbar } from "./ContextMenus";
import { commandBlock } from "./block-target";
import { prototypePresentation } from "../workbench/editor/presentation";
import { Toolbar, type ToolbarCommand } from "../workbench/editor/Toolbar";
import { RewritePanel } from "../workbench/editor/RewritePanel";
import { LinkDialog } from "../workbench/editor/LinkDialog";
import { Icon } from "../workbench/ui/Icon";
import { restoreEmptyRegions } from "../workbench/editor/regions";
import { BlockPanel } from "../workbench/editor/BlockPanel";
import { SourceDialog } from "../workbench/editor/SourceDialog";
import { TableDialog } from "../workbench/editor/TableDialog";
import { capturedSelectionCurrent } from "../workbench/editor/capture";
import { AppliedIntentFailure, IntentQueue, type IntentState } from "./intent-queue";
import { FactsPanel } from "../workbench/facts/FactsPanel";
import { BackgroundWriter, type WriterMode } from "../background/writer";
import type { AttachedWriter } from "../background/connection";
import { projectJobs } from "../background/jobs";
import { allowRichCodeStyles } from "./styles";

type FactIntent = { kind: "panel"; command: PanelCommand } | { kind: "cascade"; proposal: DateCascadeProposal };

const EditorActions = createContext<{ addText: (id: string) => void }>({ addText: () => {} });
const region = createReactBlockSpec({ type: "region", content: "none", propSchema: {
  role: { default: "main", values: ["header", "sidebar", "main"] },
} }, { render: function RegionMarker({ block }) {
  const { addText } = useContext(EditorActions);
  const label = block.props.role === "header" ? "шапку" : block.props.role === "sidebar" ? "левую колонку" : "основной текст";
  return <div className="cv-region-marker" contentEditable={false}>{!block.children.length &&
    <button type="button" className="uir-empty-region" aria-label={`Добавить текст в ${label}`} onClick={() => addText(block.id)}>Добавить текст</button>}</div>;
} });
const section = createReactBlockSpec({ type: "section", content: "inline", propSchema: {
  recordId: { default: "" }, presentation: { default: "standard", values: ["standard", "focus"] },
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
const schema = BlockNoteSchema.create({ blockSpecs: { paragraph: defaultBlockSpecs.paragraph, heading: heading(),
  bulletListItem: defaultBlockSpecs.bulletListItem, numberedListItem: defaultBlockSpecs.numberedListItem,
  checkListItem: defaultBlockSpecs.checkListItem, toggleListItem: defaultBlockSpecs.toggleListItem,
  quote: quote(), codeBlock: code, divider: defaultBlockSpecs.divider,
  table: defaultBlockSpecs.table, image: image(), region: region(), section: section() },
  inlineContentSpecs: { ...defaultInlineContentSpecs, factField } });
allowRichCodeStyles(schema);
type EditorBlock = Block<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type InputBlock = PartialBlock<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type Stored = StoredBlock;

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
  if (block.type === "table") return { id: block.id, type: "table", props: { textColor: block.props.textColor ?? "default" }, content: toTable(block.content), children };
  return { id: block.id, type: "image", props: { assetId: block.props.assetId, alt: block.props.alt, width: block.props.width,
    height: block.props.height, textAlignment: block.props.alignment }, content: toInline(block.props.caption), children };
}

export type CapturedEditorSelection = { selection: Omit<RichSelection, "capture" | "textSha256">; session: string; epochs: ReadonlyMap<string, number> };
export type RichEditorHandle = { flush: () => Promise<RichProjectResponse>; undo: () => void; redo: () => void;
  background: boolean; navigate: () => Promise<void>; resume: () => Promise<void>;
  sessionId: string; captureSelection: () => CapturedEditorSelection | null;
  assistantBaseline: (captured: CapturedEditorSelection | null) => Promise<{ response: RichProjectResponse; selection: RichSelection | null }>;
  focusFinding: (anchor: AgentFinding["anchors"][number]) => boolean;
  applyAssistant: (batchId: string, api: PreparedApi) => Promise<void> };
export function RichEditor({ initial, acknowledge, onStatus, ref, onHistoryNavigation, onAssistantFence, portalHost, contextActions, assistant, writer: writerConnection = null }: { initial: RichProjectResponse;
  acknowledge: (response: RichProjectResponse) => void; onStatus: (status: string) => void; ref: Ref<RichEditorHandle>;
  onHistoryNavigation?: () => void; onAssistantFence?: (saved: boolean) => void; portalHost?: HTMLElement; contextActions?: ReactNode; assistant?: ReactNode; writer?: AttachedWriter | null }) {
  const canonicalProject = initial.workspace.project;
  const project = canonicalProject && writerConnection?.local ? { ...canonicalProject,
    document: writerConnection.local.payload.document, facts: writerConnection.local.payload.facts } : canonicalProject;
  if (!project) throw new Error("Document is missing");
  const initialFacts = project.facts;
  const [facts, setFacts] = useState(initialFacts);
  const [factIntents, setFactIntents] = useState<IntentState<FactIntent>>({ pending: [], paused: false });
  const prototypeFacts = useRef(initialFacts);
  prototypeFacts.current = facts;
  const [ready, setReady] = useState(false);
  const [anchors, setAnchors] = useState<DateAnchor[]>([]);
  const [, refresh] = useState(0);
  const [selecting, setSelecting] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [rewriting, setRewriting] = useState(false);
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [rewriteError, setRewriteError] = useState("");
  const [factsVisible, setFactsVisible] = useState(() => window.innerWidth > 600);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkText, setLinkText] = useState("");
  const [sourceOpen, setSourceOpen] = useState(false);
  const [tableTarget, setTableTarget] = useState<string | null>(null);
  const linkCapture = useRef<{ doc: ProseMirrorNode; bookmark: SelectionBookmark } | null>(null);
  const imageTarget = useRef<string | undefined>(undefined);
  const [rewriteSource, setRewriteSource] = useState("");
  const [blockTarget, setBlockTarget] = useState<string | null>(null);
  const selectedBlock = useRef<string | null>(null);
  selectedBlock.current = blockTarget;
  const [syncRecords, setSyncRecords] = useState(initial.workspace.syncRecords);
  const rewriteSelection = useRef<ReturnType<typeof selectedRange>>(null);
  const rewriteCapture = useRef<CapturedEditorSelection | null>(null);
  const [editorWarning, setEditorWarning] = useState("");
  const [targets, setTargets] = useState<{ id: string; label: string }[]>([]);
  const [applying, setApplying] = useState(false);
  const [recovery, setRecovery] = useState(false);
  const [writerMode, setWriterMode] = useState<WriterMode | null>(null);
  const assistantCallbacks = useRef({ onHistoryNavigation, onAssistantFence });
  assistantCallbacks.current = { onHistoryNavigation, onAssistantFence };
  const presentation = useMemo<{ blocks: PresentationBlocks }>(() => ({ blocks: initial.presentation?.blocks ?? {} }), []);
  const imageInput = useRef<HTMLInputElement>(null);
  const bridge = useMemo(() => ({ session: writerConnection?.proof?.sessionId ?? crypto.randomUUID(), group: 0, composing: false, observing: false, replaying: false,
    kind: "typing" as RichMutation["kind"],
    lastTypingAt: 0, history: null as SessionHistory | null, queue: null as RichSaveQueue | null, intents: null as IntentQueue<FactIntent> | null,
    prepared: null as PreparedEditorBridge | null, applying: false, fenced: false,
    writer: null as BackgroundWriter | null, backgroundHistory: false, compositionWaiters: new Set<() => void>(),
    latestSelection: null as ReturnType<typeof selectedRange>,
    assistantFlush: async (): Promise<RichProjectResponse> => { throw new Error("Редактор ещё открывается"); },
    timeline: async (): Promise<TimelineReport> => ({ warnings: [], estimates: [] }),
    cascadePreview: async (_anchor: DateAnchor): Promise<DateCascadeProposal> => { throw new Error("Редактор ещё открывается"); },
    cascadeApply: async (_proposal: DateCascadeProposal): Promise<void> => {},
    fragments: new Map<string, string>(), projectionError: null as string | null,
    current: new Map<string, CellValue>(), values: new Map<string, Stored>(), original: new Map<string, RichBlock>(),
    undo: () => {}, redo: () => {}, complete: () => {}, panel: async (_command: PanelCommand): Promise<void> => {}, rewrite: async (_instruction: string): Promise<void> => {}, retry: async (_id: string): Promise<void> => {}, resolve: async (_id: string): Promise<void> => {}, timer: null as ReturnType<typeof setTimeout> | null }), []);
  const assets = useMemo(() => ({ upload: async (_file: File, _block?: string, _after?: string): Promise<void> => {}, cancel: (_block: string) => {},
    paste: (_event: ClipboardEvent | DragEvent): boolean => false, command: (_id: string, _command: string, _target?: string) => {} }), []);
  const timelineControls = useMemo<TimelineControls>(() => ({ read: () => bridge.timeline(),
    preview: anchor => bridge.cascadePreview(anchor), apply: proposal => bridge.cascadeApply(proposal) }), [bridge]);
  const extension = useMemo(() => createExtension({ key: "foldcv-rich-session", runsBefore: ["link"], tiptapExtensions: [tableIdentityAttributes, structureIdentityAttributes,
    Extension.create({ name: "foldcv-local-image-drop", priority: 1000, addProseMirrorPlugins: () => [new Plugin({ props: {
      handleDOMEvents: { drop: (_view, event) => assets.paste(event) },
    } })] })],
    prosemirrorPlugins: [tableIdentityPlugin(), bindingIdentityPlugin(), structureIdentityPlugin(), pastedRegionsPlugin(), presentationPlugin(() => presentation.blocks, presentationLogos),
      prototypePresentation(() => prototypeFacts.current, () => selectedBlock.current), new Plugin({
    key: new PluginKey("foldcv-rich-session"), filterTransaction: transaction => {
      if (!transaction.docChanged) return true;
      if ((bridge.applying || bridge.fenced || bridge.writer && !bridge.writer.writable) && !bridge.replaying) return false;
      const root = transaction.doc.firstChild;
      if (!root || root.childCount !== 3) return false;
      return ["header", "sidebar", "main"].every((id, index) => {
        const item = root.child(index); const value: unknown = item.attrs["id"];
        return value === id && item.firstChild?.type.name === "region";
      });
    }, props: { handleDrop: (_view, event) => assets.paste(event), handlePaste: (view, event, slice) => {
      if (assets.paste(event)) return true;
      const flattened = flattenPastedRegions(slice);
      if (flattened) { bridge.group++; view.dispatch(view.state.tr.replaceSelection(flattened).scrollIntoView()); return true; }
      const tr = authoredPasteTransaction(view.state, slice);
      if (!tr) return false;
      bridge.group++; view.dispatch(tr); return true;
    }, handleKeyDown: (view, event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
        event.preventDefault(); view.dispatch(view.state.tr.setSelection(new AllSelection(view.state.doc))); return true;
      }
      if (["Backspace", "Delete"].includes(event.key)) {
        const tr = deleteAcrossRegions(view.state);
        if (tr) { event.preventDefault(); bridge.group++; view.dispatch(tr); return true; }
      }
      if (event.key === "Enter" && !bridge.composing) queueMicrotask(() => bridge.complete());
      if (!(event.metaKey || event.ctrlKey) || !["z", "y"].includes(event.key.toLowerCase())) return false;
      event.preventDefault(); if (!bridge.composing) { bridge.group++; if (event.shiftKey || event.key.toLowerCase() === "y") bridge.redo(); else bridge.undo(); } return true;
    }, handleDOMEvents: {
      compositionstart: () => { bridge.group++; bridge.composing = true; return false; },
      compositionend: () => { queueMicrotask(() => { bridge.composing = false; bridge.complete(); bridge.group++;
        for (const resolve of bridge.compositionWaiters) resolve(); bridge.compositionWaiters.clear(); }); return false; },
      blur: () => { if (!bridge.composing) { bridge.complete(); bridge.group++; } return false; },
      beforeinput: (_view, event) => {
        if (!(event instanceof InputEvent) || !["historyUndo", "historyRedo"].includes(event.inputType)) return false;
        event.preventDefault(); if (!bridge.composing) { if (event.inputType === "historyUndo") bridge.undo(); else bridge.redo(); } return true;
      },
    } },
  })] }), [bridge, assets, presentation]);
  const editor = useCreateBlockNote({ schema, disableExtensions: ["history"], extensions: [extension],
    pasteHandler: ({ event, defaultPasteHandler }) => assets.paste(event) || defaultPasteHandler(),
    tables: { splitCells: true, cellBackgroundColor: true, cellTextColor: true, headers: true }, links: {
    onClick: event => {
      event.preventDefault();
      const anchor = event.target instanceof Element ? event.target.closest("a") : null;
      if ((event.metaKey || event.ctrlKey) && anchor instanceof HTMLAnchorElement) window.open(anchor.href, "_blank", "noopener,noreferrer");
      return false;
    },
  }, initialContent:
    project.document.regions.map(region => ({ id: region.id, type: "region", props: { role: region.role }, children: region.blocks.map(toBlock) })) }, []);

  useEffect(() => editor.onSelectionChange(() => {
    const next = editor.transact(tr => selectedRange(tr)); bridge.latestSelection = next; setSelecting(next !== null);
    refresh(value => value + 1);
  }), [editor, bridge]);
  useEffect(() => { editor.transact(tr => { tr.setMeta("foldcv-uir-target", true); }); }, [editor, blockTarget]);
  const captureSelected = useCallback((selection: ReturnType<typeof selectedRange>): CapturedEditorSelection | null => {
    if (!selection || !bridge.history) return null;
    const keys = new Set(selection.blockIds.map(id => `block:${id}`));
    let expanded = true;
    while (expanded) {
      expanded = false;
      for (const [key, value] of bridge.current) {
        if (key.startsWith("region:")) keys.add(key);
        const stored = value ? bridge.values.get(value) : undefined;
        if (key.startsWith("block:") && !keys.has(key) && stored?.children.some(id => keys.has(`block:${id}`))) { keys.add(key); expanded = true; }
      }
    }
    return { selection: structuredClone(selection), session: bridge.session,
      epochs: new Map([...keys].map(key => [key, bridge.history?.revision(key) ?? 0])) };

  }, [bridge]);
  const openRewrite = useCallback(() => {
    const selected = editor.transact(tr => selectedRange(tr)), browserSelection = window.getSelection();
    if (!selected || !browserSelection?.rangeCount) return;
    setRewriteSource(browserSelection.toString());
    rewriteCapture.current = captureSelected(selected);
    if (rewriteCapture.current) {
      const epochs = new Map(rewriteCapture.current.epochs);
      const records = new Set<string>();
      const collect = (value: unknown) => {
        if (Array.isArray(value)) value.forEach(collect);
        else if (value && typeof value === "object") {
          if ("recordId" in value && typeof value.recordId === "string") records.add(value.recordId);
          Object.values(value).forEach(collect);
        }
      };
      for (const id of selected.blockIds) {
        const value = bridge.current.get(`block:${id}`); if (value) collect(bridge.values.get(value)?.block);
      }
      for (const key of bridge.current.keys()) if ([...records].some(id => key === `fact:${id}` || key.startsWith("fact-field:") && key.includes(JSON.stringify(id))))
        epochs.set(key, bridge.history?.revision(key) ?? 0);
      rewriteCapture.current = { ...rewriteCapture.current, epochs };
    }
    rewriteSelection.current = structuredClone(selected); setRewriteError(""); setRewriteOpen(true);
  }, [editor, bridge, captureSelected]);
  const selectionToolbar = useCallback(() => selecting ? <SelectionToolbar rewrite={openRewrite} disabled={rewriting} /> : null, [openRewrite, selecting, rewriting]);
  const blockSideMenu = useCallback(() => <BlockSideMenu open={setBlockTarget} />, []);
  const selectionFloating = useMemo(() => ({ useFloatingOptions: { placement: "top-start" as const,
    middleware: [{ name: "uir-selection-position", fn: ({ x, y }: { x: number; y: number }) => {
      const selection = window.getSelection(), range = selection?.rangeCount ? selection.getRangeAt(0).getBoundingClientRect() : null;
      return range ? { x: Math.max(12, Math.min(window.innerWidth - 160, range.left)), y: Math.max(65, range.top - 36) } : { x, y };
    } }] } }), []);
  useEffect(() => { presentation.blocks = initial.presentation?.blocks ?? {};
    editor.transact(tr => { tr.setMeta("foldcv-presentation", true); });
  }, [editor, initial.presentation, presentation]);

  useEffect(() => {
    const originalDocument = project.document;
    for (const region of originalDocument.regions) {
      const remember = (block: RichBlock) => { bridge.original.set(block.id, block); block.children.forEach(remember); };
      region.blocks.forEach(remember);
    }
    function serialize(block: EditorBlock): RichBlock {
      const old = bridge.original.get(block.id);
      if (block.type === "region") throw new Error("Region is not a content block");
      const sources = editor.transact(tr => readBlockSources(tr.doc).get(block.id)) ?? [];
      const provenance = [...new Map([...(old?.provenance ?? []), ...sources.flatMap(id => bridge.original.get(id)?.provenance ?? [])]
        .filter(link => block.type !== "section" || block.props.recordId || link.kind !== "working_owner")
        .map(link => [link.id, link])).values()];
      const identity = { id: block.id, revision: old?.revision ?? 1, provenance, children: block.children.map(serialize) };
      if (block.type === "divider") return { ...identity, type: "divider", props: {}, content: null };
      if (block.type === "codeBlock") return { ...identity, type: "code", props: { language: block.props.language,
        backgroundColor: wireColor(block.props.backgroundColor, "background") }, content: block.content.map(span => span.text).join("") };
      const fragment = (binding: string, part: string) => {
        const key = `${binding}:${part}`; let id = bridge.fragments.get(key);
        if (!id) { id = crypto.randomUUID(); bridge.fragments.set(key, id); } return id;
      };
      if (block.type === "table") {
        const ids = editor.transact(tr => readTableIdentities(tr.doc).get(block.id));
        if (!ids) throw new Error("RICH_TABLE_IDENTITY_MISSING");
        return { ...identity, type: "table", props: old?.type === "table" ? { ...old.props, textColor: wireColor(block.props.textColor, "text") }
          : { alignment: "left", backgroundColor: "default", textColor: wireColor(block.props.textColor, "text") },
          content: fromTable(block.content, ids, old?.type === "table" ? old.content : undefined, fragment) };
      }
      if (block.type === "image") {
        if (!block.props.assetId) return { ...identity, type: "paragraph", props: { alignment: "left" }, content: fromInline(block.content, fragment) };
        return { ...identity, type: "image", props: { assetId: block.props.assetId, alt: block.props.alt, width: block.props.width,
          height: block.props.height, alignment: block.props.textAlignment, caption: fromInline(block.content, fragment) }, content: null };
      }
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
    function tableIds(document: RichDocumentV1) {
      const tables = new Map<string, TableRowIdentity[]>();
      const visit = (block: RichBlock) => { if (block.type === "table") tables.set(block.id, block.content.rows.map(row => ({ id: row.id, cells: row.cells.map(cell => cell.id) }))); block.children.forEach(visit); };
      document.regions.forEach(region => region.blocks.forEach(visit)); return tables;
    }
    bridge.replaying = true;
    editor.transact(tr => { restoreTableIdentities(tr, tableIds(originalDocument)); });
    bridge.replaying = false;
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
    function replace(document: RichDocumentV1) {
      const remember = (block: RichBlock) => { bridge.original.set(block.id, block); block.children.forEach(remember); };
      document.regions.forEach(region => region.blocks.forEach(remember));
      editor.transact(tr => {
        document.regions.forEach(region => editor.updateBlock(region.id, { children: region.blocks.map(toBlock) }));
        restoreEmptyRegions(tr, new Set(document.regions.filter(region => !region.blocks.length).map(region => region.id)));
        restoreTableIdentities(tr, tableIds(document));
      });
    }
    assets.command = (id, command, target) => {
      try {
      available();
      const selected = commandBlock(id, block => editor.getBlock(block));
      editor.setTextCursorPosition(selected.id, "start");
      bridge.group++;
      if (command === "delete") editor.removeBlocks([selected.id]);
      else if (command === "up") editor.moveBlocksUp(selected.id);
      else if (command === "down") editor.moveBlocksDown(selected.id);
      else if (command === "nest") editor.nestBlock();
      else if (command === "unnest") editor.unnestBlock();
      else if (command === "move" && target) replace(moveBlock(document(), selected.id, target));
      else if (command === "merge") {
        let previous = editor.getTextCursorPosition().prevBlock;
        while (previous?.children.length) previous = previous.children.at(-1);
        if (!previous) throw new Error("Нет предыдущего текстового блока");
        replace(mergeBlocks(document(), previous.id, selected.id));
      }
      else if (command === "duplicate") {
        const copy = copyBlock(serialize(selected));
        assertImageCapacity(imageIds(copy));
        const remember = (block: RichBlock) => { bridge.original.set(block.id, block); block.children.forEach(remember); };
        remember(copy);
        editor.transact(tr => { editor.insertBlocks([toBlock(copy)], selected.id, "after");
          const ids = new Map<string, TableRowIdentity[]>();
          const visit = (block: RichBlock) => { if (block.type === "table") ids.set(block.id, block.content.rows.map(row => ({ id: row.id, cells: row.cells.map(cell => cell.id) }))); block.children.forEach(visit); };
          visit(copy); restoreTableIdentities(tr, ids); });
      }
      } catch (error) { setEditorWarning(error instanceof Error ? error.message : "Не удалось изменить блок"); }
    };
    const cells = (document: RichDocumentV1) => documentCells(document, bridge.values);
    const withFacts = (doc: RichDocumentV1, facts: typeof project.facts) => new Map([...cells(doc), ...factCells(facts)]);
    bridge.current = withFacts(document(), project.facts);
    const assetHashes = new Map([...project.assets, ...(writerConnection?.local?.record.assets ?? [])].map(asset => [asset.id, asset.sha256]));
    const queue = new RichSaveQueue(initial, bridge.session, request => bridge.writer ? bridge.writer.save(request) : saveMutation(request), acknowledge);
    bridge.queue = queue;
    function schedule() {
      if (bridge.applying || bridge.fenced || bridge.intents?.awaitingSave || bridge.writer && bridge.writer.mode !== "normal") return;
      onStatus("Изменения сохраняются…");
      if (bridge.timer) clearTimeout(bridge.timer);
      if (bridge.composing) return;
      bridge.timer = setTimeout(() => { void queue.flush().then(() => onStatus("Сохранено")).catch(error => onStatus(error instanceof Error ? error.message : "Не удалось сохранить")); }, 400);
    }
    function rebuild(id: string, values = bridge.current): RichBlock {
      const value = values.get(`block:${id}`), stored = value ? bridge.values.get(value) : undefined;
      if (!stored) throw new Error("History block is missing");
      const block = { ...stored.block, children: stored.children.map(child => rebuild(child, values)) };
      bridge.original.set(id, block); return block;
    }
    const history = new SessionHistory(bridge.session, bridge.current, (changes, context) => {
      const next = new Map(bridge.current);
      for (const change of changes) next.set(change.key, change.after);
      if (!bridge.observing) {
        bridge.replaying = true;
        try {
          editor.transact(tr => {
            const empty = new Set<string>();
            originalDocument.regions.forEach(region => {
            const value = next.get(`region:${region.id}`);
            const ids: unknown = value ? JSON.parse(value) : [];
            if (!Array.isArray(ids) || !ids.every((id: unknown) => typeof id === "string")) throw new Error("History region is invalid");
            const children = ids.map((id: string) => toBlock(rebuild(id, next)));
            if (!children.length) empty.add(region.id);
            editor.updateBlock(region.id, { children });
            });
            restoreEmptyRegions(tr, empty);
            const tables = new Map<string, TableRowIdentity[]>();
            for (const value of next.values()) {
              const stored = value ? bridge.values.get(value) : undefined;
              if (stored?.block.type === "table") tables.set(stored.block.id, stored.block.content.rows.map(row => ({ id: row.id, cells: row.cells.map(cell => cell.id) })));
            }
            restoreTableIdentities(tr, tables);
          });
        } finally { bridge.replaying = false; }
      }
      bridge.current = next;
      const nextFacts = factsFromCells(bridge.current, queue.baseline.workspace.project?.facts ?? initialFacts);
      setFacts(nextFacts);
      if (context.mode !== "prepared" && !bridge.backgroundHistory) {
        if (changes.some(change => !change.key.startsWith("request:"))) bridge.writer?.input(context.kind === "undo" || context.kind === "redo" ? context.kind : bridge.kind);
        if (!bridge.writer || bridge.writer.mode === "normal") {
        queue.update(document(), context.mode === "assistant_history" ? context.actionId ?? bridge.session : history.currentActionId ?? `${bridge.session}:typing`,
          context.mode === "assistant_history" ? context.kind : bridge.kind, nextFacts);
        schedule();
        }
      }
      if (context.mode !== "ordinary") setAnchors([]);
      refresh(value => value + 1);
      queueMicrotask(() => sync.invalidate());
      imageRevision++;
      if (context.mode !== "prepared") queueMicrotask(() => { void publishImageReferences().catch(error => onStatus(error instanceof Error ? error.message : "IMAGE_IMPORT_FAILED")); });
    }, context => !bridge.writer || bridge.writer.writable || context.mode === "prepared" || bridge.backgroundHistory);
    bridge.history = history;
    const sync = new RichSynchronization({ history, queue, current: () => bridge.current,
      cells: response => {
        const current = response.workspace.project; if (!current) throw new Error("Document missing");
        return withFacts(current.document, current.facts);
      }, changed: () => { queue.update(document(), history.currentActionId ?? bridge.session, bridge.kind,
        factsFromCells(bridge.current, queue.baseline.workspace.project?.facts ?? initialFacts)); schedule(); },
      report: response => { setSyncRecords(response.workspace.syncRecords); },
      failed: error => setEditorWarning(error instanceof Error ? error.message : "Синхронизация не завершена"),
      applied: (action, changes) => { const next = dateAnchors(action, changes); if (next.length) setAnchors(next); },
    }, initial.workspace.projectId);
    let pendingAction: string | null = null;
    const pendingBlocks = new Set<string>(), movedBlocks = new Set<string>(), removedRecords = new Set<string>();
    const removedFields = new Map<string, RichCompletionRequest["removedFields"][number]>();
    const completedActions = new Set<string>();
    function finishEdit() {
      if (!pendingAction || completedActions.has(pendingAction) || bridge.composing || !open) return;
      const action = pendingAction, ids = [...pendingBlocks], moved = [...movedBlocks], removed = [...removedFields.values()], deleted = [...removedRecords];
      completedActions.add(action); pendingAction = null; pendingBlocks.clear(); movedBlocks.clear(); removedFields.clear(); removedRecords.clear();
      void sync.complete(action, ids.filter(id => !!editor.getBlock(id)), moved, removed, true, deleted).catch(error => setEditorWarning(error instanceof Error ? error.message : "Синхронизация не завершена"));
    }
    function available() {
      if (bridge.applying || bridge.fenced) throw new Error("Дождитесь завершения сохранения");
      if (bridge.writer && bridge.writer.mode !== "normal") throw new Error("Сначала восстановите черновик");
      if (bridge.composing) throw new Error("Завершите ввод текста");
      if (bridge.projectionError) throw new Error(bridge.projectionError);
    }
    const intents = new IntentQueue<FactIntent>(async intent => {
      available(); finishEdit(); bridge.group++; bridge.kind = intent.kind;
      try {
        if (intent.kind === "panel") await sync.panel(intent.command);
        else await sync.cascadeApply(intent.proposal);
      } catch (error) {
        if (error instanceof AppliedIntentFailure) {
          if (bridge.timer) clearTimeout(bridge.timer);
          onStatus(error.message);
        }
        throw error;
      } finally { bridge.kind = "typing"; }
    }, setFactIntents);
    bridge.intents = intents;
    if (writerConnection) {
      bridge.writer = new BackgroundWriter(writerConnection, { queue, history,
        snapshot: () => ({ document: document(), facts: factsFromCells(bridge.current, queue.baseline.workspace.project?.facts ?? initialFacts),
          assets: [...assetHashes].map(([id, sha256]) => ({ id, sha256 })) }),
        cells: response => { const value = response.workspace.project; if (!value) throw new Error("Document missing"); return withFacts(value.document, value.facts); },
        flushLocal: async () => { await intents.drain(); await queue.flush(); },
        compositionEnd: () => bridge.composing ? new Promise(resolve => bridge.compositionWaiters.add(resolve)) : Promise.resolve(),
        lock: locked => { bridge.applying = locked; setApplying(locked); editor.isEditable = !locked; imageRevision++;
          if (locked && bridge.timer) clearTimeout(bridge.timer); },
        changed: (mode, error) => { setWriterMode(mode); if (error) setEditorWarning(error);
          if (mode === "recovering") onStatus("Требуется восстановление черновика"); },
        saved: () => onStatus("Сохранено"),
        applyHistory: direction => { bridge.backgroundHistory = true;
          try { return direction === "undo" ? history.undo() : history.redo(); } finally { bridge.backgroundHistory = false; } },
      });
      if (bridge.writer.mode === "read_only") editor.isEditable = false;
      if (bridge.writer.mode === "recovering") queue.fencePrepared();
    }
    bridge.assistantFlush = async () => {
      available(); await intents.drain(); finishEdit(); await queue.flush();
      queue.refreshMetadata(await projectRequest(`/${initial.workspace.projectId}`));
      return queue.baseline;
    };
    bridge.prepared = new PreparedEditorBridge({ history, queue, flush: () => bridge.assistantFlush(),
      cells: response => {
        const current = response.workspace.project; if (!current) throw new Error("Document missing");
        return withFacts(current.document, current.facts);
      }, preview: batch => projectRequest(`/${initial.workspace.projectId}/preview`, "POST", batch.mutation),
      enter: () => { bridge.applying = true; setApplying(true); if (bridge.timer) clearTimeout(bridge.timer); editor.isEditable = false; },
      leave: () => { bridge.applying = false; setApplying(false); if (!bridge.fenced) editor.isEditable = true; },
      retainImages: async () => { await publishImageReferences(); },
      fence: receipt => {
        bridge.fenced = true; setRecovery(true); editor.isEditable = false;
        setEditorWarning(receipt?.durable ? "Правки сохранены. Откройте резюме заново для продолжения." : "Нужно подтвердить сохранение. Откройте резюме заново.");
        assistantCallbacks.current.onAssistantFence?.(receipt?.durable ?? false);
      } });
    bridge.rewrite = async instruction => {
      available();
      if (!rewriteSelection.current || bridge.composing) throw new Error("Выделите фрагмент текста");
      if (!capturedSelectionCurrent(rewriteCapture.current, bridge.history, bridge.session))
        throw new Error("Выделение устарело. Запросите правку заново.");
      const captured: RichSelection = { ...rewriteSelection.current, textSha256: "0".repeat(64), capture: { sessionId: bridge.session,
        actionId: bridge.session, actionToken: 0, dependencies: [] } };
      await sync.rewrite(captured, instruction);
    };
    bridge.resolve = id => { available(); return sync.resolve(id); };
    bridge.timeline = async () => { await queue.flush(); return readTimeline(initial.workspace.projectId); };
    bridge.cascadePreview = async anchor => { available(); await intents.drain(); return sync.cascadePreview(anchor.jobId, anchor.periodId, anchor.actionId); };
    bridge.cascadeApply = proposal => { available(); return intents.enqueue({ kind: "cascade", proposal }); };
    bridge.panel = command => { available(); return intents.enqueue({ kind: "panel", command }); };
    bridge.retry = async id => {
      available();
      const response = await projectRequest(`/${initial.workspace.projectId}`), record = response.workspace.syncRecords.find(item => item.id === id);
      if (!record) return;
      if (record.kind === "panel" || record.kind === "rewrite" && record.selection && record.instruction) await sync.retry(record.id, record.blockIds);
      else {
        const marker = `request:${crypto.randomUUID()}`, action = history.commit("structure", [{ key: marker, before: null, after: "retry" }]);
        if (action) await sync.complete(action, record.blockIds.filter(id => !!editor.getBlock(id)), [], []);
      }
    };

    let imageRevision = 1, open = true, sessionUpdates: Promise<unknown> = Promise.resolve();
    const imageSessionId = () => bridge.writer?.connection.proof?.incarnation ?? bridge.session;
    let previousSessionId: string | null = null;
    try { if (!writerConnection || writerConnection.proof) previousSessionId = sessionStorage.getItem(`foldcv-image-session:${initial.workspace.projectId}`); } catch { /* Current pins stay retained when storage is unavailable. */ }
    const uploads = new Map<string, AbortController>();
    const knownAssets = new Set(project.assets.map(asset => asset.id));
    function imageIds(block: RichBlock): string[] {
      return [...(block.type === "image" ? [block.props.assetId] : []), ...block.children.flatMap(imageIds)];
    }
    function assertImageCapacity(additions: string[]) {
      const live = document().regions.flatMap(region => region.blocks.flatMap(imageIds));
      if (!validateImageSession({ sessionId: bridge.session, revision: imageRevision, live: [...live, ...additions], history: [] }))
        throw new Error("В документе может быть не более 20 изображений");
    }
    function imageReferences(): ImageSessionRequest {
      if (!open) return { sessionId: imageSessionId(), revision: imageRevision, live: [], history: [], closed: true, previousSessionId };
      const live: string[] = [];
      const visit = (block: RichBlock) => { if (block.type === "image") live.push(block.props.assetId); block.children.forEach(visit); };
      document().regions.forEach(region => region.blocks.forEach(visit));
      const retained = new Set<string>();
      for (const id of writerConnection?.local?.payload.assetPins ?? []) retained.add(id);
      for (const value of history.retainedValues()) {
        const stored = value ? bridge.values.get(value) : undefined;
        if (stored?.block.type === "image") retained.add(stored.block.props.assetId);
      }
      const capture = { sessionId: imageSessionId(), revision: imageRevision, live, history: [...retained], closed: !open, previousSessionId };
      if (!validateImageSession(capture)) throw new Error("IMAGE_REFERENCE_LIMIT");
      return capture;
    }
    function publishImageReferences(): Promise<unknown> {
      const capture = imageReferences();
      sessionUpdates = sessionUpdates.catch(() => {}).then(async () => {
        const result = await projectRequest(`/${initial.workspace.projectId}/images/session`, "POST", { ...capture, previousSessionId });
        previousSessionId = capture.sessionId;
        try { sessionStorage.setItem(`foldcv-image-session:${initial.workspace.projectId}`, capture.sessionId); } catch { /* Server pins remain authoritative. */ }
        return result;
      });
      return sessionUpdates;
    }
    assets.cancel = block => uploads.get(block)?.abort();
    assets.upload = async (file, blockId, after) => {
      available();
      setEditorWarning("");
      if (bridge.composing) throw new Error("Завершите ввод текста");
      if (!open || (!["image/png", "image/jpeg", "image/webp"].includes(file.type) && !/\.(png|jpe?g|webp)$/i.test(file.name))) throw new Error("Выберите PNG, JPEG или WebP");
      if (!file.size || file.size > 10 * 1024 * 1024) throw new Error("Изображение превышает 10 МБ");
      const revision = imageRevision;
      const cursor = blockId || after ? editor.getBlock(blockId ?? after ?? "") : editor.getTextCursorPosition().block;
      if (!cursor || cursor.type === "region") throw new Error("Выберите место в документе");
      const controller = new AbortController(), key = blockId ?? crypto.randomUUID();
      uploads.get(key)?.abort(); uploads.set(key, controller);
      try {
        await queue.flush(); await publishImageReferences();
        available();
        if (!open || controller.signal.aborted || imageRevision !== revision) throw new Error("Загрузка отменена: документ изменился");
        const replacement = blockId && cursor.type === "image" && cursor.props.assetId ? cursor.props.assetId : undefined;
        const result = await uploadImage(initial.workspace.projectId, file, { sessionId: imageSessionId(), revision,
          actionId: crypto.randomUUID(), reservationId: crypto.randomUUID(), replacementId: replacement ?? null }, controller.signal);
        if (!open || controller.signal.aborted || imageRevision !== revision || !editor.getBlock(cursor.id)) throw new Error("Загрузка отменена: документ изменился");
        const { asset } = result, width = blockId && cursor.type === "image" ? cursor.props.width : Math.min(300, asset.width * .75);
        available(); assetHashes.set(asset.id, asset.sha256);
        knownAssets.add(asset.id);
        bridge.group++; acknowledge(result.response);
        const imageBlock: InputBlock = { type: "image", props: { assetId: asset.id, alt: blockId && cursor.type === "image" ? cursor.props.alt : "",
          width, height: width * asset.height / asset.width, textAlignment: blockId && cursor.type === "image" ? cursor.props.textAlignment : "left" } };
        if (blockId) editor.updateBlock(blockId, imageBlock);
        else editor.insertBlocks([imageBlock], cursor.id, "after");
      } finally {
        if (uploads.get(key) === controller) uploads.delete(key);
        imageRevision++; await publishImageReferences().catch(() => {});
      }
    };
    assets.paste = event => {
      const transfer = "clipboardData" in event ? event.clipboardData : event.dataTransfer;
      const files = transfer ? [...transfer.files] : [];
      if (files.length) {
        event.preventDefault();
        const after = event.type === "drop" && event.target instanceof Element ? event.target.closest("[data-id]")?.getAttribute("data-id") ?? undefined : undefined;
        void (async () => { for (const file of files) await assets.upload(file, undefined, after); })().catch(error => setEditorWarning(error instanceof Error ? error.message : "Не удалось добавить изображение"));
        return true;
      }
      const html = transfer?.getData("text/html") ?? "";
      const internal = transfer?.getData("blocknote/html") ?? "";
      if (event.type === "drop" && editor.prosemirrorView.dragging) return false;
      if (internal) {
        event.preventDefault(); const parsed = window.document.createElement("template"); parsed.innerHTML = internal;
        for (const img of parsed.content.querySelectorAll("img")) img.remove();
        for (const controls of parsed.content.querySelectorAll(".cv-image-controls")) controls.remove();
        let unavailable = false;
        for (const block of parsed.content.querySelectorAll('[data-content-type="image"]')) {
          const id = block.getAttribute("data-asset-id");
          if (id && knownAssets.has(id)) continue;
          const paragraph = window.document.createElement("p"); paragraph.textContent = block.getAttribute("data-alt") || block.textContent || "Изображение";
          block.replaceWith(paragraph); unavailable = true;
        }
        for (const field of parsed.content.querySelectorAll('[data-inline-content-type="factField"]')) {
          const record = field.getAttribute("data-record-id");
          if (record && project.facts.records.some(fact => fact.id === record)) continue;
          field.replaceWith(...field.childNodes); unavailable = true;
        }
        try { assertImageCapacity([...parsed.content.querySelectorAll('[data-content-type="image"]')].map(block => block.getAttribute("data-asset-id") ?? "")); }
        catch (error) { setEditorWarning(error instanceof Error ? error.message : "Не удалось вставить изображение"); return true; }
        editor.pasteHTML(parsed.innerHTML, true);
        if (unavailable) setEditorWarning("Часть связей отсутствует в этом проекте. Текст сохранён; изображение добавьте локальным файлом.");
        return true;
      }
      if (/<img\b/i.test(html)) {
        event.preventDefault();
        const parsed = window.document.createElement("template"); parsed.innerHTML = html;
        for (const img of parsed.content.querySelectorAll("img")) {
          const alt = img.getAttribute("alt") ?? "", source = img.getAttribute("src") ?? "";
          if (/^https?:\/\//i.test(source)) { const link = window.document.createElement("a"); link.href = source; link.textContent = alt || source; img.replaceWith(link); }
          else img.replaceWith(window.document.createTextNode(alt || "Изображение"));
        }
        editor.pasteHTML(parsed.innerHTML); setEditorWarning("Удалённое изображение не загружено. Выберите локальный файл."); return true;
      }
      return false;
    };
    void publishImageReferences().catch(error => onStatus(error instanceof Error ? error.message : "IMAGE_IMPORT_FAILED"));
    const closeOnUnload = () => { if (bridge.writer?.connection.proof && !["detached", "closed", "read_only"].includes(bridge.writer.mode)) {
        navigator.sendBeacon(`/v1/rich/projects/${initial.workspace.projectId}/writer/suspend`,
          new Blob([JSON.stringify(bridge.writer.connection.proof)], { type: "application/json" }));
      }
      if (bridge.writer?.retainsDraft && writerConnection?.proof) return;
      navigator.sendBeacon(`/v1/rich/projects/${initial.workspace.projectId}/images/session`,
      new Blob([JSON.stringify({ sessionId: imageSessionId(), revision: imageRevision + 1, live: [], history: [], closed: true, previousSessionId })], { type: "application/json" })); };
    window.addEventListener("pagehide", closeOnUnload, { capture: true });
    const navigateHistory = (direction: "undo" | "redo") => {
      if (intents.busy || bridge.composing || bridge.projectionError || bridge.applying || bridge.fenced || bridge.writer && !bridge.writer.writable) return;
      void (async () => {
        if (bridge.writer && await bridge.writer.history(direction)) return;
        if (!bridge.writer) assistantCallbacks.current.onHistoryNavigation?.();
        bridge.kind = direction; try { if (direction === "undo") history.undo(); else history.redo(); } finally { bridge.kind = "typing"; }
      })().catch(error => setEditorWarning(error instanceof Error ? error.message : "HISTORY_FAILED"));
    };
    bridge.undo = () => navigateHistory("undo"); bridge.redo = () => navigateHistory("redo");
    function observe() {
      if (bridge.replaying || bridge.applying || bridge.fenced) return;
      let next: Map<string, CellValue>;
      try { const doc = document(); next = new Map([...bridge.current].filter(([key]) => !key.startsWith("block:") && !key.startsWith("region:")));
        for (const [key, value] of cells(doc)) next.set(key, value); bridge.projectionError = null;
        const destinations: { id: string; label: string }[] = doc.regions.map(region => ({ id: region.id,
          label: region.role === "header" ? "Заголовок" : region.role === "sidebar" ? "Боковая колонка" : "Основная колонка" }));
        const title = (block: RichBlock): string => Array.isArray(block.content) ? block.content.map(span => span.type === "link"
          ? span.content.map(text => text.text).join("") : span.text).join("") : "";
        const visit = (block: RichBlock) => { if (block.type === "section") destinations.push({ id: block.id,
          label: title(block) || block.children.map(title).find(text => text.trim()) || "Раздел" }); block.children.forEach(visit); };
        doc.regions.forEach(region => region.blocks.forEach(visit)); setTargets(destinations);
      }
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
        if (id) {
          if (!bridge.writer || bridge.writer.mode === "normal") queue.update(document(), id, kind, factsFromCells(bridge.current, queue.baseline.workspace.project?.facts ?? initialFacts));
          pendingAction = id; completedActions.delete(id);
          for (const change of changes) {
            if (change.key.startsWith("block:")) {
              const blockId = change.key.slice(6); pendingBlocks.add(blockId);
              const old = change.before ? bridge.values.get(change.before) : undefined;
              const remember = (item: unknown) => {
                if (Array.isArray(item)) item.forEach(remember);
                else if (typeof item === "object" && item !== null) {
                  if ("type" in item && item.type === "fact_field" && "recordId" in item && typeof item.recordId === "string"
                    && "fieldKey" in item && typeof item.fieldKey === "string" && "bindingId" in item && typeof item.bindingId === "string") {
                    const rootId = "bindingRootId" in item && typeof item.bindingRootId === "string" ? item.bindingRootId : item.bindingId;
                    removedFields.set(rootId, { recordId: item.recordId, fieldKey: item.fieldKey, rootId });
                  }
                  Object.values(item).forEach(remember);
                }
              };
              if (old) {
                remember(old.block);
                if (!change.after && old.block.type === "section" && old.block.props.recordId) removedRecords.add(old.block.props.recordId);
              }
            }
            if ((change.key.startsWith("block:") || change.key.startsWith("region:")) && change.before && change.after) {
              const ids = (value: string): string[] => { const stored = bridge.values.get(value); if (stored) return stored.children;
                const parsed: unknown = JSON.parse(value); return Array.isArray(parsed) ? parsed.filter((id: unknown): id is string => typeof id === "string") : []; };
              for (const child of ids(change.after)) if (!ids(change.before).includes(child) && bridge.original.has(child)) movedBlocks.add(child);
            }
          }
          if (kind === "structure") queueMicrotask(finishEdit);
        }
      } finally { bridge.observing = false; bridge.kind = "typing"; }
    }
    const stop = editor.onChange(observe);
    observe();
    bridge.complete = () => { observe(); schedule(); finishEdit(); };
    // Only initial normalization is queued; acknowledgments never replace the editor.
    if (!bridge.writer || bridge.writer.mode === "normal") queue.update(document(), `${bridge.session}:initial`);
    const heartbeat = bridge.writer ? setInterval(() => { void bridge.writer?.heartbeat(); }, 5000) : null;
    const guardUnload = (event: BeforeUnloadEvent) => { if (bridge.writer?.needsUnloadGuard) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", guardUnload);
    let jobsWork: Promise<void> = Promise.resolve();
    const writer = bridge.writer, jobs = writer ? projectJobs(initial.workspace.projectId) : null;
    const unsubscribeJobs = jobs?.subscribe(view => {
      if (!writer || !view.project) return;
      const pending = view.project.jobs;
      jobsWork = jobsWork.catch(() => {}).then(async () => {
        for (const job of pending) {
          if (["closed", "detached", "read_only"].includes(writer.mode)) return;
          writer.observeJob(job);
          if (writer.mode === "recovering") { await writer.recoverPublication(job); continue; }
          if (["ready", "waiting_for_sync"].includes(job.publication) && job.proposalId) await writer.publish(job, await jobs.api.proposal(job.id));
          else if (job.receipt && !job.undoExpired) await writer.adoptHeadless(job);
        }
      }).catch(error => { if (writer.mode !== "closed") setEditorWarning(error instanceof Error ? error.message : "JOB_REQUEST_FAILED"); });
    });
    setReady(true);
    return () => { stop(); sync.close(); intents.close(); bridge.prepared?.close(); open = false; imageRevision++; for (const upload of uploads.values()) upload.abort();
      if (heartbeat) clearInterval(heartbeat); bridge.writer?.close(); bridge.compositionWaiters.forEach(resolve => resolve()); bridge.compositionWaiters.clear();
      unsubscribeJobs?.();
      window.removeEventListener("beforeunload", guardUnload);
      window.removeEventListener("pagehide", closeOnUnload, { capture: true });
      if (!bridge.writer?.retainsDraft || !writerConnection?.proof) void publishImageReferences().catch(() => {});
      history.close(); queue.close(); if (bridge.timer) clearTimeout(bridge.timer); };
  }, [editor, bridge]);
  useImperativeHandle(ref, () => ({ flush: async () => {
    if (bridge.fenced || bridge.applying) throw new Error(bridge.applying ? "Дождитесь завершения сохранения" : "Откройте резюме заново для продолжения");
    if (bridge.composing) throw new Error("Завершите ввод текста");
    if (!bridge.queue) throw new Error("Редактор ещё открывается");
    if (bridge.projectionError) throw new Error(bridge.projectionError);
    if (bridge.writer && bridge.writer.mode !== "normal") throw new Error("Сначала восстановите черновик");
    await bridge.intents?.drain(); await bridge.queue.flush(); await bridge.writer?.flushTouches(); return bridge.queue.baseline;
  }, background: writerConnection !== null, navigate: async () => {
    if (bridge.writer) await bridge.writer.navigate(); else { await bridge.intents?.drain(); await bridge.queue?.flush(); }
  }, resume: async () => { await bridge.writer?.resume(); },
  undo: () => bridge.undo(), redo: () => bridge.redo(), sessionId: bridge.session,
  focusFinding: anchor => {
    if (bridge.applying || !bridge.queue || !anchorCurrent(anchor, bridge.queue.baseline, bridge.current)) return false;
    if (anchor.blockId) {
      const blockId = anchor.blockId, block = editor.getBlock(blockId);
      if (!block) return false;
      const element = window.document.querySelector(`.cv-document[data-project-id="${CSS.escape(initial.workspace.projectId)}"] [data-id="${CSS.escape(blockId)}"]`);
      if (!element) return false;
      if (anchor.cellId) {
        const cellId = anchor.cellId;
        let position: number | null = null;
        editor.transact(tr => {
          tr.doc.descendants((node, pos) => {
            if (node.type.name !== "blockContainer" || node.attrs["id"] !== blockId) return;
            node.firstChild?.descendants((cell, offset) => {
              if (cell.attrs["foldcvNodeId"] === cellId) position = pos + offset + 4;
            });
          });
          if (position !== null) tr.setSelection(TextSelection.near(tr.doc.resolve(position))).scrollIntoView();
        });
        if (position === null) return false;
      } else editor.setTextCursorPosition(blockId, "start");
      editor.focus(); element.scrollIntoView({ block: "center", behavior: "smooth" }); return true;
    }
    if (!anchor.recordId) return false;
    setFactsVisible(true);
    requestAnimationFrame(() => {
      const element = window.document.querySelector<HTMLElement>(`.rich-fact-row[data-fact-id="${CSS.escape(anchor.recordId ?? "")}"]`);
      const details = element?.closest("details"); if (details) details.open = true;
      element?.scrollIntoView({ block: "center", behavior: "smooth" }); element?.querySelector("button")?.focus();
    });
    return true;
  }, captureSelection: () => captureSelected(bridge.latestSelection), assistantBaseline: async captured => {
    const valid = () => !captured || captured.session === bridge.session && !!bridge.history
      && [...captured.epochs].every(([key, revision]) => bridge.history?.revision(key) === revision);
    if (!valid()) throw new Error("AGENT_STALE_READ");
    const response = await bridge.assistantFlush(), project = response.workspace.project;
    if (!valid() || !project) throw new Error("AGENT_STALE_READ");
    if (!captured) return { response, selection: null };
    const revisions = new Map<string, number>(), blocksById = new Map<string, RichBlock>();
    function visit(blocks: RichBlock[]) { for (const block of blocks) { revisions.set(block.id, block.revision); blocksById.set(block.id, block); visit(block.children); } }
    project.document.regions.forEach(region => visit(region.blocks));
    const dependencies: RichSelection["capture"]["dependencies"] = [];
    for (const id of captured.selection.blockIds) {
      const block = blocksById.get(id);
      if (!block) throw new Error("AGENT_STALE_READ");
      if (block.type === "table" && captured.selection.kind !== "blocks") {
        const cells = block.content.rows.flatMap(row => row.cells);
        const first = id === captured.selection.anchor.blockId ? cells.findIndex(cell => cell.id === captured.selection.anchor.cellId) : 0;
        const last = id === captured.selection.head.blockId ? cells.findIndex(cell => cell.id === captured.selection.head.cellId) : cells.length - 1;
        for (const cell of cells.slice(first, last + 1)) dependencies.push({ kind: "field", id: JSON.stringify(["cell", id, cell.id]), revision: cell.revision, fingerprint: null });
      } else dependencies.push({ kind: "block", id, revision: revisions.get(id) ?? 1, fingerprint: null });
    }
    const selection: RichSelection = { ...captured.selection, textSha256: "0".repeat(64),
      capture: { sessionId: bridge.session, actionId: `${bridge.session}:selection`, actionToken: bridge.history?.revisionClock ?? 0,
        dependencies } };
    selection.textSha256 = await selectionChecksum(project.document, selection);
    if (!valid()) throw new Error("AGENT_STALE_READ");
    return { response, selection };
  }, applyAssistant: async (batchId, api) => {
    if (!bridge.prepared) throw new Error("Редактор ещё открывается");
    await bridge.prepared.apply(batchId, api);
  } }), [bridge]);
  function submitRewrite() {
    setRewriting(true); setRewriteError("");
    void bridge.rewrite(instruction).then(() => setRewriteOpen(false)).catch(error => setRewriteError(error instanceof Error && /stale|устар|обнов|измен/i.test(error.message)
      ? "Документ изменился. Выделите фрагмент и запросите правку заново." : "Не удалось изменить текст. Можно повторить запрос."))
      .finally(() => setRewriting(false));
  }
  function toolbarCommand(command: ToolbarCommand) {
    try {
    if (command === "undo") bridge.undo();
    else if (command === "redo") bridge.redo();
    else if (command === "facts") setFactsVisible(value => !value);
    else if (command === "block") { const target = blockTarget ? null : commandBlock(editor.getTextCursorPosition().block.id, id => editor.getBlock(id)).id; setBlockTarget(target); }
    else if (command === "rewrite") openRewrite();
    else if (command === "image") { imageTarget.current = commandBlock(editor.getTextCursorPosition().block.id, id => editor.getBlock(id)).id; imageInput.current?.click(); }
    else if (command === "link") {
      linkCapture.current = { doc: editor.prosemirrorState.doc, bookmark: editor.prosemirrorState.selection.getBookmark() };
      setLinkText(editor.getSelectedText()); setLinkOpen(true);
    }
    else if (command === "table") {
      const block = commandBlock(editor.getTextCursorPosition().block.id, id => editor.getBlock(id));
      setTableTarget(block.id);
    } else if (command === "list") {
      const block = commandBlock(editor.getTextCursorPosition().block.id, id => editor.getBlock(id));
      if (block.type !== "table" && block.type !== "image") editor.updateBlock(block, { type: "bulletListItem" });
      bridge.complete(); editor.focus();
    } else { editor.toggleStyles({ [command]: true }); bridge.complete(); editor.focus(); }
    } catch (error) { setEditorWarning(error instanceof Error ? error.message : "Не удалось выполнить действие"); }
  }
  return <EditorActions.Provider value={{ addText: id => {
    const target = editor.getBlock(id);
    if (!target || target.type !== "region" || target.children.length) return;
    bridge.kind = "structure";
    const updated = editor.updateBlock(id, { children: [{ type: "paragraph", content: "" }] });
    const child = updated.children[0]; if (child) editor.setTextCursorPosition(child.id, "start");
    bridge.complete(); editor.focus();
  } }}><ImageActions.Provider value={{ source: asset => imageSource(initial.workspace.projectId, asset), upload: assets.upload, cancel: assets.cancel }}>
    <><RewritePanel open={rewriteOpen} close={() => setRewriteOpen(false)} instruction={instruction} change={setInstruction}
      submit={submitRewrite} busy={rewriting} source={rewriteSource} error={rewriteError} />
      {linkOpen && <LinkDialog open selectedText={linkText} close={() => { setLinkOpen(false); editor.focus(); }} apply={(href, text) => {
        const capture = linkCapture.current;
        if (!capture || capture.doc !== editor.prosemirrorState.doc) { setEditorWarning("Документ изменился. Выделите текст и добавьте ссылку заново."); return; }
        editor.transact(tr => { tr.setSelection(capture.bookmark.resolve(tr.doc)); });
        editor.createLink(href, text === linkText ? undefined : text); bridge.complete();
      }} />}
      {sourceOpen && <SourceDialog sources={project.sources} close={() => setSourceOpen(false)} />}
      {tableTarget && <TableDialog close={() => { setTableTarget(null); editor.focus(); }} apply={(rows, columns) => {
        try {
          const target = commandBlock(tableTarget, id => editor.getBlock(id));
          const inserted = editor.insertBlocks([{ type: "table", content: { type: "tableContent", rows: Array.from({ length: rows }, () => ({ cells: Array.from({ length: columns }, () => "") })) } }], target, "after");
          const table = inserted[0]; if (table) editor.setTextCursorPosition(table.id, "start");
          bridge.complete(); setTableTarget(null); editor.focus();
        } catch (error) { setTableTarget(null); setEditorWarning(error instanceof Error ? error.message : "Не удалось вставить таблицу"); }
      }} />}</>
    {applying && <p role="status">Сохраняю правки помощника…</p>}
    {(writerMode === "recovering" || writerMode === "read_only") && <div role="alert" className="notice error">
      <p>{writerMode === "read_only" ? "Не удалось восстановить редактор. Редактирование приостановлено. Выберите состояние для продолжения."
        : "Ввод сохранён в отдельном черновике. Сначала выберите, какое состояние продолжить."}</p>
      {(writerMode === "recovering" || writerConnection?.local) && <button type="button" onClick={() => void bridge.writer?.resolveDraft("draft").then(() => location.reload())
        .catch(error => setEditorWarning(error instanceof Error ? error.message : "DRAFT_RECOVERY_FAILED"))}>Использовать мой черновик</button>}
      <button type="button" onClick={() => void bridge.writer?.resolveDraft("saved").then(() => location.reload())
        .catch(error => setEditorWarning(error instanceof Error ? error.message : "DRAFT_RECOVERY_FAILED"))}>Продолжить с сохранённого состояния</button>
      <p>Продолжение с сохранённого состояния удалит доступный черновик. Невосстановленные правки могут быть потеряны.</p>
    </div>}
    <div className="contents uir-editor-session">
    <fieldset className="contents uir-editor-controls" disabled={applying || recovery || writerMode === "read_only" || writerMode === "detached"}>
    <><Toolbar command={toolbarCommand} factsVisible={factsVisible} blockVisible={blockTarget !== null}
      canUndo={!factIntents.pending.length && (bridge.history?.position ?? 0) > 0} canRedo={!factIntents.pending.length && (bridge.history?.position ?? 0) < (bridge.history?.length ?? 0)} selecting={selecting}
      active={{ bold: editor.getActiveStyles().bold === true, italic: editor.getActiveStyles().italic === true, underline: editor.getActiveStyles().underline === true }}
      style={(() => { const block = editor.getTextCursorPosition().block; return block.type === "heading" && block.props.level === 2 ? "h2" : block.type === "heading" && block.props.level === 3 ? "h3" : block.type === "quote" ? "blockquote" : "p"; })()}
      textStyle={style => {
        try {
        const block = commandBlock(editor.getTextCursorPosition().block.id, id => editor.getBlock(id));
        if (block.type === "table" || block.type === "image") return;
        if (style === "h2" || style === "h3") editor.updateBlock(block, { type: "heading", props: { level: style === "h2" ? 2 : 3 } });
        else editor.updateBlock(block, { type: style === "blockquote" ? "quote" : "paragraph" });
        bridge.complete(); editor.focus();
        } catch (error) { setEditorWarning(error instanceof Error ? error.message : "Не удалось изменить стиль"); }
      }} />
      <input hidden ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp" aria-label="Файл изображения"
        onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) void assets.upload(file, undefined, imageTarget.current).catch(error => setEditorWarning(error instanceof Error ? error.message : "Не удалось добавить изображение")); }} /></>
    </fieldset>
    <div className="editor-body uir-editor-body">
    <fieldset className="contents uir-editor-controls" disabled={applying || recovery || writerMode === "read_only" || writerMode === "detached"}>
    <FactsPanel facts={facts} submit={command => bridge.panel(command)} hidden={!factsVisible} close={() => { setFactsVisible(false); editor.focus(); }}
      pending={factIntents.pending.flatMap(intent => intent.kind === "panel" ? [intent.command] : [])} paused={factIntents.paused}
      timeline={ready ? <Timeline facts={facts} anchors={anchors} controls={timelineControls} /> : null} />
    </fieldset>
    <div className="document-workspace">
    <fieldset className="contents uir-editor-controls" disabled={applying || recovery}>
    <div className="document-context"><div className="context-left"><span>Исходный текст</span><span>Шаблон FoldCV</span></div>{contextActions}</div>
    <div className="paper-scroll">
    <div className="cv-document resume-paper uir-prototype" data-project-id={initial.workspace.projectId}
      data-history-position={bridge.history?.position ?? 0} data-history-length={bridge.history?.length ?? 0} data-composing={bridge.composing}>
      {editorWarning && <p role="alert" className="cv-editor-warning">{editorWarning}<button className="text-button" onClick={() => setEditorWarning("")}>Закрыть</button></p>}
      {syncRecords.filter(record => ["failed", "conflict", "pending", "stale"].includes(record.status)).map(record => <p key={record.id} className="cv-editor-warning" role="status">
        {record.status === "failed" ? "Не удалось проверить изменения. Повторите проверку." : record.status === "conflict" ? "Есть другие упоминания. Проверьте связанные факты." : record.status === "stale" ? "Предложение устарело. Ваши изменения сохранены." : record.errorCode === "OPERATION_INTERRUPTED" ? "Синхронизация была прервана." : "Синхронизация…"}
        {record.status === "conflict" && <button className="text-button" onClick={() => void bridge.resolve(record.id).catch(error => setEditorWarning(error instanceof Error ? error.message : "Не удалось обновить"))}>Обновить связанные поля</button>}
        <button className="text-button" onClick={() => void bridge.retry(record.id).catch(error => setEditorWarning(error instanceof Error ? error.message : "Не удалось повторить"))}>Повторить</button>
        <button className="text-button" onClick={() => void projectRequest(`/${initial.workspace.projectId}/sync/${record.id}`, "POST", { status: "stale" }).then(response => setSyncRecords(response.workspace.syncRecords))}>Закрыть</button>
      </p>)}
      <div className="paper-kicker"><span>РЕЗЮМЕ СПЕЦИАЛИСТА</span><span>F / РЕЗЮМЕ</span></div>
      <div className="uir-engine-sheet"><span className="template-wordmark" aria-label="generic">generic</span>
      <BlockNoteView editor={editor} theme="light" linkToolbar={!selecting} filePanel={false} slashMenu={false} formattingToolbar={false} sideMenu={false}
        {...(portalHost ? { portalElements: { default: portalHost } } : {})}>
        <FormattingToolbarController formattingToolbar={selectionToolbar} portalElement={portalHost ?? window.document.body}
          floatingUIOptions={selectionFloating} />
        <SideMenuController sideMenu={blockSideMenu} portalElement={portalHost ?? window.document.body} />
        <SuggestionMenuController triggerCharacter="/" getItems={async query => [...getDefaultReactSlashMenuItems(editor),
          { title: "Изображение", subtext: "Локальный PNG, JPEG или WebP", aliases: ["image", "photo"], group: "Media", onItemClick: () => imageInput.current?.click() }]
          .filter(item => `${item.title} ${item.aliases?.join(" ") ?? ""}`.toLowerCase().includes(query.toLowerCase()))} />
      </BlockNoteView>
      </div>
      <footer className="paper-footer"><span>mail@example.com</span><span>FoldCV</span></footer>
    </div></div>
    <footer className="editor-footer"><span>Исходный текст</span><button onClick={() => setSourceOpen(true)}><Icon name="file" />Исходник</button></footer>
    </fieldset>
    {(assistant ?? <div className="uir-chat-reservation" aria-hidden="true" />)}
    </div>
    <fieldset className="contents uir-editor-controls" disabled={applying || recovery}>
    {blockTarget && (<BlockPanel id={blockTarget} available={!!editor.getBlock(blockTarget)} text={(() => {
      const key = bridge.current.get(`block:${blockTarget}`), block = key ? bridge.values.get(key)?.block : null;
      return typeof block?.content === "string" ? block.content : Array.isArray(block?.content) ? block.content.map(span => span.type === "link" ? span.content.map(part => part.text).join("") : span.text).join("") : "";
    })()} close={() => { setBlockTarget(null); editor.focus(); }} command={(command, target) => assets.command(blockTarget, command, target)} destinations={targets} />)}
    </fieldset>
    </div>
    </div>
  </ImageActions.Provider></EditorActions.Provider>;
}
