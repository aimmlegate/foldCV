import { createExtension } from "@blocknote/core";
import { Extension } from "@tiptap/core";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { ProjectApiFailure, type ProjectEditorConnection } from "./v7-connection";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { AssistantApplyResultV1 } from "../contracts/generated/assistant_apply_result_v1";
import type { AssistantFinding, AssistantSelection } from "../assistant/controller";
import { errorMessage, knownErrorMessage } from "../errors/messages";
import { ComparisonWorkspace, WorkspaceViews, type WorkspaceView } from "../workbench/editor/ComparisonWorkspace";
import { SourceDialog } from "../workbench/editor/SourceDialog";
import type { PaneOrder } from "../workbench/settings/interface";
import { BlockedInputNotice } from "../workbench/editor/BlockedInputNotice";
import { EditorNotices } from "../workbench/editor/EditorNotices";
import { FactsPanel } from "../workbench/facts/FactsPanel";
import { RewritePanel } from "../workbench/editor/RewritePanel";
import { LinkTargetDialog } from "../workbench/editor/LinkTargetDialog";
import { RewriteRequests, type RewriteActivity } from "./rewrite-progress";
import type { PanelCommand } from "./v7-panel";
import { Toolbar, type ToolbarCommand } from "../workbench/editor/Toolbar";
import { blockStyle, selectionLocation, type BlockStyle } from "./selection";
import { markable } from "./v7-extraction";
import { tableIdentityAttributes } from "./table-identity";
import { disabledExtensions, templateSchema } from "./template-schema";
import { projectTemplateDocument } from "./v7-projection";
import { focusFacts } from "./v7-focus";
import { focusIconChoices } from "../projects/api";
import { remarkMarks, remarkMarksMeta, remarkMarksPlugin, type RemarkMarks } from "./remarks";
import { groupAnchors } from "./outline";
import { readRemarkMarks, saveRemarkMarks } from "../workbench/settings/interface";
import { presentationMeta, templatePresentationPlugin, templateSheet, type TemplateSheet } from "./v7-presentation";
import { TemplateEditorSession, type TemplateRewrite, type EditorMode } from "./v7-session";

export type TemplateEditorHandle = { background: boolean; flush: () => Promise<TemplateProjectResponseV1>;
  navigate: () => Promise<void>; resume: () => Promise<void>; refresh: () => Promise<void>; undo: () => void; redo: () => void;
  /** The assistant drawer's bridge: Apply through this page's token, the selection as run context, and a finding's place. */
  applyAssistant: (proposalId: string, allowEdits: boolean) => Promise<AssistantApplyResultV1>;
  captureSelection: () => AssistantSelection | null;
  focusFinding: (anchor: AssistantFinding["anchors"][number]) => boolean };
