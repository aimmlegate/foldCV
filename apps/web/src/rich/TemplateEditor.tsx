import { createExtension } from "@blocknote/core";
import { Extension } from "@tiptap/core";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import type { ProjectEditorConnection } from "./v7-connection";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { AssistantApplyResultV1 } from "../contracts/generated/assistant_apply_result_v1";
import type { AssistantFinding, AssistantSelection } from "../assistant/controller";
import { errorMessage, knownErrorMessage } from "../errors/messages";
import { ComparisonWorkspace, WorkspaceViews, type WorkspaceView } from "../workbench/editor/ComparisonWorkspace";
import { SourceDialog } from "../workbench/editor/SourceDialog";
import { EditorNotices } from "../workbench/editor/EditorNotices";
import { FactsPanel } from "../workbench/facts/FactsPanel";
import { RewritePanel } from "../workbench/editor/RewritePanel";
import { LinkTargetDialog } from "../workbench/editor/LinkTargetDialog";
import type { RewriteActivity } from "./rewrite-progress";
import type { PanelCommand } from "./v7-panel";
import { Toolbar, type ToolbarCommand } from "../workbench/editor/Toolbar";
import { blockStyle, selectionLocation, type BlockStyle } from "./selection";
import { tableIdentityAttributes } from "./table-identity";
import { templateSchema } from "./template-schema";
import { projectTemplateDocument } from "./v7-projection";
import { checkCount, checkRemarks, importRemarks, placeRemarks } from "./remarks";
import type { ProjectCheckResultV1 } from "../contracts/generated/project_check_result_v1";
import type { CheckState } from "../workbench/facts/RemarkSections";
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
export function TemplateEditor({ initial, connection, onStatus, onShown, ref, portalHost, assistant }: {
  initial: TemplateProjectResponseV1; connection: ProjectEditorConnection; onStatus: (status: string) => void;
  onShown: (response: TemplateProjectResponseV1) => void; ref: Ref<TemplateEditorHandle>; portalHost?: HTMLElement; assistant?: ReactNode }) {
  const project = initial.workspace.project;
  if (!project) throw new Error("Document is missing");
  const [warning, setWarning] = useState("");
  const [mode, setMode] = useState<EditorMode | null>(null);
  const [recovering, setRecovering] = useState(false);
  const recoveryRunning = useRef(false);
  // The verified state shown in the editor: facts and issues are read from it, never from editor content.
  const [shown, setShown] = useState(initial);
  const [factsVisible, setFactsVisible] = useState(false);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("layout");
  const [sourceVisited, setSourceVisited] = useState(false);
  const [panelPending, setPanelPending] = useState<PanelCommand[]>([]);
  const [, refresh] = useState(0);
  // Selected-text rewrite: one preview at a time; nothing changes until Apply.
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [rewriteSource, setRewriteSource] = useState("");
  const [rewritePreview, setRewritePreview] = useState<TemplateRewrite | null>(null);
  const [rewriteText, setRewriteText] = useState("");
  const [rewriteError, setRewriteError] = useState("");
  const [rewriteActivity, setRewriteActivity] = useState<RewriteActivity | null>(null);
  const [rewriteAnchor, setRewriteAnchor] = useState<{ left: number; top: number; bottom: number } | null>(null);
  // A bound link's URL is edited through Python, which changes its URL cell and target together.
  const [linkTarget, setLinkTarget] = useState<{ blockId: string; occurrenceId: string; href: string } | null>(null);
  // The last explicit check; its findings stay listed until the next check and read as stale after a document change.
  const [checked, setChecked] = useState<ProjectCheckResultV1 | null>(null);
  const [checkState, setCheckState] = useState<{ kind: "idle" | "running" } | { kind: "failed"; message: string }>({ kind: "idle" });
  const callbacks = useRef({ onStatus, onShown });
  callbacks.current = { onStatus, onShown };
  // The compiled presentation of the verified state; decorations read the latest one.
  const sheet = useMemo(() => templateSheet(shown), [shown]);
  const presented = useRef<TemplateSheet | null>(sheet);
  presented.current = sheet;
  const presentation = useMemo(() => templatePresentationPlugin(() => presented.current), []);
  const session = useMemo(() => new TemplateEditorSession(connection, {
    status: text => { callbacks.current.onStatus(text); refresh(value => value + 1); },
    warning: text => setWarning(text),
    mode: value => setMode(value),
    shown: response => { setShown(response); callbacks.current.onShown(response); refresh(value => value + 1); },
  }), [connection]);
  // Copy, cut and paste must run before BlockNote's own clipboard handlers, which would otherwise end the event.
  const extension = useMemo(() => createExtension({ key: "foldcv-v7-session", runsBefore: ["link"], tiptapExtensions: [tableIdentityAttributes,
    Extension.create({ name: "foldcv-v7-clipboard", priority: 1000, addProseMirrorPlugins: () => [session.clipboard] })],
    prosemirrorPlugins: [session.plugin, presentation] }), [session, presentation]);
  const editor = useCreateBlockNote({ schema: templateSchema, extensions: [extension],
    disableExtensions: ["history", "sideMenu", "code-block-keyboard-shortcuts", "check-list-item-shortcuts", "toggle-list-item-shortcuts"],
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
  useImperativeHandle(ref, () => ({ background: true,
    flush: async () => {
      await session.flush();
      return session.queue.template.durable;
    },
    navigate: () => session.navigateAway(), resume: () => session.resume(), refresh: () => session.refresh(),
    undo: () => void session.navigate("undo"), redo: () => void session.navigate("redo"),
    applyAssistant: (proposalId, allowEdits) => session.applyAssistant(proposalId, allowEdits),
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
  function showBlock(blockId: string): boolean {
    if (!editor.getBlock(blockId)) return false;
    // A block without text (an item frame) cannot hold the caret; it is still scrolled to.
    try { editor.setTextCursorPosition(blockId, "start"); editor.focus(); } catch { /* scroll only */ }
    document.querySelector(`.cv-document [data-id="${CSS.escape(blockId)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    return true;
  }
  // The check reads the committed state, so typing is saved first and the result matches what the page shows.
  async function runCheck() {
    setCheckState({ kind: "running" });
    try { await session.flush(); setChecked(await connection.check()); setCheckState({ kind: "idle" }); }
    catch (error) { setCheckState({ kind: "failed", message: errorMessage(error) }); }
  }
  function formatBlocks(style: BlockStyle) {
    // The style select keeps focus after a choice; the caret goes back to the document once Python's result is shown.
    void session.format(style).then(() => { if (editor.isEditable) editor.focus(); });
  }
  function openRewrite() {
    const source = session.rewriteSource();
    if (!source) { unsupported(); return; }
    const view = editor._tiptapEditor.view, coords = view.coordsAtPos(view.state.selection.from);
    setRewriteAnchor({ left: coords.left, top: coords.top, bottom: coords.bottom });
    setRewriteSource(source.text); setRewritePreview(null); setRewriteText(""); setRewriteError(""); setRewriteOpen(true);
  }
  async function submitRewrite() {
    const requestId = crypto.randomUUID();
    setRewriteError(""); setRewriteActivity({ actionId: requestId, stage: "running", startedAt: Date.now(), finishedAt: null, detail: null });
    try {
      const preview = await session.rewritePreview(instruction, requestId);
      setRewritePreview(preview); setRewriteText(preview.text); setRewriteSource(preview.source);
    } catch (error) { setRewriteError(error instanceof Error ? error.message : "INVALID_RESULT"); }
    finally { setRewriteActivity(null); }
  }
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
    setPanelPending([value]);
    try { await session.panel(value); }
    catch (error) { if (!(error instanceof Error && error.message === "V7_INPUT_UNSUPPORTED")) setWarning(errorMessage(error)); throw error; }
    finally { setPanelPending([]); }
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
  // Selection changes re-render the editor; the outline is read again only when the shown state or the check changes.
  const remarks = useMemo(() => placeRemarks(documentShown, [...importRemarks(shown.workspace.project?.importIssues ?? []),
    ...checked ? checkRemarks(checked) : []]), [documentShown, shown, checked]);
  const check: CheckState = checkState.kind !== "idle" ? checkState : checked ? { kind: "done", count: checkCount(checked),
    stale: checked.documentRevision !== shown.workspace.documentRevision } : { kind: "idle" };
  const locked = mode === "read_only" || mode === "detached" || mode === "recovering";
  return <div className="contents uir-editor-session">
    <RewritePanel open={rewriteOpen} close={() => setRewriteOpen(false)} instruction={instruction} change={setInstruction}
      submit={() => void submitRewrite()} busy={rewriteActivity !== null} source={rewriteSource} error={rewriteError}
      preview={rewritePreview ? { text: rewriteText } : null} apply={() => void applyRewrite()} editPreview={setRewriteText}
      anchor={rewriteAnchor} focusInstruction activity={rewriteActivity} cancel={id => { void session.cancelRewrite(id); }} />
    {linkTarget && <LinkTargetDialog href={linkTarget.href} close={() => { setLinkTarget(null); editor.focus(); }}
      apply={href => void applyLinkTarget(linkTarget, href)} />}
    <WorkspaceViews view={workspaceView} change={changeWorkspaceView} hasSource={sources.length > 0} notices={null} />
    <div className="editor-body uir-editor-body">
      <aside className="editor-notifications" aria-label="Уведомления">
        {mode === "recovering" && <div className="notice warning" role="alert">
          <p>{recovering ? "Восстанавливаем введённый текст…" : errorMessage("WRITER_RECOVERY_REQUIRED")}</p>
          {!recovering && <button type="button" onClick={() => void recover()}>Продолжить</button>}
        </div>}
        {mode === "read_only" && <div className="notice warning" role="alert"><p>{errorMessage("EDITOR_REPLACED")}</p></div>}
        <EditorNotices warning={warning} clearWarning={() => setWarning("")} onOpen={() => {}} />
        {(state.kind === "conflict" || state.kind === "rejected") && <div className="notice warning" role="alert">
          <p>{errorMessage(state.kind === "conflict" ? "V7_INPUT_CONFLICT" : "V7_INPUT_REJECTED")}</p>
          <button type="button" onClick={() => session.retry()}>Сохранить мой текст</button>
        </div>}
      </aside>
      {/* The layout host: the facts panel floats over the document. */}
      <ComparisonWorkspace view={workspaceView} original={sourceVisited && <SourceDialog projectId={initial.workspace.projectId} sources={sources}
        expanded={workspaceView === "original"} toggle={() => changeWorkspaceView(workspaceView === "original" ? "compare" : "original")}
        close={() => { changeWorkspaceView("layout"); editor.focus(); }} />} layout={<div className="document-workspace">
        <fieldset className="contents uir-editor-controls" disabled={locked}>
          <Toolbar command={command} textStyle={formatBlocks} factsVisible={factsVisible} selecting={session.rewriteSource() !== null}
            style={blockStyle(textBlocks[0])} canUndo={session.canUndo} canRedo={session.canRedo}
            active={{ bold: styles.bold === true, italic: styles.italic === true, underline: styles.underline === true,
              list: listed("bullet_list"), numbered: listed("numbered_list") }} />
        </fieldset>
        <fieldset className="contents uir-editor-controls" disabled={locked}>
          <FactsPanel facts={facts} document={documentShown} submit={submitPanel} pending={panelPending} paused={false}
            hidden={!factsVisible} close={() => { setFactsVisible(false); editor.focus(); }}
            remarks={remarks} showBlock={blockId => { showBlock(blockId); }} check={{ state: check, run: () => void runCheck() }} />
        </fieldset>
        <div className="paper-scroll" onKeyDownCapture={linkShortcut}>
          <div className="cv-document resume-paper" data-project-id={initial.workspace.projectId} data-template="v7"
            data-history-position={session.history.position} data-history-length={session.history.length}>
            {sheet && <style>{sheet.css}</style>}
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
