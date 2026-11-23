import { createExtension } from "@blocknote/core";
import { Extension } from "@tiptap/core";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { ProjectApiFailure, type ProjectEditorConnection } from "./v7-connection";
import type { TemplateProjectResponseV1 } from "../contracts/generated/contracts";
import type { AssistantApplyResultV1 } from "../contracts/generated/contracts";
import type { AssistantFinding, AssistantSelection } from "../assistant/controller";
import { errorMessage, knownErrorMessage } from "../errors/messages";
import { ComparisonWorkspace, WorkspaceViews, type WorkspaceView } from "../workbench/editor/ComparisonWorkspace";
import { unshownLines, withChanged, type ChangedLine } from "../workbench/editor/unshown";
import { SourceDialog } from "../workbench/editor/SourceDialog";
import type { PaneOrder } from "../workbench/settings/interface";
import { BlockedInputNotice } from "../workbench/editor/BlockedInputNotice";
import { EditorNotices } from "../workbench/editor/EditorNotices";
import { FactsPanel } from "../workbench/facts/FactsPanel";
import { RewritePanel } from "../workbench/editor/RewritePanel";
import { RemarkTip } from "../workbench/editor/RemarkTip";
import { SelectionAction } from "../workbench/editor/SelectionAction";
import { RefusalNotice, type Refusal } from "../workbench/editor/RefusalNotice";
import { ContextMenu } from "../workbench/editor/ContextMenu";
import { menuItems, type MenuItem } from "../workbench/editor/context-menu";
import { AllSelection, TextSelection, type Selection } from "@tiptap/pm/state";
import { refusalDue } from "../workbench/editor/refusal-notice";
import { LinkTargetDialog } from "../workbench/editor/LinkTargetDialog";
import { BlockRewordButton, BlockRewritePanel } from "../workbench/editor/BlockReword";
import { rewordTarget, type RewordChange, type RewordPreview } from "../workbench/editor/reword";
import { RewriteRequests, type RewriteActivity } from "./rewrite-progress";
import type { PanelCommand } from "./v7-panel";
import { Toolbar, type ToolbarCommand } from "../workbench/editor/Toolbar";
import { parseZoom, readZoom, saveZoom, useFittedZoom, zoomLevels } from "../workbench/editor/document-zoom";
import { PanelHandle, readPanelSize, savePanelSize } from "../workbench/ui/PanelHandle";
import { blockStyle, selectionLocation, type BlockStyle } from "./selection";
import { markable, technologyBlock } from "./v7-extraction";
import { tableIdentityAttributes } from "./table-identity";
import { disabledExtensions, templateDictionary, templateSchema } from "./template-schema";
import { projectTemplateDocument } from "./v7-projection";
import { focusFacts } from "./v7-focus";
import { focusIconChoices } from "../projects/api";
import { remarkMarks, remarkMarksMeta, remarkMarksPlugin, type RemarkMarks } from "./remarks";
import { listIndexPlugin } from "./list-index";
import { listEndsPlugin } from "./list-ends";
import { technologyLockPlugin } from "./technology-lock";
import { groupAnchors } from "./outline";
import { readRemarkMarks, saveRemarkMarks } from "../workbench/settings/interface";
import { presentationMeta, templatePresentationPlugin, templateSheet, type TemplateSheet } from "./v7-presentation";
import { TemplateEditorSession, type TemplateRewrite, type EditorMode } from "./v7-session";
import { printCopy, printCopyNow, removePrintCopy } from "../workbench/files/print";

export type TemplateEditorHandle = { background: boolean; flush: () => Promise<TemplateProjectResponseV1>;
  navigate: () => Promise<void>; resume: () => Promise<void>; refresh: () => Promise<void>; undo: () => void; redo: () => void;
  /** PDF export: the shown sheet through the system print window; the title names the saved file. */
  print: (title: string) => Promise<void>;
  /** The assistant drawer's bridge: Apply through this page's token, the selection as run context, and a finding's place. */
  applyAssistant: (proposalId: string, allowEdits: boolean) => Promise<AssistantApplyResultV1>;
  captureSelection: () => AssistantSelection | null;
  focusFinding: (anchor: AssistantFinding["anchors"][number]) => boolean };
type ShownBlock = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>["document"]["regions"][number]["blocks"][number];
const factsWidths = { fallback: 300, minimum: 240, maximum: 560 };
const noBlocks: ReadonlySet<string> = new Set();

function blockRevisions(response: TemplateProjectResponseV1): Map<string, number> {
  const revisions = new Map<string, number>();
  const visit = (blocks: readonly ShownBlock[]) => { for (const block of blocks) { revisions.set(block.id, block.revision); visit(block.children); } };
  response.workspace.project?.document.regions.forEach(region => visit(region.blocks));
  return revisions;
}