type ShownBlock = NonNullable<TemplateProjectResponseV1["workspace"]["project"]>["document"]["regions"][number]["blocks"][number];

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
  const [mode, setMode] = useState<EditorMode | null>(null);
  const [recovering, setRecovering] = useState(false), [formatting, setFormatting] = useState(false);
  const recoveryRunning = useRef(false);
  // The verified state shown in the editor: facts and issues are read from it, never from editor content.
  const [shown, setShown] = useState(initial);
  const [factsVisible, setFactsVisible] = useState(false);
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
  const callbacks = useRef({ onStatus, onShown });
  callbacks.current = { onStatus, onShown };
  // The compiled presentation of the verified state; decorations read the latest one.
  const sheet = useMemo(() => templateSheet(shown), [shown]);
  const presented = useRef<TemplateSheet | null>(sheet);
  presented.current = sheet;
  const presentation = useMemo(() => templatePresentationPlugin(() => presented.current), []);
  // Remarks and doubtful values of the verified state, marked in the text while the switch is on.
  const marks = useMemo(() => {
    const value = shown.workspace.project;
    return value ? remarkMarks(value.document, value.importIssues, value.facts) : null;
  }, [shown]);
  const [marking, setMarking] = useState(readRemarkMarks);
  const marked = useRef<RemarkMarks | null>(null);
  marked.current = marking ? marks : null;
  const remarkPlugin = useMemo(() => remarkMarksPlugin(() => marked.current), []);
  const session = useMemo(() => new TemplateEditorSession(connection, {
    status: text => { callbacks.current.onStatus(text); refresh(value => value + 1); },
    // A repeated text still re-renders: the undo buttons follow the history a refused step brought back.
    warning: text => { setWarning(text); refresh(value => value + 1); },
    mode: value => setMode(value),
    shown: response => { setShown(response); callbacks.current.onShown(response); refresh(value => value + 1); },
  }), [connection]);
  // Copy, cut and paste must run before BlockNote's own clipboard handlers, which would otherwise end the event.
  const extension = useMemo(() => createExtension({ key: "foldcv-v7-session", runsBefore: ["link"], tiptapExtensions: [tableIdentityAttributes,
    Extension.create({ name: "foldcv-v7-clipboard", priority: 1000, addProseMirrorPlugins: () => [session.clipboard] })],
    prosemirrorPlugins: [session.plugin, presentation, remarkPlugin] }), [session, presentation, remarkPlugin]);
  const editor = useCreateBlockNote({ schema: templateSchema, extensions: [extension],
    disableExtensions: disabledExtensions,
    tables: { splitCells: true, cellBackgroundColor: true, cellTextColor: true, headers: true },
    initialContent: projectTemplateDocument(project.document) }, []);
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
  useImperativeHandle(ref, () => ({ background: true,
    flush: async () => {
      await session.flush();
      return session.queue.template.durable;
    },
    navigate: () => session.navigateAway(), resume: () => session.resume(), refresh: () => session.refresh(),
    undo: () => void session.navigate("undo"), redo: () => void session.navigate("redo"),
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
    if (value === "rewrite") { openRewrite(); return; }
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
  // Selection changes re-render the editor; Focus and the group anchors are read again only when the shown state changes.
  const focus = useMemo(() => shown.workspace.project ? focusFacts(shown.workspace.project, shown.presentation)
    : { entries: [], options: [], only: new Set<string>(), icons: false }, [shown]);
  const projectId = initial.workspace.projectId;
  const loadIcons = useCallback(() => focusIconChoices(projectId), [projectId]);
  const anchors = useMemo(() => groupAnchors(documentShown, new Map(facts.records.map(record => [record.id, record.kind]))),
    [documentShown, facts]);
  const locked = mode === "read_only" || mode === "detached" || mode === "recovering";
  return <div className="contents uir-editor-session">
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
      {/* The layout host: the facts panel floats over the document. */}
      <ComparisonWorkspace view={workspaceView} order={paneOrder} original={sourceVisited && <SourceDialog projectId={initial.workspace.projectId} sources={sources}
        expanded={workspaceView === "original"} toggle={() => changeWorkspaceView(workspaceView === "original" ? "compare" : "original")}
        close={() => { changeWorkspaceView("layout"); editor.focus(); }} />} layout={<div className="document-workspace">
        <fieldset className="contents uir-editor-controls" disabled={locked}>
          <Toolbar command={command} textStyle={formatBlocks} factsVisible={factsVisible} selecting={session.rewriteSource() !== null}
            style={blockStyle(textBlocks[0])} canUndo={session.canUndo} canRedo={session.canRedo}
            blocks={textBlocks.length > 0 && !formatting} marks={markable(editor._tiptapEditor.state)}
            active={{ bold: styles.bold === true, italic: styles.italic === true, underline: styles.underline === true,
              list: listed("bullet_list"), numbered: listed("numbered_list") }}
            remarks={marks && (marks.cells.size > 0 || marks.blocks.size > 0) ? marking : null} />
        </fieldset>
        <fieldset className="contents uir-editor-controls" disabled={locked}>
          <FactsPanel facts={facts} document={documentShown} submit={submitPanel} pending={panelPending} paused={false}
            focusEntries={focus.entries} focusOptions={focus.options} focusOnly={focus.only} focusIcons={focus.icons ? loadIcons : null}
            technologyTargets={shown.presentation?.editor?.technologyTargets ?? []} plan={shown.presentation?.editor ?? {}}
            hidden={!factsVisible} close={() => { setFactsVisible(false); editor.focus(); }} focusRequest={factFocus} onFocused={factFocused}
            anchors={anchors} showBlock={blockId => { showBlock(blockId, "start"); }} />
        </fieldset>
        <div className="paper-scroll" onKeyDownCapture={linkShortcut}>
          <div className="cv-document resume-paper" data-project-id={initial.workspace.projectId} data-template="v7"
            data-history-position={session.history.position} data-history-length={session.history.length}>
            {sheet && <style>{sheet.css}</style>}
            {/* A style rule, not classes on the blocks: ProseMirror owns their DOM. */}
            {changed && <style key={changed.at}>{`${changed.blockIds.map(id => `.cv-document .bn-block[data-id="${CSS.escape(id)}"] > :first-child`).join(", ")} { animation: assistant-change 3s ease-out; }`}</style>}
            <div className={sheet ? "uir-engine-sheet fcv-sheet" : "uir-engine-sheet"} style={sheet?.variables}>
              {sheet?.logo && <img className="fcv-logo" src={sheet.logo.url} alt="" style={sheet.logo.style} />}
              <BlockNoteView editor={editor} theme="light" filePanel={false} slashMenu={false} formattingToolbar={false} sideMenu={false} tableHandles={false}
                {...(portalHost ? { portalElements: { default: portalHost } } : {})} />
            </div>
          </div>
        </div>
        {assistant ?? <div className="uir-chat-reservation" aria-hidden="true" />}
      </div>} />
    </div>
  </div>;
}