/** The V7 editor: the same BlockNote view and controls, bound to one TemplateEditorSession. */
export function TemplateEditor({ initial, connection, onStatus, onShown, ref, portalHost, assistant, paneOrder }: {
  initial: TemplateProjectResponseV1; connection: ProjectEditorConnection; onStatus: (status: string) => void;
  onShown: (response: TemplateProjectResponseV1) => void; ref: Ref<TemplateEditorHandle>; portalHost?: HTMLElement; assistant?: ReactNode; paneOrder: PaneOrder }) {
  const project = initial.workspace.project;
  if (!project) throw new Error("Document is missing");
  const [warning, setWarning] = useState("");
  // A refused input is said at the text; the same text stays quiet for 3 s.
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const lastRefusal = useRef<{ text: string; at: number } | null>(null);
  const refuseAtText = useRef<(text: string) => void>(text => setWarning(text));
  const refusalDone = useCallback((id: number) => setRefusal(value => value?.id === id ? null : value), []);
  const [mode, setMode] = useState<EditorMode | null>(null);
  const [recovering, setRecovering] = useState(false), [formatting, setFormatting] = useState(false);
  const recoveryRunning = useRef(false);
  // The verified state shown in the editor: facts and issues are read from it, never from editor content.
  const [shown, setShown] = useState(initial);
  const [factsVisible, setFactsVisible] = useState(false);
  const [factsWidth, setFactsWidth] = useState(() => readPanelSize("facts", factsWidths.minimum, factsWidths.maximum) ?? factsWidths.fallback);
  function changeFactsWidth(value: number | null) { setFactsWidth(value ?? factsWidths.fallback); savePanelSize("facts", value); }
  const [zoomChoice, setZoomChoice] = useState(readZoom);
  const paperScroll = useRef<HTMLDivElement>(null);
  // The fact row a finding points at, until the panel has shown it.
  const [factFocus, setFactFocus] = useState<{ recordId: string } | null>(null);
  const factFocused = useCallback(() => setFactFocus(null), []);
  // Blocks an assistant Apply changed, marked for a moment so the user sees where the edit landed.
  const [changed, setChanged] = useState<{ blockIds: string[]; at: number } | null>(null);
  useEffect(() => {
    if (!changed) return;
    const timer = setTimeout(() => setChanged(null), 3000);
    return () => clearTimeout(timer);
  }, [changed]);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("layout");
  // While the pointer drags a selection the action beside it waits, or it would sit under the pointer.
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const down = (event: PointerEvent) => { if (paperScroll.current?.contains(event.target instanceof Node ? event.target : null)) setDragging(true); };
    const up = () => setDragging(false);
    document.addEventListener("pointerdown", down); document.addEventListener("pointerup", up); document.addEventListener("pointercancel", up);
    return () => { document.removeEventListener("pointerdown", down); document.removeEventListener("pointerup", up); document.removeEventListener("pointercancel", up); };
  }, []);
  const [sourceVisited, setSourceVisited] = useState(false);
  const [panelPending, setPanelPending] = useState<PanelCommand[]>([]);
  const [, refresh] = useState(0);
  // Selected-text rewrite: one preview at a time; nothing changes until Apply.
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const instructionNow = useRef(instruction), rewriteTarget = useRef("");
  instructionNow.current = instruction;
  const [rewriteSource, setRewriteSource] = useState("");
  const [rewritePreview, setRewritePreview] = useState<TemplateRewrite | null>(null);
  const [rewriteText, setRewriteText] = useState("");
  const [rewriteError, setRewriteError] = useState("");
  const [rewriteActivity, setRewriteActivity] = useState<RewriteActivity | null>(null);
  const [rewriteAnchor, setRewriteAnchor] = useState<{ left: number; top: number; bottom: number } | null>(null);
  // A bound link's URL is edited through Python, which changes its URL cell and target together.
  const [linkTarget, setLinkTarget] = useState<{ blockId: string; occurrenceId: string; href: string } | null>(null);
  // A whole block reworded by the template's rules, in the same panel: one preview at a time, the facts change only
  // through its Apply.
  const [rewordRules, setRewordRules] = useState<Readonly<Record<string, string>>>({});
  const rewordIds = useMemo<ReadonlySet<string>>(() => new Set(Object.keys(rewordRules)), [rewordRules]);
  // The words each shown field has beyond its source lines, by cell ID; marked green while the marks are on.
  const [beyond, setBeyond] = useState<ReadonlyMap<string, readonly string[]>>(new Map());
  // The source lines of shown values with the words the document no longer shows; marked red in the original.
  const [changedLines, setChangedLines] = useState<readonly ChangedLine[]>([]);
  const [rewordOpen, setRewordOpen] = useState(false), rewordBlock = useRef(""), [rewordShown, setRewordShown] = useState("");
  const [rewordInstruction, setRewordInstruction] = useState(""), rewordInstructionNow = useRef("");
  rewordInstructionNow.current = rewordInstruction;
  const [rewordPreview, setRewordPreview] = useState<RewordPreview | null>(null);
  const [rewordError, setRewordError] = useState("");
  const [rewordActivity, setRewordActivity] = useState<RewriteActivity | null>(null);
  const [rewordAnchor, setRewordAnchor] = useState<{ left: number; top: number; bottom: number } | null>(null);
  const callbacks = useRef({ onStatus, onShown });
  callbacks.current = { onStatus, onShown };
  // The compiled presentation of the verified state; decorations read the latest one.
  const sheet = useMemo(() => templateSheet(shown), [shown]);
  // The page is drawn in points; CSS pixels are 96 to 72 of them.
  const fitted = useFittedZoom(paperScroll, (sheet?.presentation.recipe.style.page.width ?? 596) * 96 / 72);
  const zoom = zoomChoice === "fit" ? fitted : zoomChoice;
  const presented = useRef<TemplateSheet | null>(sheet);
  presented.current = sheet;
  const presentation = useMemo(() => templatePresentationPlugin(() => presented.current), []);
  // Remarks and doubtful values of the verified state, marked in the text while the switch is on.
  const marks = useMemo(() => {
    const value = shown.workspace.project;
    return value ? { ...remarkMarks(value.document, value.importIssues, value.facts), beyond } : null;
  }, [shown, beyond]);
  const [marking, setMarking] = useState(readRemarkMarks);
  // The lines of the original the resume does not show, marked in the original while the same switch is on.
  // The same lines keep the same array, so the original is not read and marked again after every saved edit.
  const unshownHeld = useRef<ReturnType<typeof withChanged>>([]);
  const unshown = useMemo(() => {
    const next = marking ? withChanged(unshownLines(shown.workspace.project?.importIssues ?? []), changedLines) : [];
    if (JSON.stringify(next) !== JSON.stringify(unshownHeld.current)) unshownHeld.current = next;
    return unshownHeld.current;
  }, [shown, marking, changedLines]);
  // The blocks the template lets a model reword and the words beyond the original, read again when the saved state
  // changes (a fact edited in the panel changes the page too).
  const savedRevision = shown.workspace.projectRevision;
  useEffect(() => {
    let live = true;
    void connection.rewordBlocks().then(rules => { if (live) setRewordRules(rules); }, () => { if (live) setRewordRules({}); });
    void connection.sourceDiff().then(diff => { if (live) { setBeyond(new Map(Object.entries(diff.added))); setChangedLines(diff.removed); } },
      () => { if (live) { setBeyond(new Map()); setChangedLines([]); } });
    return () => { live = false; };
  }, [connection, savedRevision]);
  const marked = useRef<RemarkMarks | null>(null);
  marked.current = marking ? marks : null;
  const remarkPlugin = useMemo(() => remarkMarksPlugin(() => marked.current), []);
  const listIndex = useMemo(() => listIndexPlugin(), []);
  const listEnds = useMemo(() => listEndsPlugin(), []);
  // Technologies change only in Facts: a click on one in the page opens its row there.
  const technologyLock = useMemo(() => technologyLockPlugin(recordId => { setFactsVisible(true); setFactFocus({ recordId }); }), []);
  const session = useMemo(() => new TemplateEditorSession(connection, {
    status: text => { callbacks.current.onStatus(text); refresh(value => value + 1); },
    // A repeated text still re-renders: the undo buttons follow the history a refused step brought back.
    warning: text => { setWarning(text); refresh(value => value + 1); },
    mode: value => setMode(value),
    shown: response => { setShown(response); callbacks.current.onShown(response); refresh(value => value + 1); },
    refused: text => refuseAtText.current(text),
  }), [connection]);
  // Copy, cut and paste must run before BlockNote's own clipboard handlers, which would otherwise end the event.
  const extension = useMemo(() => createExtension({ key: "foldcv-v7-session", runsBefore: ["link"], tiptapExtensions: [tableIdentityAttributes,
    Extension.create({ name: "foldcv-v7-clipboard", priority: 1000, addProseMirrorPlugins: () => [session.clipboard] })],
    prosemirrorPlugins: [session.plugin, presentation, remarkPlugin, listIndex, listEnds, technologyLock] }), [session, presentation, remarkPlugin, listIndex, listEnds, technologyLock]);
  const editor = useCreateBlockNote({ schema: templateSchema, extensions: [extension],
    disableExtensions: disabledExtensions, dictionary: templateDictionary,
    tables: { splitCells: true, cellBackgroundColor: true, cellTextColor: true, headers: true },
    initialContent: projectTemplateDocument(project.document) }, []);
  useEffect(() => {
    refuseAtText.current = text => {
      const now = Date.now();
      if (!refusalDue(lastRefusal.current, text, now)) return;
      lastRefusal.current = { text, at: now };
      const view = editor._tiptapEditor.view;
      let line: { left: number; top: number; right: number; bottom: number } | null = null;
      try { const at = view.coordsAtPos(view.state.selection.from); line = { left: at.left, top: at.top, right: at.right, bottom: at.bottom }; }
      catch { line = null; }
      // With no place in the page (the page is not shown), the notice area says it.
      if (!line) { setWarning(text); return; }
      setRefusal({ id: now, text, line });
    };
  }, [editor]);
  useEffect(() => {
    session.bind(editor, project.document);
    const stop = editor.onSelectionChange(() => { session.selected(editor.transact(tr => selectionLocation(tr))); refresh(value => value + 1); });
    return () => { stop(); session.close(); };
  }, [editor, session]);
  useEffect(() => {
    presented.current = sheet;
    editor.transact(tr => { tr.setMeta(presentationMeta, true); });
  }, [editor, sheet]);
  useEffect(() => { editor.transact(tr => { tr.setMeta(remarkMarksMeta, true); }); }, [editor, marks, marking]);
  // The print copy and what it was made from. A print the browser starts itself (its menu or ⌘P) gets a new copy when the
  // text or the presentation changed since; the copy stays until then, as the macOS window prints after window.print returns.
  const printed = useRef<{ doc: unknown; sheet: TemplateSheet | null } | null>(null);
  const printSource = useCallback(() => {
    const paper = paperScroll.current?.querySelector<HTMLElement>(".resume-paper"), page = presented.current?.presentation.recipe.style.page;
    return paper && page ? { paper, page: { ...page, footer_bottom: presented.current?.footer?.bottom ?? null } } : null;
  }, []);
  useEffect(() => {
    const title = document.title;
    const prepare = () => {
      const source = printSource(), doc = editor._tiptapEditor.state.doc, last = printed.current;
      if (!source || (last?.doc === doc && last.sheet === presented.current && document.querySelector("body > .print-root"))) return;
      printCopyNow(source.paper, source.page);
      printed.current = { doc, sheet: presented.current };
    };
    const restore = () => { document.title = title; };
    addEventListener("beforeprint", prepare); addEventListener("afterprint", restore);
    return () => { removeEventListener("beforeprint", prepare); removeEventListener("afterprint", restore); removePrintCopy(); restore(); };
  }, [editor, printSource]);
  useImperativeHandle(ref, () => ({ background: true,
    flush: async () => {
      await session.flush();
      return session.queue.template.durable;
    },
    navigate: () => session.navigateAway(), resume: () => session.resume(), refresh: () => session.refresh(),
    undo: () => void session.navigate("undo"), redo: () => void session.navigate("redo"),
    print: async title => {
      await session.flush();
      const source = printSource(), doc = editor._tiptapEditor.state.doc;
      if (!source) throw new Error("Не удалось подготовить резюме к печати.");
      await printCopy(source.paper, source.page);
      printed.current = { doc, sheet: presented.current };
      // The print window names the PDF after the page title; it returns to the app's own after the print.
      document.title = title;
      try {
        // Tauri's window.print asks the shell and answers with a promise; a browser's returns when its window closes.
        const started: unknown = window.print();
        if (started instanceof Promise) await started;
      } catch { throw new Error("Не удалось открыть окно печати."); }
    },
    applyAssistant: async (proposalId, allowEdits) => {
      const result = await session.applyAssistant(proposalId, allowEdits);
      showChanges(result.edit?.changedBlockIds ?? []);
      return result;
    },
    captureSelection: () => {
      const selected = editor.getSelection(), text = window.getSelection()?.toString().trim() ?? "";
      if (!selected?.blocks.length || !text) return null;
      return { blockIds: selected.blocks.slice(0, 100).map(block => block.id), text: text.slice(0, 4000) };
    },
    focusFinding: anchor => {
      // A finding points at the state the run read; a block or fact changed since then is reported, not guessed.
      const durable = session.queue.template.durable, revisions = blockRevisions(durable);
      const records = new Map((durable.workspace.project?.facts.records ?? []).map(record => [record.id, record.revision]));
      if (!anchor.dependencies.every(stamp => stamp.kind === "block" ? revisions.get(stamp.id) === stamp.revision
        : stamp.kind !== "record" || records.get(stamp.id) === stamp.revision)) return false;
      if (anchor.blockId) return showBlock(anchor.blockId);
      if (!anchor.recordId || !records.has(anchor.recordId)) return false;
      setFactsVisible(true);
      setFactFocus({ recordId: anchor.recordId });
      return true;
    } }), [session, editor]);
  async function recover() {
    if (recoveryRunning.current) return;
    recoveryRunning.current = true; setRecovering(true);
    try { await session.recoverDraft(); }
    catch (error) { setWarning(errorMessage(error)); }
    finally { recoveryRunning.current = false; setRecovering(false); }
  }
  useEffect(() => { if (mode === "recovering") void recover(); }, [mode]);
  const unsupported = () => setWarning(knownErrorMessage("V7_INPUT_UNSUPPORTED") ?? "");
  function showChanges(blockIds: readonly string[]) {
    const shown = blockIds.filter(id => editor.getBlock(id)), first = shown[0];
    if (first === undefined) return;
    document.querySelector(`.cv-document [data-id="${CSS.escape(first)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    setChanged({ blockIds: shown, at: Date.now() });
  }
  function showBlock(blockId: string, at: ScrollLogicalPosition = "center"): boolean {
    if (!editor.getBlock(blockId)) return false;
    // A block without text (an item frame) cannot hold the caret; it is still scrolled to.
    try { editor.setTextCursorPosition(blockId, "start"); editor.focus(); } catch { /* scroll only */ }
    document.querySelector(`.cv-document [data-id="${CSS.escape(blockId)}"]`)?.scrollIntoView({ block: at, behavior: "smooth" });
    return true;
  }
  function formatBlocks(style: BlockStyle) {
    // The style select keeps focus after a choice; the caret goes back to the document once Python's result is shown.
    setFormatting(true);
    void session.format(style).then(() => { if (editor.isEditable) editor.focus(); }).finally(() => setFormatting(false));
  }
  const rewrites = useMemo(() => new RewriteRequests<TemplateRewrite>({
    preview: (requestId, stage) => session.rewritePreview(instructionNow.current, requestId, stage),
    cancel: requestId => session.cancelRewrite(requestId), activity: setRewriteActivity,
    done: preview => { setRewritePreview(preview); setRewriteText(preview.text); setRewriteSource(preview.source); },
    failed: setRewriteError, cancelFailed: error => setWarning(errorMessage(error)),
  }), [session]);
  /** Where the selection ends on screen, for the action beside it; null while the editor has no view yet. */
  function selectionEnd(): { left: number; top: number; bottom: number } | null {
    try {
      const view = editor._tiptapEditor.view, coords = view.coordsAtPos(view.state.selection.to);
      return { left: coords.left, top: coords.top, bottom: coords.bottom };
    } catch { return null; }
  }
  function openRewrite() {
    const source = session.rewriteSource();
    if (!source) { unsupported(); return; }
    const view = editor._tiptapEditor.view, coords = view.coordsAtPos(view.state.selection.from);
    setRewriteAnchor({ left: coords.left, top: coords.top, bottom: coords.bottom });
    // A panel hidden during a request reopens on it; another selection replaces it.
    const target = JSON.stringify([source.container, source.start, source.end]);
    if (rewrites.running && target === rewriteTarget.current) { setRewriteOpen(true); return; }
    rewriteTarget.current = target;
    rewrites.supersede();
    setRewriteSource(source.text); setRewritePreview(null); setRewriteText(""); setRewriteError(""); setRewriteOpen(true);
  }
  function submitRewrite() { setRewriteError(""); void rewrites.submit(); }
  async function applyRewrite() {
    if (!rewritePreview) return;
    setRewriteActivity({ actionId: rewritePreview.requestId, stage: "applying", startedAt: Date.now(), finishedAt: null, detail: null });
    try { await session.applyRewrite(rewritePreview, rewriteText); setRewriteOpen(false); setRewritePreview(null); editor.focus(); }
    catch (error) { setRewriteError(error instanceof Error ? error.message : "INVALID_RESULT"); }
    finally { setRewriteActivity(null); }
  }
  const command = (value: ToolbarCommand) => {
    if (value === "undo" || value === "redo") { void session.navigate(value); return; }
    if (value === "rewrite") {
      const block = session.rewriteSource() === null ? caretBlock() : null;
      if (block) openReword(block); else { setRewordOpen(false); openRewrite(); }
      return;
    }
    if (value === "bold" || value === "italic" || value === "underline") { editor.toggleStyles({ [value]: true }); editor.focus(); return; }
    if (value === "facts") { setFactsVisible(visible => !visible); return; }
    if (value === "remarks") { saveRemarkMarks(!marking); setMarking(!marking); return; }
    formatBlocks(value);
  };
  // Links are no longer inserted from the toolbar; ⌘K on an existing bound link still edits its address.
  function linkShortcut(event: KeyboardEvent) {
    if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k" || event.shiftKey || event.altKey) return;
    const link = session.linkAtCaret();
    if (!link) return;
    event.preventDefault(); event.stopPropagation(); setLinkTarget(link);
  }
  const rewords = useMemo(() => new RewriteRequests<RewordPreview>({
    preview: (requestId, stage) => session.rewordPreview(requestId, rewordBlock.current, rewordInstructionNow.current, stage),
    cancel: requestId => session.cancelRewrite(requestId), activity: setRewordActivity,
    done: setRewordPreview, failed: setRewordError, cancelFailed: error => setWarning(errorMessage(error)),
  }), [session]);
  /** The block the caret stands in that the template lets a model reword; null when there is none. */
  function caretBlock(): string | null {
    try {
      const id = editor.getTextCursorPosition().block.id;
      return rewordTarget(document.querySelector(`.cv-document [data-id="${CSS.escape(id)}"]`), rewordIds)?.getAttribute("data-id") ?? null;
    } catch { return null; }
  }
  function openReword(blockId: string) {
    const rect = document.querySelector(`.cv-document [data-id="${CSS.escape(blockId)}"]`)?.getBoundingClientRect();
    // Beside the block's first line, to the right of it while the window has the room.
    setRewordAnchor(rect ? { left: rect.right + 12, top: rect.top + 28, bottom: rect.top - 8 } : null);
    setRewriteOpen(false);
    // A panel hidden during a request or with a preview reopens on it; another block replaces it.
    if ((rewords.running || rewordPreview) && blockId === rewordBlock.current) { setRewordOpen(true); return; }
    rewordBlock.current = blockId;
    // The request starts as the unified rules of this kind of block, in the field where the user reads and edits them;
    // their own text stays.
    const typed = rewordInstructionNow.current;
    if (!typed.trim() || Object.values(rewordRules).includes(typed)) setRewordInstruction(rewordRules[blockId] ?? "");
    rewords.supersede();
    setRewordShown(blockId); setRewordPreview(null); setRewordError(""); setRewordOpen(true);
  }
  function submitReword() { setRewordError(""); void rewords.submit(); }
  async function applyReword(changes: RewordChange[]) {
    if (!rewordPreview || changes.length === 0) return;
    setRewordError("");
    setRewordActivity({ actionId: rewordPreview.requestId, stage: "applying", startedAt: Date.now(), finishedAt: null, detail: null });
    try {
      const result = await session.applyReword(rewordBlock.current, changes, rewordPreview.touched);
      setRewordOpen(false); setRewordPreview(null); editor.focus();
      showChanges(result.changedBlockIds);
    } catch (error) { setRewordError(error instanceof ProjectApiFailure ? error.code : error instanceof Error ? error.message : "INVALID_RESULT"); }
    finally { setRewordActivity(null); }
  }
  async function applyLinkTarget(target: { blockId: string; occurrenceId: string }, href: string) {
    try { await session.linkTarget(target, href); }
    catch (error) { setWarning(errorMessage(error)); }
  }
  async function submitPanel(value: PanelCommand) {
    setPanelPending(list => [...list, value]);
    try { await session.panel(value); }
    // The facts panel shows a refusal itself; other errors also reach the editor notices.
    catch (error) { if (!(error instanceof ProjectApiFailure && error.status === 422)) setWarning(errorMessage(error)); throw error; }
    finally { setPanelPending(list => list.filter(item => item !== value)); }
  }
  const facts = shown.workspace.project?.facts ?? project.facts, documentShown = shown.workspace.project?.document ?? project.document;
  const sources = (shown.workspace.project?.sources ?? project.sources).map(source => ({
    id: source.id, originalName: source.originalName, byteSha256: source.byteSha256 }));
  function changeWorkspaceView(view: WorkspaceView) {
    setWorkspaceView(view);
    if (view !== "layout") setSourceVisited(true);
  }
  const state = session.queue.template.state, styles = editor.getActiveStyles(), textBlocks = session.textBlocks();
  const listed = (type: string) => textBlocks.length > 0 && textBlocks.every(block => block.type === type);
  const plan = shown.presentation?.editor;
  const heavier = textBlocks.length === 0 || textBlocks.some(block => {
    const entry = plan?.blocks[block.id], faces = entry && plan?.styles[entry.style]?.faces;
    return !faces || faces.bold !== faces.regular;
  });
  // Selection changes re-render the editor; Focus and the group anchors are read again only when the shown state changes.
  const focus = useMemo(() => shown.workspace.project ? focusFacts(shown.workspace.project, shown.presentation)
    : { entries: [], options: [], only: new Set<string>(), icons: false }, [shown]);
  const projectId = initial.workspace.projectId;
  const loadIcons = useCallback(() => focusIconChoices(projectId), [projectId]);
  const anchors = useMemo(() => groupAnchors(documentShown, new Map(facts.records.map(record => [record.id, record.kind]))),
    [documentShown, facts]);
  const locked = mode === "read_only" || mode === "detached" || mode === "recovering";
  // The page's own context menu (F5): it opens at the pointer or, from the keyboard, at the caret; items that cannot run
  // are not shown, and with none nothing opens.
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null), [menuList, setMenuList] = useState<MenuItem[]>([]);
  const [pasteHint, setPasteHint] = useState<string | null>(null);
  const menuBlock = useRef<string | null>(null), rightPress = useRef<Selection | null>(null);
  function openMenu(x: number, y: number, block: string | null) {
    const { selection, cuttable } = session.menuSelection();
    const items = menuItems({ selection, cuttable, editable: session.writable && !locked, rewritable: session.rewriteSource() !== null,
      rewordable: caretBlock() !== null, block });
    menuBlock.current = block; setPasteHint(null);
    setMenuList(items); setMenuAt(items.length ? { x, y } : null);
  }
  function textBlockAt(target: EventTarget | null): string | null {
    const container = target instanceof Element ? target.closest(".cv-document [data-node-type=blockContainer]") : null;
    const content = container?.querySelector(":scope > [data-content-type]");
    const type = content?.getAttribute("data-content-type") ?? "";
    if (!container || !content || !["paragraph", "heading", "bulletListItem", "numberedListItem"].includes(type)) return null;
    // A technology line changes only in Facts (D131), so it is not removed from here.
    const id = container.getAttribute("data-id");
    return id && !technologyBlock(editor._tiptapEditor.state.doc, id) ? id : null;
  }
  function contextMenu(event: React.MouseEvent) {
    event.preventDefault();
    const view = editor._tiptapEditor.view, before = rightPress.current ?? view.state.selection;
    rightPress.current = null;
    const pos = view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos;
    // A right click inside the selection keeps it; elsewhere the caret goes to the click. WebKit selects the word under the
    // pointer before this event, so the selection of the press is the one compared.
    const inside = !before.empty && pos !== undefined && pos >= before.from && pos <= before.to;
    const doc = view.state.doc;
    const kept = before instanceof AllSelection ? new AllSelection(doc) : TextSelection.create(doc, before.anchor, before.head);
    if (inside) view.dispatch(view.state.tr.setSelection(kept));
    else if (pos !== undefined) view.dispatch(view.state.tr.setSelection(TextSelection.near(doc.resolve(pos))));
    openMenu(event.clientX, event.clientY, textBlockAt(event.target));
  }
  function menuKey(event: KeyboardEvent) {
    if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
    event.preventDefault();
    const view = editor._tiptapEditor.view, coords = view.coordsAtPos(view.state.selection.head);
    openMenu(coords.left, coords.bottom + 4, textBlockAt(view.domAtPos(view.state.selection.head).node.parentElement));
  }
  async function pasteFromMenu() {
    const desktop = (window as { foldcvDesktop?: { paste?: () => Promise<unknown> } }).foldcvDesktop;
    editor.focus();
    // In the app the shell sends the system paste to the page: a real paste event with no prompt.
    if (desktop?.paste) { setMenuAt(null); await desktop.paste(); return; }
    try {
      const text = await navigator.clipboard.readText();
      setMenuAt(null);
      await session.pasteText(text);
    } catch { setPasteHint(/Mac|iPhone|iPad/u.test(navigator.platform) ? "Нажмите ⌘V" : "Нажмите Ctrl+V"); }
  }
  const runMenu = (item: MenuItem) => {
    if (item === "paste") { void pasteFromMenu(); return; }
    setMenuAt(null);
    editor.focus();
    if (item === "cut" || item === "copy") document.execCommand(item);
    else if (item === "rewrite") openRewrite();
    else if (item === "reword") { const block = caretBlock(); if (block) openReword(block); }
    else if (menuBlock.current) void session.removeBlocks([menuBlock.current]);
  };
  const closeMenu = useCallback(() => setMenuAt(null), []);
  const selecting = session.rewriteSource() !== null;
  const selectionAnchor = selecting && !rewriteOpen && !dragging && !locked && workspaceView !== "original" ? selectionEnd() : null;
  // The fact a mark names, shown in Facts: the panel opens on its row.
  const openFact = (recordId: string) => { setFactsVisible(true); setFactFocus({ recordId }); };
  return <div className="contents uir-editor-session">
    <SelectionAction anchor={selectionAnchor} open={openRewrite} />
    <RefusalNotice refusal={refusal} done={refusalDone} />
    <ContextMenu at={menuAt} items={menuList} run={runMenu} close={closeMenu} pasteHint={pasteHint} />
    <RemarkTip host={paperScroll} openFact={openFact} />
    <BlockRewordButton host={paperScroll} blockIds={locked || rewordOpen || rewriteOpen || dragging || selecting ? noBlocks : rewordIds}
      open={openReword} />
    <BlockRewritePanel open={rewordOpen} close={() => setRewordOpen(false)} instruction={rewordInstruction} change={setRewordInstruction}
      rules={rewordRules[rewordShown] ?? ""} submit={submitReword} apply={changes => void applyReword(changes)} preview={rewordPreview} busy={rewordActivity !== null}
      error={rewordError} activity={rewordActivity} cancel={id => { void rewords.cancel(id); }} anchor={rewordAnchor} />
    <RewritePanel open={rewriteOpen} close={() => setRewriteOpen(false)} instruction={instruction} change={setInstruction}
      submit={submitRewrite} busy={rewriteActivity !== null} source={rewriteSource} error={rewriteError}
      preview={rewritePreview ? { text: rewriteText } : null} apply={() => void applyRewrite()} editPreview={setRewriteText}
      anchor={rewriteAnchor} focusInstruction activity={rewriteActivity} cancel={id => { void rewrites.cancel(id); }} />
    {linkTarget && <LinkTargetDialog href={linkTarget.href} close={() => { setLinkTarget(null); editor.focus(); }}
      apply={href => void applyLinkTarget(linkTarget, href)} />}
    <WorkspaceViews view={workspaceView} change={changeWorkspaceView} hasSource={sources.length > 0} notices={null} />
    <div className="editor-body uir-editor-body">
      <aside className="editor-notifications" aria-label="Уведомления">
        {mode === "recovering" && <div className="notice warning" role="alert">
          <p>{recovering ? "Восстанавливаем введённый текст…" : "Введённый текст ещё не восстановлен."}</p>
          {!recovering && <button type="button" onClick={() => void recover()}>Продолжить</button>}
        </div>}
        {mode === "read_only" && <div className="notice warning" role="alert"><p>{errorMessage("EDITOR_REPLACED")}</p></div>}
        <EditorNotices warning={warning} clearWarning={() => setWarning("")} onOpen={() => {}} />
        {(state.kind === "conflict" || state.kind === "rejected") && <BlockedInputNotice
          text={state.kind === "conflict" ? errorMessage("V7_INPUT_CONFLICT") : knownErrorMessage(state.reason) ?? errorMessage("V7_INPUT_REJECTED")}
          keep={() => session.keepEditorText()} discard={() => session.discard()} />}
      </aside>
      {/* The layout host: the facts panel is docked beside the document. */}
      <ComparisonWorkspace view={workspaceView} order={paneOrder} original={sourceVisited && <SourceDialog projectId={initial.workspace.projectId} sources={sources}
        expanded={workspaceView === "original"} toggle={() => changeWorkspaceView(workspaceView === "original" ? "compare" : "original")}
        close={() => { changeWorkspaceView("layout"); editor.focus(); }} unshown={unshown} />} layout={<div className="document-workspace" data-facts={factsVisible ? "open" : "closed"}
        style={{ "--facts-width": `${String(factsWidth)}px`, "--document-zoom": String(zoom) } as CSSProperties}>
        <fieldset className="contents uir-editor-controls" disabled={locked}>
          <Toolbar command={command} textStyle={formatBlocks} factsVisible={factsVisible} selecting={selecting || (!locked && caretBlock() !== null)} rewriteBlock={!selecting}
            style={blockStyle(textBlocks[0])} canUndo={session.canUndo} canRedo={session.canRedo}
            blocks={textBlocks.length > 0 && !formatting} marks={markable(editor._tiptapEditor.state)} bold={heavier}
            active={{ bold: styles.bold === true, italic: styles.italic === true, underline: styles.underline === true,
              list: listed("bullet_list"), numbered: listed("numbered_list") }}
            remarks={marks && (marks.cells.size > 0 || marks.scoped.size > 0 || marks.blocks.size > 0 || beyond.size > 0) ? marking : null}
            layoutControls={<div className="layout-controls"><select className="toolbar-select" aria-label="Масштаб листа" value={String(zoomChoice)}
              onChange={event => { const next = parseZoom(event.currentTarget.value); setZoomChoice(next); saveZoom(next); }}>
              <option value="fit">По ширине</option>{zoomLevels.map(level => <option key={level} value={String(level)}>{level * 100}%</option>)}
            </select></div>} />
        </fieldset>
        {/* The page and the facts panel share one row above the assistant, so the open assistant never covers the panel. */}
        <div className="document-row">
          <fieldset className="contents uir-editor-controls" disabled={locked}>
            <FactsPanel facts={facts} document={documentShown} submit={submitPanel} pending={panelPending} paused={false}
              focusEntries={focus.entries} focusOptions={focus.options} focusOnly={focus.only} focusIcons={focus.icons ? loadIcons : null}
              technologyTargets={shown.presentation?.editor?.technologyTargets ?? []} plan={shown.presentation?.editor ?? {}}
              hidden={!factsVisible} close={() => { setFactsVisible(false); editor.focus(); }} focusRequest={factFocus} onFocused={factFocused}
              anchors={anchors} showBlock={blockId => { showBlock(blockId, "start"); }} />
          </fieldset>
          {factsVisible && <PanelHandle className="facts-handle" label="Ширина панели фактов" axis="x" sign={-1} value={factsWidth} minimum={factsWidths.minimum}
            maximum={factsWidths.maximum} change={changeFactsWidth} reset={() => changeFactsWidth(null)} />}
          <div className="paper-scroll" ref={paperScroll} onKeyDownCapture={event => { linkShortcut(event); menuKey(event); }}
            onMouseDownCapture={event => { if (event.button === 2) rightPress.current = editor._tiptapEditor.state.selection; }}>
            <div className="cv-document resume-paper" onContextMenu={contextMenu} data-project-id={initial.workspace.projectId} data-template="v7"
              data-history-position={session.history.position} data-history-length={session.history.length}>
              {sheet && <style>{sheet.css}</style>}
              {/* A style rule, not classes on the blocks: ProseMirror owns their DOM. */}
              {changed && <style key={changed.at}>{`${changed.blockIds.map(id => `.cv-document .bn-block[data-id="${CSS.escape(id)}"] > :first-child`).join(", ")} { animation: assistant-change 3s ease-out; }`}</style>}
              <div className={sheet ? "uir-engine-sheet fcv-sheet" : "uir-engine-sheet"} style={sheet?.variables}>
                {sheet?.logo && <img className="fcv-logo" src={sheet.logo.url} alt="" style={sheet.logo.style} />}
                <BlockNoteView editor={editor} theme="light" filePanel={false} slashMenu={false} formattingToolbar={false} sideMenu={false} tableHandles={false}
                  {...(portalHost ? { portalElements: { default: portalHost } } : {})} />
                {sheet?.footer && <p className="fcv-footer" style={sheet.footer.style}>{sheet.footer.text}</p>}
              </div>
            </div>
          </div>
        </div>
        {assistant ?? <div className="uir-chat-reservation" aria-hidden="true" />}
      </div>} />
    </div>
  </div>;
}
