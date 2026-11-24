import type { RewordChange, RewordPreview } from "../workbench/editor/reword";
import { selectedFragmentToHTML, type BlockNoteEditor } from "@blocknote/core";
import { Plugin, PluginKey, TextSelection, type EditorState, type Transaction } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";
import type { AssistantApplyResultV1 } from "../contracts/generated/contracts";
import { ProjectEditorConnection, ProjectApiFailure, pendingStore, type AcceptTarget, type EditResult, type PendingNavigation, type PendingRecord, type PendingStore } from "./v7-connection";
import type { RichDocumentV2, TemplateProjectResponseV1 } from "../contracts/generated/contracts";
import { contentText, responseBlocks } from "./v7-response";
import { errorMessage, knownErrorMessage } from "../errors/messages";
import { projectRegionChildren } from "../workbench/editor/regions";
import { SessionHistory, type HistoryKind, type HistoryReservation } from "./history";
import { RichSaveQueue, type TemplateAdoption, type TemplateQueueState, type TemplateQueuedIntent } from "./save-queue";
import { restoreTableIdentities } from "./table-identity";
import type { templateSchema } from "./template-schema";
import { blockAt, containerText, copySource, correctionOperation, emptyRemovalAt, extractOperations, foldComposition, insertionAt, joinAt, mergeAt,
  placementOf, itemContaining, rangeAt, rangeCaret, replacementAt, selectedBlocks, selectedText, siblingAfter, splitAt, technologyLines, technologyLocked,
  technologySelected, textPoint, textPosition, type ExtractedOperation, type Insertion, type TextPoint, type TextRange } from "./v7-extraction";
import { wireMarks } from "./inline";
import { panelCommandsV7, type PanelCommand } from "./v7-panel";
import { serverRewriteStage, type RewriteStage } from "./rewrite-progress";
import { projectTemplateBlock, templateTableIdentities } from "./v7-projection";
import { changedBy, selectedTextBlocks, shownSelection, styledKind, type BlockStyle, type TextBlock } from "./selection";
import { clipboardSelection, containerKey, correctionRange, verifiedRange, type ClipboardSource, type LocalContainer, type LocalJoin, type Placement,
  type V7Intent, type V7Operation } from "./v7-translation";

export type EditorMode = "normal" | "recovering" | "read_only" | "detached" | "closed";
type Schema = typeof templateSchema;
export type TemplateEditor = BlockNoteEditor<Schema["blockSchema"], Schema["inlineContentSchema"], Schema["styleSchema"]>;
export type TemplateSessionPort = {
  status: (text: string) => void;
  warning: (text: string) => void;
  mode: (mode: EditorMode) => void;
  /** The verified canonical state now shown in the editor. */
  shown: (response: TemplateProjectResponseV1) => void;
  /** An input that was not taken, said at the place of work; without it the notice area says it. */
  refused?: (text: string) => void;
};

const projectionMeta = "foldcv.v7.projection";
// Marks a copy from this editor; the token finds the session's own server capture, never wording.
export const clipboardType = "application/x-foldcv-v7-copy";
type Captured = { id: string; kind: ClipboardSource["kind"] };
type CommandItem = { operation: V7Operation; prior: ReadonlyMap<string, string> };
type Copied = { token: string; text: string; capture: Promise<Captured | null> };
/** A generated replacement for one selected range, shown before anything changes. */
export type TemplateRewrite = { requestId: string; instruction: string; container: LocalContainer; start: number; end: number;
  prior: string; source: string; text: string };

/** Binds one BlockNote editor to the shared V7 queue, writer and server-retained SessionHistory. */
export class TemplateEditorSession {
  readonly queue: RichSaveQueue;
  readonly history: SessionHistory;
  readonly plugin: Plugin;
  /** Copy, cut and paste; installed ahead of BlockNote's own clipboard handlers. */
  readonly clipboard: Plugin;
  private editor: TemplateEditor | null = null;
  private copied: Copied | null = null;
  // While set, an editor move is only measured for its target, never applied.
  private probe: { blockId: string; placement: Placement | null } | null = null;
  // Server-first intents change the editor only through the verified result; drafts do not retain them.
  private readonly serverFirst = new Set<string>();
  private readonly stash = new WeakMap<Transaction, ExtractedOperation[]>();
  private readonly tokens = new Map<string, number>();
  private readonly waiters = new Set<() => void>();
  private composing = false;
  private composed: ExtractedOperation[] = [];
  // A composition can end while the writer is locked; its text is already in the editor and must still be queued.
  private deferred: { value: ExtractedOperation; kind: HistoryKind }[] = [];
  private group = 0;
  private lastInput = 0;
  private action: string | null = null;
  private location: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private projecting = false;
  private navigating = false;
  // Settles when the undo or redo in flight has been adopted or given up.
  private navigation: Promise<void> = Promise.resolve();
  private panelBusy = false;
  // A refusal of a facts-panel command is shown by the panel, not as an editor notice.
  private factsCommand = false;
  // A block style waits for Python's result; a second one before it would be expressed on a stale revision.
  private formatting = false;
  // A removal that Backspace or Delete started, from the key to the re-projection; more of these keys do nothing meanwhile.
  private removing: Promise<void> | null = null;
  // Characters typed while a range removal that typing started is in flight; they are typed at the caret after it.
  private held: string[] = [];
  // Set when the queue has said a refusal of the structure command in flight.
  private said = false;
  private closed = false;
  private retries = 0;
  // A cancel can come while the request still waits for typing to save; it is then never sent.
  private readonly cancelledRewrites = new Set<string>();

  private modeValue: EditorMode = "recovering";
  private retention: Promise<void> = Promise.resolve();
  private recovery: Promise<void> | null = null;
  private pendingLoaded = false;
  private pendingNavigation: PendingNavigation | null = null;
  private historyNeedsRefresh = false;
  readonly sessionId = crypto.randomUUID();

  get mode(): EditorMode { return this.modeValue; }
  get writable(): boolean { return this.modeValue === "normal"; }
  get canUndo(): boolean { return this.connection.history.undo !== null; }
  get canRedo(): boolean { return this.connection.history.redo !== null; }
  private setMode(mode: EditorMode): void { this.modeValue = mode; this.port.mode(mode); this.lock(!this.writable); }

  constructor(readonly connection: ProjectEditorConnection, private readonly port: TemplateSessionPort, private readonly debounce = 400,
    private readonly store: PendingStore = pendingStore(), private readonly rewriteInterval = 500) {
    const sessionId = this.sessionId;
    this.history = new SessionHistory(sessionId, new Map(), () => {}, () => !this.closed, `${sessionId}:${crypto.randomUUID()}`, "server");
    this.queue = new RichSaveQueue({ durable: connection.response, sessionId, ports: {
      edit: (preparation, base) => connection.edit(preparation, base), read: () => connection.read(),
      adopted: adoption => this.adopted(adoption), changed: state => this.queueChanged(state), retained: () => {},
      released: actionId => { this.history.acknowledgeServerAction(actionId, this.tokens.get(actionId) ?? 0, false); },
      lost: items => this.lost(items), pending: () => {
        const retained = this.retain();
        void retained.catch(error => this.port.warning(errorMessage(error)));
        return retained;
      },
    } });
    queueMicrotask(() => { if (!this.closed) this.setMode("recovering"); });
    this.plugin = new Plugin({ key: new PluginKey("foldcv-v7-session"),
      filterTransaction: transaction => this.filter(transaction),
      appendTransaction: (transactions, previous, state) => {
        for (const transaction of transactions) { const operations = this.stash.get(transaction); if (operations) this.accept(operations); }
        if (this.composing || this.projecting) return null;
        // A caret in an item's hidden section line moves on to shown text, so nothing is typed or styled out of sight.
        const pointer = transactions.some(transaction => transaction.getMeta("pointer") === true);
        const shown = shownSelection(pointer ? null : previous.selection, state);
        return shown ? state.tr.setSelection(shown) : null;
      },
      props: {
        handleKeyDown: (_view, event) => this.key(event),
        handleTextInput: (view, from, to, text) => this.textInput(view.state, from, to, text),
        handleDOMEvents: {
          compositionstart: () => { this.compositionStart(); return false; },
          compositionend: () => { queueMicrotask(() => this.compositionEnd()); return false; },
          blur: () => { if (!this.composing) this.boundary(); return false; },
          beforeinput: (view, event) => {
            // Text that comes with no key press (dictation, a tool) over a range over containers takes the range path too.
            if ((event.inputType === "insertText" || event.inputType === "insertReplacementText") && event.data && !view.state.selection.empty
                && rangeAt(view.state)) {
              event.preventDefault();
              return this.textInput(view.state, view.state.selection.from, view.state.selection.to, event.data);
            }
            if (!["historyUndo", "historyRedo"].includes(event.inputType)) return false;
            event.preventDefault(); void this.navigate(event.inputType === "historyUndo" ? "undo" : "redo"); return true;
          },
        },
      } });
    this.clipboard = new Plugin({ key: new PluginKey("foldcv-v7-clipboard"), props: { handleDOMEvents: {
      copy: (view, event) => this.copy(view, event, false),
      cut: (view, event) => this.copy(view, event, true),
      paste: (_view, event) => this.paste(event),
    } } });
  }

  /** Attach the editor projected from `document`; table cells receive their canonical identities first. */
  bind(editor: TemplateEditor, document: RichDocumentV2 | null = null): void {
    this.editor = editor;
    if (document) {
      this.projecting = true;
      try { editor.transact(tr => { tr.setMeta(projectionMeta, true); restoreTableIdentities(tr, templateTableIdentities(document)); }); }
      finally { this.projecting = false; }
    }
    // Input waits while recovering: retained text is shown and saved before new input joins it.
    if (this.mode === "read_only" || this.mode === "recovering") editor.isEditable = false;
  }

  async refresh(): Promise<void> {
    await this.flush();
    const current = await this.connection.read();
    // Input typed meanwhile meets the newer revision itself and is translated again there.
    if (this.queue.template.pending.length) return;
    // An edit committed while this read was on its way: its reply is newer than the read.
    if (current.workspace.projectRevision < this.queue.template.durable.workspace.projectRevision) return;
    this.queue.template.adoptDurable(current);
    await this.reproject();
  }

  async recoverWriter(): Promise<void> {
    try { await this.queue.template.recoverPending(); await this.queue.flush(); this.setMode("normal"); await this.reproject(); }
    catch (error) { this.port.warning(errorMessage(error)); }
  }

  async navigateAway(): Promise<void> {
    this.compositionEnd();
    await this.flush();
    await this.retention;
    this.setMode("detached");
  }

  async resume(): Promise<void> { this.setMode("normal"); await this.refresh(); }

  private lock(locked: boolean): void {
    // One server-first step ending does not open input while another still runs.
    const held = locked || this.panelBusy || this.navigating;
    if (this.editor) this.editor.isEditable = !held && this.mode !== "read_only";
    if (held && this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (!held && this.deferred.length && this.writable) {
      const deferred = this.deferred;
      this.deferred = [];
      for (const { value, kind } of deferred) this.enqueue(value, kind);
    }
  }

  private refuse(reason: string, code = "V7_INPUT_UNSUPPORTED"): void {
    console.warn(`V7 input refused: ${reason}`);
    // Enter or Backspace on a chip line just does nothing: the keys offer no action there.
    if (reason !== technologyLines) this.refusal(errorMessage(code));
  }

  /** A refused input goes to the page's message at the text when the page has one, else to the notice area. */
  private refusal(text: string): void {
    if (this.port.refused) this.port.refused(text);
    else this.port.warning(text);
  }

  private filter(transaction: Transaction): boolean {
    if (this.probe && transaction.docChanged) { this.probe.placement = placementOf(transaction.doc, this.probe.blockId); return false; }
    if (!transaction.docChanged || this.projecting || transaction.getMeta(projectionMeta)) return true;
    if (this.closed || this.navigating || this.pendingNavigation || this.panelBusy || !this.writable) return false;
    const result = extractOperations(transaction);
    if (result.kind === "unsupported") { this.refuse(result.reason, result.code); return false; }
    if (result.operations.length) this.stash.set(transaction, result.operations);
    return true;
  }

  /** Input that would change a technology line goes nowhere: those lines change only in Facts (D131). */
  private technologyRefused(state: EditorState): boolean {
    if (!technologySelected(state)) return false;
    this.refuse(technologyLocked, "TECHNOLOGY_IN_FACTS");
    return true;
  }

  private accept(operations: readonly ExtractedOperation[]): void {
    for (const value of operations) {
      if (this.composing) this.composed.push(value);
      else this.enqueue(value, value.operation.kind === "replace_text" ? "typing" : "structure");
    }
  }

  private recordKinds(): Map<string, string> {
    return new Map((this.queue.template.durable.workspace.project?.facts.records ?? []).map(record => [record.id, record.kind]));
  }

  /** A facts-panel command: typing drains first; input stays locked until Python's verified result is adopted and shown. */
  async panel(command: PanelCommand): Promise<void> {
    await this.navigation;
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    const commands = panelCommandsV7(command, this.recordKinds());
    // The panel offers only what Python saves, so this is a stale or foreign command; the panel shows the refusal.
    if (!commands) { console.warn(`V7 panel ${command.operation} refused`); throw new ProjectApiFailure("PANEL_ACTION_UNSUPPORTED", 422); }
    this.factsCommand = true;
    try {
      // The line is read from the plan of the state the command is issued against, after typing drained.
      await this.command(() => {
        const target = command.lineBlockId === undefined ? undefined
          : this.queue.template.durable.presentation?.editor?.technologyTargets?.find(value => value.blockId === command.lineBlockId);
        if (command.lineBlockId !== undefined && !target) throw new ProjectApiFailure("TECHNOLOGY_LINE_MISSING", 422);
        const context = target ? { placementContext: { contextBlockId: target.blockId, placement: target.placement } } : {};
        return commands.map(value => ({ operation: { kind: "builtin_panel", command: value, ...context }, prior: new Map() }));
      }, "panel");
    } finally { this.factsCommand = false; }
  }

  /** One server-first action: typing drains, input locks, and Python's verified result is shown before input continues. */
  private async command(items: CommandItem[] | (() => CommandItem[]), kind: HistoryKind): Promise<void> {
    // An undo or redo in flight moves the revision; the command is expressed on the state it leaves.
    await this.navigation;
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    await this.flush();
    const operations = typeof items === "function" ? items() : items;
    // Locking turns the contenteditable read-only and drops its focus; an editor command gives it back.
    const focused = this.editor.isFocused();
    this.panelBusy = true;
    this.lock(true);
    try {
      this.boundary();
      const id = this.history.commit(kind, [], null);
      if (!id) throw new Error("WRITER_INPUT_BLOCKED");
      const token = this.history.capture(id, [])?.actionToken ?? 0;
      this.tokens.set(id, token);
      for (const item of operations) {
        const localId = `intent-${crypto.randomUUID()}`;
        this.serverFirst.add(localId);
        this.queue.template.enqueue({ localId, operation: item.operation, prior: item.prior }, id, token);
      }
      this.action = id;
      this.boundary();
      try { await this.queue.flush(); this.port.status("Сохранено"); }
      catch (error) {
        // Typing drained first, so only this command is pending; a definitive answer drops it and input continues.
        const state = this.queue.template.state;
        if (state.kind === "rejected" || state.kind === "conflict") this.queue.template.discardUnsaved();
        this.retryLater();
        // A refusal keeps its public code, so the caller can say why.
        if (state.kind === "rejected" && knownErrorMessage(state.reason)) throw new ProjectApiFailure(state.reason, 422);
        throw error;
      }
      await this.reproject();
    } finally {
      this.panelBusy = false;
      this.lock(!this.writable);
      if (focused && this.editor?.isEditable) this.editor.focus();
    }
  }

  /** Apply an assistant proposal: typing drains, input locks, and the editor shows Python's committed result (one undo
   * action). An unknown token re-opens and repeats the same request; a lost reply repeats it once, which the server's
   * replay window answers without applying twice. */
  async applyAssistant(proposalId: string, allowEdits: boolean): Promise<AssistantApplyResultV1> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.navigating || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    await this.flush();
    const focused = this.editor.isFocused();
    this.panelBusy = true;
    this.lock(true);
    try {
      this.boundary();
      const mutationId = crypto.randomUUID();
      let result: AssistantApplyResultV1;
      try { result = await this.connection.applyProposal(proposalId, mutationId, allowEdits); }
      catch (error) {
        if (error instanceof ProjectApiFailure && error.code === "EDITOR_REPLACED") { this.setMode("read_only"); throw error; }
        if (error instanceof ProjectApiFailure && error.code !== "EDITOR_TOKEN_UNKNOWN") throw error;
        result = await this.connection.applyProposal(proposalId, mutationId, allowEdits);
      }
      if (result.edit) this.queue.template.adoptDurable(result.edit.response);
      await this.reproject();
      return result;
    } finally {
      this.panelBusy = false;
      this.lock(!this.writable);
      if (focused && this.editor?.isEditable) this.editor.focus();
    }
  }

  /** A block reworded by the template's rules, with the user's own instruction beside them when there is one. Typing is
   * saved first, so the model reads what the page shows; `stage` hears the save, the send and the server's stages, as a
   * rewrite of a selection does. Nothing is written. */
  async rewordPreview(requestId: string, blockId: string, instruction: string, stage: (stage: RewriteStage) => void = () => {}): Promise<RewordPreview> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.navigating || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    stage("saving");
    try {
      await this.flush();
      if (this.cancelledRewrites.has(requestId)) throw new ProjectApiFailure("CANCELLED", 409);
      stage("starting");
      const stop = this.followRewrite(requestId, stage);
      return await this.connection.rewordPreview(requestId, blockId, instruction.trim()).finally(stop);
    } finally { this.cancelledRewrites.delete(requestId); }
  }

  /** The user's Apply of a reworded block, as an assistant proposal is applied: input locks, the editor shows Python's
   * committed result, one undo action takes it back. */
  async applyReword(blockId: string, changes: RewordChange[], touched: Record<string, string>): Promise<EditResult> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.navigating || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    await this.flush();
    this.panelBusy = true;
    this.lock(true);
    try {
      this.boundary();
      const mutationId = crypto.randomUUID();
      let result: EditResult;
      try { result = await this.connection.rewordApply(mutationId, blockId, changes, touched); }
      catch (error) {
        if (error instanceof ProjectApiFailure && error.code === "EDITOR_REPLACED") { this.setMode("read_only"); throw error; }
        if (error instanceof ProjectApiFailure && error.code !== "EDITOR_TOKEN_UNKNOWN") throw error;
        result = await this.connection.rewordApply(mutationId, blockId, changes, touched);
      }
      this.queue.template.adoptDurable(result.response);
      await this.reproject();
      return result;
    } finally {
      this.panelBusy = false;
      this.lock(!this.writable);
    }
  }

  /** «Принять» in a mark's tip (D179): as an Apply, input locks, the editor shows Python's committed result, one undo
   * action takes it back. */
  async acceptMark(target: AcceptTarget): Promise<EditResult> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.navigating || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    await this.flush();
    this.panelBusy = true;
    this.lock(true);
    try {
      this.boundary();
      const mutationId = crypto.randomUUID();
      let result: EditResult;
      try { result = await this.connection.accept(mutationId, target); }
      catch (error) {
        if (error instanceof ProjectApiFailure && error.code === "EDITOR_REPLACED") { this.setMode("read_only"); throw error; }
        if (error instanceof ProjectApiFailure && error.code !== "EDITOR_TOKEN_UNKNOWN") throw error;
        result = await this.connection.accept(mutationId, target);
      }
      this.queue.template.adoptDurable(result.response);
      await this.reproject();
      return result;
    } finally {
      this.panelBusy = false;
      this.lock(!this.writable);
    }
  }

  /** Editor structure commands report a refusal as a notice; the editor keeps showing the verified state. */
  private async structure(items: { operation: V7Operation; prior?: ReadonlyMap<string, string> }[]): Promise<boolean> {
    this.said = false;
    try { await this.command(items.map(item => ({ operation: item.operation, prior: item.prior ?? new Map() })), "structure"); return true; }
    catch (error) {
      // A refusal that the queue has said already is not said twice.
      if (!this.said) this.refusal(errorMessage(error));
      return false;
    }
  }

  /** Shift+Mod+Arrow: BlockNote decides the target as usual; Python moves the block and decides any owner change. */
  async move(direction: "up" | "down"): Promise<void> {
    const editor = this.editor;
    if (!editor || this.closed || this.composing || this.panelBusy || !this.writable) return;
    const blocks = editor.getSelection()?.blocks ?? [];
    if (blocks.length > 1) {
      // The section line is hidden, so any lines inside one item move that item. A selection that crosses items does not.
      const item = itemContaining(editor._tiptapEditor.state.doc, blocks.map(block => block.id));
      if (!item) { this.refuse("only one block or one whole item moves at a time"); return; }
      const index = item.siblings.indexOf(item.id), rest = item.siblings.filter(id => id !== item.id);
      if (direction === "up" ? index < 1 : index >= rest.length) return;
      // The section heading stays above its items, so an item never moves past it.
      if (item.kinds[direction === "up" ? index - 1 : index + 1] === "heading") return;
      const afterId = (direction === "up" ? rest[index - 2] : rest[index]) ?? null;
      await this.structure([{ operation: { kind: "move_block", blockId: item.id, placement: { parentId: item.parentId, afterId } } }]);
      return;
    }
    const blockId = editor.getTextCursorPosition().block.id, before = placementOf(editor._tiptapEditor.state.doc, blockId);
    const probe: { blockId: string; placement: Placement | null } = { blockId, placement: null };
    this.probe = probe;
    try { if (direction === "up") editor.moveBlocksUp(); else editor.moveBlocksDown(); }
    finally { this.probe = null; }
    const placement = probe.placement;
    if (!before || !placement || placement.parentId === before.parentId && placement.afterId === before.afterId) return;
    await this.structure([{ operation: { kind: "move_block", blockId, placement } }]);
  }

  /** The bound link at the caret; Python changes its URL cell and target together. */
  linkAtCaret(): { blockId: string; occurrenceId: string; href: string } | null {
    const editor = this.editor;
    if (!editor || this.closed) return null;
    const { $from, $to } = editor._tiptapEditor.state.selection, node = $from.parent;
    const occurrenceId: unknown = node.attrs["occurrenceId"], href: unknown = node.attrs["href"];
    if (node.type.name !== "boundLink" || $to.parent !== node || typeof occurrenceId !== "string" || !occurrenceId
      || typeof href !== "string") return null;
    return { blockId: editor.getTextCursorPosition().block.id, occurrenceId, href };
  }

  /** A new URL for one bound link, as one server-first action with its own Undo. */
  async linkTarget(target: { blockId: string; occurrenceId: string }, href: string): Promise<void> {
    await this.command([{ operation: { kind: "set_link_target", blockId: target.blockId, occurrenceId: target.occurrenceId, href },
      prior: new Map() }], "panel");
  }

  /** The text blocks the selection reaches into, with their kinds, as the editor shows them. */
  textBlocks(): TextBlock[] {
    return this.editor && !this.closed ? selectedTextBlocks(this.editor._tiptapEditor.state) : [];
  }

  /** A toolbar block style on the selected blocks: one format_blocks request and one Undo. Blocks that already have
   * the kind are left out, and nothing is sent when none is left. */
  async format(style: BlockStyle): Promise<void> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.formatting || !this.writable) return;
    const blocks = this.textBlocks();
    if (!blocks.length) { this.refuse("block style needs a text block"); return; }
    const kind = styledKind(style, blocks), blockIds = changedBy(kind, blocks);
    if (!blockIds.length) return;
    this.formatting = true;
    try { await this.structure([{ operation: { kind: "format_blocks", blockIds, blockKind: kind } }]); }
    finally { this.formatting = false; }
  }

  /** Remove whole selected blocks; their facts stay, as in Python's occurrence removal. */
  async removeBlocks(blockIds: string[]): Promise<void> {
    await this.structure([{ operation: { kind: "remove_occurrences", blockIds } }]);
  }

  /** A range over containers goes as one `remove_range`, with the join text when there is one; the caret then goes to
   * the join, else to the start of the last block when it stays, else by the rule of F2 point 4 (F3b). */
  private async removeRange(range: TextRange, join: LocalJoin | null = null, direction: "backward" | "forward" = "backward"): Promise<void> {
    const editor = this.editor;
    if (!editor) return;
    const fallback = rangeCaret(editor._tiptapEditor.state.doc, range, direction);
    const prior = new Map([[containerKey(range.start.container), range.start.prior], [containerKey(range.end.container), range.end.prior]]);
    const done = await this.structure([{ operation: { kind: "remove_range", start: { container: range.start.container, offset: range.start.offset },
      end: { container: range.end.container, offset: range.end.offset }, join }, prior }]);
    if (!done || !this.editor || this.closed) return;
    const doc = this.editor._tiptapEditor.state.doc, live = (point: TextPoint) => containerText(doc, this.canonical(point.container)) !== null;
    const start: TextPoint = { container: range.start.container, offset: range.start.offset };
    if (live(start)) { this.caretTo(join ? this.afterLines(start, join.text, join.enter) : start); return; }
    const end: TextPoint = { container: range.end.container, offset: 0 };
    this.caretTo(live(end) ? end : fallback.find(live) ?? null);
  }

  /** Lines pasted at a place, or Enter over a selection in one container, as one `paste_lines` (F3c, F3d). */
  private async pasteLines(at: Insertion, text: string, enter: boolean): Promise<void> {
    const editor = this.editor;
    if (!editor) return;
    const place = replacementAt(editor._tiptapEditor.state.doc, at.container, at.start, at.start < at.end ? at.start + 1 : at.start);
    if ("reason" in place) { this.refuse(place.reason); return; }
    const done = await this.structure([{ operation: { kind: "paste_lines", container: at.container, start: at.start, end: at.end,
      side: at.start === at.end ? at.side : null, text, styles: place.styles, enter }, prior: new Map([[containerKey(at.container), at.prior]]) }]);
    if (done) this.caretTo(this.afterLines({ container: at.container, offset: at.start }, text, enter));
  }

  /** Where the caret goes after text put at a place: after the last line Python made from it. */
  private afterLines(place: TextPoint, text: string, enter: boolean): TextPoint | null {
    const lines = pastedLines(text, enter), last = lines.at(-1) ?? "";
    if (place.container.kind !== "content") return { container: place.container, offset: place.offset + lines.join(" ").length };
    if (lines.length < 2) return { container: place.container, offset: place.offset + last.length };
    const doc = this.editor?._tiptapEditor.state.doc, id = doc ? siblingAfter(doc, this.canonical(place.container).blockId, lines.length - 1) : null;
    return id ? { container: { blockId: id, kind: "content", cellId: null }, offset: last.length } : null;
  }

  private canonical(container: LocalContainer): LocalContainer {
    const locals = this.queue.template.localBlocks;
    return { ...container, blockId: locals.get(container.blockId) ?? container.blockId };
  }

  private caretTo(point: TextPoint | null): void {
    const editor = this.editor;
    if (!editor || !point || this.closed) return;
    const doc = editor._tiptapEditor.state.doc, pos = textPosition(doc, { ...point, container: this.canonical(point.container) });
    if (pos !== null) editor._tiptapEditor.view.dispatch(editor._tiptapEditor.state.tr.setSelection(TextSelection.create(doc, pos)));
  }

  /** Typed text over a selection that spans containers: the range goes and the text goes at the join, as one action
   * (F3c). Text typed while that runs is held and typed at the caret after it. */
  private textInput(state: EditorState, from: number, to: number, text: string): boolean {
    if (this.composing) return false;
    if (this.removing) { this.held.push(text); return true; }
    if (from === to) return false;
    const range = rangeAt(state);
    if (!range) return false;
    if ("reason" in range) { this.refuse(range.reason, range.code); return true; }
    const join = joinAt(state.doc, range.start);
    if ("reason" in join) { this.refuse(join.reason); return true; }
    this.keyRemoval(() => this.removeRange(range, { text, styles: join.styles, side: join.side, enter: false }));
    return true;
  }

  /** What the page's own context menu needs to know of the selection (F5): its kind and whether a cut can run. */
  menuSelection(): { selection: "none" | "one" | "range" | "blocks"; cuttable: boolean } {
    const editor = this.editor;
    if (!editor || this.closed) return { selection: "none", cuttable: false };
    const state = editor._tiptapEditor.state;
    if (state.selection.empty) return { selection: "none", cuttable: false };
    if (selectedBlocks(state)) return { selection: "blocks", cuttable: !technologySelected(state) };
    const range = rangeAt(state);
    if (range) return { selection: "range", cuttable: !("reason" in range) };
    return { selection: "one", cuttable: !technologySelected(state) && copySource(state) !== null };
  }

  /** Cut over a range that spans containers: the copy handler has put the shown text and the HTML on the clipboard; the
   * range then goes, with no same-project capture (F3b). Null when the selection is no such range. */
  cutRange(): { text: string; done: Promise<void> } | null {
    const editor = this.editor;
    if (!editor || this.closed || !this.writable || this.composing || this.panelBusy || this.removing) return null;
    const state = editor._tiptapEditor.state, range = rangeAt(state);
    if (!range || "reason" in range) return null;
    const text = selectedText(state);
    this.keyRemoval(() => this.removeRange(range));
    return { text, done: this.keyed() };
  }

  /** The text a rewrite would read: one non-empty range inside one block or cell. */
  rewriteSource(): { container: LocalContainer; start: number; end: number; prior: string; text: string } | null {
    const editor = this.editor;
    if (!editor || technologySelected(editor._tiptapEditor.state)) return null;
    const at = insertionAt(editor._tiptapEditor.state);
    if ("reason" in at || at.start === at.end) return null;
    return { container: at.container, start: at.start, end: at.end, prior: at.prior, text: at.prior.slice(at.start, at.end) };
  }

  /** One generation for the selected range after typing drains; the document and history do not change. `stage` hears
   * the save, the send and what the server then reports. */
  async rewritePreview(instruction: string, requestId: string = crypto.randomUUID(), stage: (stage: RewriteStage) => void = () => {}): Promise<TemplateRewrite> {
    const source = this.rewriteSource();
    if (!source) throw new Error("V7_INPUT_UNSUPPORTED");
    if (this.closed || this.composing || this.panelBusy || this.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    stage("saving");
    try {
      await this.flush();
      if (this.cancelledRewrites.has(requestId)) throw new ProjectApiFailure("CANCELLED", 409);
      const template = this.queue.template;
      const range = verifiedRange(source, { response: template.durable, locals: template.localBlocks });
      if ("conflict" in range) throw new Error("V7_INPUT_CONFLICT");
      stage("starting");
      const stop = this.followRewrite(requestId, stage);
      const preview = await this.connection.rewritePreview(requestId, this.snapshot(), range, instruction).finally(stop);
      if (preview.source !== source.text) throw new Error("INVALID_RESULT");
      return { requestId, instruction, container: source.container, start: source.start, end: source.end, prior: source.prior,
        source: preview.source, text: preview.text };
    } finally { this.cancelledRewrites.delete(requestId); }
  }

  /** Reads the server's stage until the reply arrives; a failed read leaves the shown stage as it is. */
  private followRewrite(requestId: string, stage: (stage: RewriteStage) => void): () => void {
    let stopped = false, timer: ReturnType<typeof setTimeout> | null = null;
    const read = async () => {
      const value = await this.connection.rewriteStage(requestId).catch(() => null);
      if (stopped) return;
      const known = serverRewriteStage(value);
      if (known) stage(known);
      timer = setTimeout(() => { void read(); }, this.rewriteInterval);
    };
    void read();
    return () => { stopped = true; if (timer) clearTimeout(timer); };
  }

  cancelRewrite(requestId: string): Promise<boolean> {
    this.cancelledRewrites.add(requestId);
    return this.connection.rewriteCancel(requestId);
  }

  /** Apply exactly the shown text as one replacement and one Undo; only the changed middle is replaced, so the rest keeps
   * its marks and owners. A container edited since the preview conflicts instead of applying. */
  async applyRewrite(preview: TemplateRewrite, text = preview.text): Promise<void> {
    const editor = this.editor;
    if (!editor) throw new Error("WRITER_INPUT_BLOCKED");
    const middle = correctionRange(preview.source, text);
    if (!middle) return;
    const start = preview.start + middle.start, end = preview.start + middle.end;
    const place = replacementAt(editor._tiptapEditor.state.doc, preview.container, start, end);
    if ("reason" in place) { this.refuse(place.reason); throw new Error("V7_INPUT_UNSUPPORTED"); }
    await this.command([{ operation: { kind: "replace_text", container: preview.container, start, end, text: middle.text, styles: place.styles,
      side: start === end ? place.side : null }, prior: new Map([[containerKey(preview.container), preview.prior]]) }], "rewrite");
  }

  private copy(view: EditorView, event: ClipboardEvent, cut: boolean): boolean {
    const editor = this.editor, data = event.clipboardData;
    // A caret copies nothing, so the clipboard keeps what it holds.
    if (!editor || !data || this.closed || view.state.selection.empty) return false;
    event.preventDefault();
    if (cut && this.technologyRefused(view.state)) return true;
    const range = cut ? rangeAt(view.state) : null;
    if (range && "reason" in range) { this.refuse(range.reason, range.code); return true; }
    if (range && (!this.writable || this.composing || this.panelBusy || this.removing)) return true;
    if (cut && !range && (!copySource(view.state) || !this.writable || this.composing || this.panelBusy)) {
      this.refuse("cut needs whole blocks or text inside one block"); return true;
    }
    const { clipboardHTML, externalHTML } = selectedFragmentToHTML(view, editor);
    data.clearData();
    data.setData("blocknote/html", clipboardHTML);
    data.setData("text/html", externalHTML);
    // The shown text, not BlockNote's Markdown: a paste elsewhere must not bring literal markers.
    data.setData("text/plain", selectedText(view.state));
    if (range) { this.cutRange(); return true; }
    const copied = this.copySelection(cut);
    if (copied) data.setData(clipboardType, JSON.stringify({ projectId: this.connection.project, token: copied.token }));
    return true;
  }

  /** Start a same-project copy of the selection: Python captures it after typing drains. A cut removes the source
   * once the capture exists. Null when the selection names nothing Python copies. */
  copySelection(cut = false): (Copied & { done: Promise<void> }) | null {
    const editor = this.editor;
    if (!editor || this.closed || !this.writable || this.composing || this.panelBusy) return null;
    const state = editor._tiptapEditor.state, source = copySource(state);
    if (!source) return null;
    const capture = this.capture(source);
    const copied: Copied = { token: crypto.randomUUID(), text: selectedText(state), capture };
    this.copied = copied;
    return { ...copied, done: cut ? this.cut(source, capture) : capture.then(() => {}) };
  }

  /** Python captures the copied source against the drained verified state; a failed capture leaves plain text only. */
  private async capture(source: ClipboardSource): Promise<Captured | null> {
    try {
      await this.flush();
      const template = this.queue.template;
      const selection = clipboardSelection(source, { response: template.durable, locals: template.localBlocks });
      if ("conflict" in selection) { console.warn(`V7 copy not captured: ${selection.conflict}`); return null; }
      const captured = await this.connection.capture(crypto.randomUUID(), this.snapshot(), selection);
      return { id: captured.clipboardCaptureId, kind: source.kind };
    } catch (error) {
      console.warn(`V7 copy not captured: ${error instanceof Error ? error.message : String(error)}`);
      return null;
    }
  }

  /** Cut removes the source only after Python holds the copy. */
  private async cut(source: ClipboardSource, capture: Promise<Captured | null>): Promise<void> {
    if (!await capture) { this.refusal(errorMessage("V7_INPUT_UNSUPPORTED")); return; }
    if (source.kind === "blocks") { await this.removeBlocks(source.blockIds); return; }
    await this.structure([{ operation: { kind: "replace_text", container: source.container, start: source.start, end: source.end, text: "",
      styles: wireMarks({}), side: null }, prior: new Map([[containerKey(source.container), source.prior]]) }]);
  }

  private paste(event: ClipboardEvent): boolean {
    const data = event.clipboardData;
    if (!this.editor || !data || this.closed) return false;
    event.preventDefault();
    if (!this.writable || this.composing || this.panelBusy) return true;
    let marker: unknown = null;
    try { marker = JSON.parse(data.getData(clipboardType) || "null"); } catch { marker = null; }
    const own = this.copied && typeof marker === "object" && marker !== null && Reflect.get(marker, "token") === this.copied.token
      && Reflect.get(marker, "projectId") === this.connection.project ? this.copied : null;
    void this.pasteFrom(own, own?.text ?? data.getData("text/plain"));
    return true;
  }

  /** Text read from the clipboard by the page's own menu: the session's own copy keeps its bindings (F5 point 5). */
  async pasteText(text: string): Promise<void> {
    const own = this.copied && this.copied.text === text ? this.copied : null;
    await this.pasteFrom(own, text);
  }

  /** Same-project copies paste through Python with their bindings; other text enters as typing in one block. */
  async pasteFrom(copied: Copied | null, text: string): Promise<void> {
    const captured = copied ? await copied.capture : null, editor = this.editor;
    if (!editor || this.closed) return;
    let state = editor._tiptapEditor.state;
    if (this.technologyRefused(state)) return;
    const range = rangeAt(state);
    if (range && "reason" in range) { this.refuse(range.reason, range.code); return; }
    if (range && !captured) {
      // Plain text over a range over containers: the range goes and the text goes at the join, as one action (F3b, F3d).
      const join = joinAt(state.doc, range.start);
      if ("reason" in join) { this.refuse(join.reason); return; }
      if (text) await this.removeRange(range, { text, styles: join.styles, side: join.side, enter: false });
      return;
    }
    if (range) {
      // The session's own copy: the range goes first, then the present paste runs at the caret (two actions).
      await this.removeRange(range);
      if (!this.editor || this.closed || rangeAt(this.editor._tiptapEditor.state)) return;
      state = this.editor._tiptapEditor.state;
    }
    if (captured?.kind === "blocks") {
      const caret = blockAt(state), around = caret ? placementOf(state.doc, caret) : null;
      if (!caret || !around) { this.refuse("blocks paste needs a caret in a block"); return; }
      await this.structure([{ operation: { kind: "paste_blocks", clipboardCaptureId: captured.id, placement: { parentId: around.parentId, afterId: caret } } }]);
      return;
    }
    const at = insertionAt(state);
    if ("reason" in at) { this.refuse(at.reason); return; }
    if (captured) {
      await this.structure([{ operation: { kind: "paste_inline", container: at.container, start: at.start, end: at.end, side: at.side,
        source: { kind: "same_project", clipboardCaptureId: captured.id } }, prior: new Map([[containerKey(at.container), at.prior]]) }]);
      return;
    }
    // One copied line ends in a line end; text with more lines is pasted as lines by Python (F3d).
    const line = text.replace(/\r?\n$/, "");
    if (/[\r\n]/.test(line)) { await this.pasteLines(at, text, false); return; }
    if (line) editor._tiptapEditor.view.dispatch(state.tr.insertText(line));
  }

  /** Moving the caret to another container ends the current typing action. */
  selected(location: string | null): void {
    if (!this.composing && this.location !== null && this.location !== location) this.boundary();
    this.location = location;
  }

  /** Close the current history action: later input starts a new one and the queue may release an empty one. */
  boundary(): void {
    this.group++;
    if (this.action) { this.queue.template.seal(this.action); this.action = null; }
  }

  private enqueue(value: ExtractedOperation, kind: HistoryKind): void {
    if (!this.writable || this.deferred.length) { this.deferred.push({ value, kind }); return; }
    const now = Date.now();
    if (kind === "structure" || now - this.lastInput > 500) this.boundary();
    this.lastInput = now;
    const id = this.history.commit(kind, [], kind === "structure" ? null : `typing:${this.group}`);
    if (!id) { this.refuse("history is closed or reserved"); return; }
    if (this.action !== id) { if (this.action) this.queue.template.seal(this.action); this.action = id; }
    const token = this.history.capture(id, [])?.actionToken ?? 0;
    this.tokens.set(id, token);
    this.queue.template.enqueue({ localId: `intent-${crypto.randomUUID()}`, operation: value.operation, prior: value.prior }, id, token);
    if (kind === "structure") this.boundary();
    this.retainSoon();
    this.schedule();
  }

  private snapshot() {
    const snapshot = this.queue.template.durable.snapshot;
    if (!snapshot) throw new Error("INVALID_RESULT");
    return snapshot;
  }

  private retainSoon(): void { void this.retain().catch(error => this.port.warning(errorMessage(error))); }

  retain(): Promise<void> {
    if (!this.pendingLoaded) return this.retention;
    const intents = this.queue.template.pending.map(item => ({ localId: item.intent.localId, clientMutationId: item.clientMutationId,
      baseRevision: item.baseRevision, actionId: item.actionId, actionToken: item.actionToken,
      operation: structuredClone(item.intent.operation), prior: [...item.intent.prior], issued: item.issued,
      text: item.intent.operation.kind === "replace_text" ? item.intent.operation.text : [...item.intent.prior.values()].join("\n") }));
    const record: PendingRecord = { schemaVersion: 1, project: this.connection.project, intents, locals: [...this.queue.template.localBlocks],
      navigation: this.pendingNavigation };
    this.retention = this.retention.catch(() => {}).then(() => intents.length || record.navigation ? this.store.save(record) : this.store.clear(record.project));
    return this.retention;
  }

  private lost(items: readonly TemplateQueuedIntent[], code = "V7_INPUT_CONFLICT"): void {
    const text = items.map(item => item.intent.operation.kind === "replace_text" ? item.intent.operation.text
      : [...item.intent.prior.values()].join("\n")).filter(Boolean).join("\n");
    this.port.warning(`${errorMessage(code)}${text ? "\n" + text : ""}`);
    // The editor still shows the dropped text; the saved state replaces it once nothing else is pending.
    if (!this.queue.template.pending.length) queueMicrotask(() => { void this.reproject(); });
  }

  async recoverDraft(): Promise<{ conflicts: number }> {
    this.recovery ??= this.restorePending().finally(() => { this.recovery = null; });
    await this.recovery;
    return { conflicts: 0 };
  }

  private async restorePending(): Promise<void> {
    const record = this.pendingLoaded ? null : await this.store.load(this.connection.project);
    if (this.closed) return;
    if (record) {
      this.pendingNavigation = record.navigation;
      this.queue.template.restore(record.intents.map(item => ({ intent: { localId: item.localId, operation: item.operation,
        prior: new Map(item.prior) }, actionId: item.actionId, actionToken: item.actionToken, clientMutationId: item.clientMutationId,
        baseRevision: item.baseRevision, issued: item.issued })), record.locals);
    }
    this.pendingLoaded = true;
    // An undo or redo that cannot be settled is given up with a notice; it does not keep the editor in recovery.
    if (this.pendingNavigation) await this.recoverNavigation().catch(error => { this.port.warning(errorMessage(error)); });
    while (this.queue.template.pending.length) {
      const head = this.queue.template.pending[0];
      await this.queue.template.recoverPending();
      if (head?.clientMutationId === this.queue.template.pending[0]?.clientMutationId) break;
    }
    try { await this.flush(); }
    catch (error) {
      const state = this.queue.template.state.kind;
      if (state !== "rejected" && state !== "conflict") throw error;
      this.lost(this.queue.template.pending);
      this.queue.template.discardUnsaved();
    }
    await this.retain();
    this.setMode("normal");
    await this.reproject();
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.port.status("Изменения сохраняются…");
    if (this.composing || this.closed) return;
    this.timer = setTimeout(() => { this.timer = null; void this.flush().catch(() => {}); }, this.debounce);
  }

  async flush(): Promise<void> {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    try {
      await this.queue.flush();
      if (this.historyNeedsRefresh) {
        await this.connection.reopen();
        this.queue.template.adoptDurable(this.connection.response);
        this.historyNeedsRefresh = false;
      }
      await this.retention;
      this.retries = 0;
      this.port.status("Сохранено");
    } catch (error) {
      this.retainSoon();
      this.port.status(errorMessage(error));
      if (this.connection.replaced) this.setMode("read_only");
      this.retryLater();
      throw error;
    }
  }

  /** Pending input without an answer is sent again with the same ids after 1, 2, 4… up to 30 seconds; a refusal or a
   * conflict blocks the queue instead and waits for the user. */
  private retryLater(): void {
    if (this.closed || this.timer || !this.writable || this.queue.template.state.kind !== "ready" || !this.queue.template.pending.length) return;
    const delay = Math.min(30_000, 1000 * 2 ** Math.min(this.retries++, 5));
    this.timer = setTimeout(() => { this.timer = null; void this.flush().catch(() => {}); }, delay);
  }

  private adopted(adoption: TemplateAdoption): void {
    if (adoption.result === null) this.historyNeedsRefresh = true;
    if (!this.queue.template.pending.length) queueMicrotask(() => { void this.reproject(); });
  }

  private queueChanged(state: TemplateQueueState): void {
    if (state.kind === "conflict") this.port.warning(errorMessage("V7_INPUT_CONFLICT"));
    else if (state.kind === "rejected" && !this.factsCommand) {
      this.said = true;
      this.refusal(knownErrorMessage(state.reason) ?? errorMessage("V7_INPUT_REJECTED"));
    }
    else if (state.kind === "replaced") { this.setMode("read_only"); this.port.warning(errorMessage("EDITOR_REPLACED")); }
  }

  /** Containers are re-projected from canonical content only after the queue drains; local block IDs end there. */
  async reproject(): Promise<boolean> {
    const editor = this.editor, durable = this.queue.template.durable;
    if (!editor || this.closed || this.composing || this.queue.template.pending.length) return false;
    const response = durable, project = response.workspace.project;
    if (!response || !project) { this.port.warning(errorMessage("INVALID_RESULT")); return false; }
    if (durable !== this.queue.template.durable || this.closed || this.composing || this.queue.template.pending.length) return false;
    const locals = this.queue.template.localBlocks;
    this.projecting = true;
    try {
      editor.transact(tr => {
        tr.setMeta(projectionMeta, true);
        // Inline structure may change (new fragments), so the caret is kept as text offsets, not node positions.
        const caret = tr.selection instanceof TextSelection
          ? [textPoint(tr.doc, tr.selection.anchor), textPoint(tr.doc, tr.selection.head)].map(point => rekey(point, locals)) : null;
        projectRegionChildren(tr, project.document.regions.map(region => ({ id: region.id, children: region.blocks.map(projectTemplateBlock) })),
          (id, children) => editor.updateBlock(id, { children }));
        restoreTableIdentities(tr, templateTableIdentities(project.document));
        const [anchor, head] = caret?.map(point => point && textPosition(tr.doc, point)) ?? [];
        if (anchor !== null && anchor !== undefined && head !== null && head !== undefined) tr.setSelection(TextSelection.create(tr.doc, anchor, head));
      });
    } finally { this.projecting = false; }
    this.port.shown(response);
    return true;
  }

  enter(): boolean {
    if (this.composing) return false;
    const editor = this.editor;
    if (!editor || this.removing) return true;
    const state = editor._tiptapEditor.state;
    if (!state.selection.empty) {
      // Enter over a selection: the selected text goes, then the block splits there, as one action (F3c).
      const range = rangeAt(state);
      if (range && "reason" in range) { this.refuse(range.reason, range.code); return true; }
      if (range) {
        const join = joinAt(state.doc, range.start);
        if ("reason" in join) this.refuse(join.reason);
        else this.keyRemoval(() => this.removeRange(range, { text: "", styles: join.styles, side: null, enter: true }));
        return true;
      }
      if (this.technologyRefused(state)) return true;
      const at = insertionAt(state);
      if ("reason" in at) this.refuse(at.reason);
      else if (at.container.kind !== "content") this.refuse("cells and captions keep one line");
      else this.keyRemoval(() => this.pasteLines(at, "", true));
      return true;
    }
    const result = splitAt(state, `local-${crypto.randomUUID()}`);
    if ("reason" in result) this.refuse(result.reason);
    else editor._tiptapEditor.view.dispatch(result.transaction);
    return true;
  }

  /** Backspace/Delete at a block edge merge siblings; elsewhere the default deletion is plain text input. A merge that
   * cannot be made at the edge is silent: the key just does nothing there. */
  join(direction: "backward" | "forward"): boolean {
    const editor = this.editor;
    if (!editor || this.composing) return false;
    const state = editor._tiptapEditor.state, result = mergeAt(state, direction);
    if ("transaction" in result) { editor._tiptapEditor.view.dispatch(result.transaction); return true; }
    return !/caret is not at the block edge|structure input needs a caret/.test(result.reason);
  }

  /** Settles when the removal that a key started has been shown. */
  keyed(): Promise<void> { return this.removing ?? Promise.resolve(); }

  private keyRemoval(work: () => Promise<void>): void {
    const stop = this.holdKeys();
    const done = work().finally(() => {
      stop();
      if (this.removing !== done) return;
      this.removing = null;
      this.typeHeld();
    });
    this.removing = done;
  }

  /** While input is locked the page has no focus; printable keys meanwhile are held for the caret (F3c point 2). */
  private holdKeys(): () => void {
    if (typeof document === "undefined" || !this.editor) return () => {};
    const page = document, dom = this.editor._tiptapEditor.view.dom;
    const listener = (event: KeyboardEvent) => {
      const target = event.target instanceof globalThis.Node ? event.target : null;
      if (event.key.length !== 1 || event.metaKey || event.ctrlKey || event.altKey || event.isComposing) return;
      if (target && target !== page.body && !dom.contains(target)) return;
      event.preventDefault();
      this.held.push(event.key);
    };
    page.addEventListener("keydown", listener, true);
    return () => page.removeEventListener("keydown", listener, true);
  }

  private typeHeld(): void {
    const editor = this.editor, text = this.held.join("");
    this.held = [];
    if (!text || !editor || this.closed || !this.writable || !editor.isEditable) return;
    const view = editor._tiptapEditor.view, { from, to } = view.state.selection;
    if (this.textInput(view.state, from, to, text)) return;
    view.dispatch(view.state.tr.insertText(text, from, to));
  }

  /** An empty block goes as one occurrence removal; the caret then goes to the shown text that the key names. */
  private async removeEmpty(blockId: string, caret: TextPoint): Promise<void> {
    await this.removeBlocks([blockId]);
    const editor = this.editor;
    if (!editor || this.closed) return;
    const locals = this.queue.template.localBlocks, doc = editor._tiptapEditor.state.doc;
    // A refused removal keeps the block and the caret in it.
    if (containerText(doc, { blockId: locals.get(blockId) ?? blockId, kind: "content", cellId: null }) !== null) return;
    const point = rekey(caret, locals), pos = point && textPosition(doc, point);
    if (pos === null || pos === undefined) return;
    editor._tiptapEditor.view.dispatch(editor._tiptapEditor.state.tr.setSelection(TextSelection.create(doc, pos)));
  }

  private key(event: KeyboardEvent): boolean {
    const mod = event.metaKey || event.ctrlKey, key = event.key.toLowerCase();
    if (mod && (key === "z" || key === "y")) {
      event.preventDefault();
      void this.navigate(event.shiftKey || key === "y" ? "redo" : "undo");
      return true;
    }
    if (event.key === "Enter" && !event.shiftKey && !mod) { event.preventDefault(); return this.enter(); }
    if (mod && event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      event.preventDefault(); void this.move(event.key === "ArrowUp" ? "up" : "down"); return true;
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      if (this.removing) { event.preventDefault(); return true; }
      const direction = event.key === "Backspace" ? "backward" : "forward";
      const state = this.editor?._tiptapEditor.state, blocks = state ? selectedBlocks(state) : null;
      if (state && blocks && this.technologyRefused(state)) { event.preventDefault(); return true; }
      if (blocks) { event.preventDefault(); if (!this.composing) this.keyRemoval(() => this.removeBlocks(blocks)); return true; }
      const range = state && !this.composing ? rangeAt(state) : null;
      if (range) {
        event.preventDefault();
        if ("reason" in range) this.refuse(range.reason, range.code);
        else this.keyRemoval(() => this.removeRange(range, null, direction));
        return true;
      }
      const empty = state && !this.composing ? emptyRemovalAt(state, direction) : null;
      if (empty) {
        event.preventDefault();
        if (empty !== "keep") this.keyRemoval(() => this.removeEmpty(empty.blockId, empty.caret));
        return true;
      }
      return this.join(direction);
    }
    if (event.key === "Tab") { event.preventDefault(); return true; }
    return false;
  }

  compositionStart(): void {
    // A composition over a range that spans containers removes nothing: the selection collapses to its end (F3c point 5).
    const view = this.editor?._tiptapEditor.view, state = view?.state;
    if (view && state && !state.selection.empty && rangeAt(state))
      view.dispatch(state.tr.setSelection(TextSelection.near(state.doc.resolve(state.selection.to), -1)));
    this.boundary(); this.composing = true; this.composed = [];
  }

  compositionEnd(): void {
    if (!this.composing) return;
    this.composing = false;
    const updates = this.composed;
    this.composed = [];
    if (updates.length) {
      const folded = foldComposition(updates);
      if ("operation" in folded) this.enqueue(folded, "composition");
      else if (folded.reason !== "composition made no change") {
        // These updates are already visible; keep them when they cannot share one replacement.
        for (const update of updates) this.enqueue(update, "composition");
      }
    }
    this.boundary();
    for (const resolve of this.waiters) resolve();
    this.waiters.clear();
  }

  /** Undo/Redo drain input, then one server history command; SessionHistory moves only after its verified result. */
  async navigate(direction: "undo" | "redo"): Promise<void> {
    if (this.closed || this.navigating || this.composing) return;
    let settled = () => {};
    this.navigation = new Promise(resolve => { settled = resolve; });
    this.boundary();
    // Input stays locked to the end, and a contenteditable that turns read-only loses focus; give it back afterwards.
    const focused = this.editor?.isFocused() ?? false;
    this.navigating = true;
    this.lock(true);
    let reservation: HistoryReservation | null = null;
    try {
      await this.flush();
      if (this.pendingNavigation) { await this.recoverNavigation(); await this.reproject(); return; }
      const actionId = this.connection.history[direction]?.actionId;
      if (!actionId) return;
      if (this.history.actionFor(direction) === actionId) reservation = this.history.reserveNavigation(direction, crypto.randomUUID());
      const base = this.queue.template.durable.workspace.projectRevision, mutationId = crypto.randomUUID();
      this.pendingNavigation = { direction, clientMutationId: mutationId, expectedActionId: actionId, baseRevision: base };
      await this.retain();
      let applied = true;
      try {
        const result = await this.connection.step(direction, mutationId, actionId, base);
        this.queue.template.adoptDurable(result.response);
      } catch (error) {
        if (error instanceof ProjectApiFailure && !["EDITOR_TOKEN_UNKNOWN", "REVISION_CONFLICT"].includes(error.code)) {
          this.pendingNavigation = null;
          await this.retain();
          if (error.code === "EDITOR_REPLACED") this.setMode("read_only");
          throw error;
        }
        applied = await this.recoverNavigation();
      }
      this.pendingNavigation = null;
      await this.retain();
      if (reservation) {
        if (applied) this.history.publishNavigation(reservation, direction, []);
        else this.history.discard(reservation);
      }
      reservation = null;
      this.navigating = false;
      await this.reproject();
    } catch (error) {
      this.port.warning(errorMessage(error));
    } finally {
      if (reservation) this.history.discard(reservation);
      this.navigating = false;
      this.lock(!this.writable);
      settled();
      if (focused && this.editor?.isEditable) this.editor.focus();
    }
  }

  /** Settle an unconfirmed undo or redo from the saved state. When that fails too it is given up, so input is never
   * blocked by it: the next save re-opens the project and the editor and its buttons follow the server again. */
  private async recoverNavigation(): Promise<boolean> {
    const pending = this.pendingNavigation;
    if (!pending) return false;
    try {
      let applied = true;
      const current = await this.connection.read();
      if (!(current.workspace.mutationReplay ?? []).some(row => row.clientMutationId === pending.clientMutationId)) {
        if (current.workspace.projectRevision === pending.baseRevision) {
          await this.connection.step(pending.direction, pending.clientMutationId, pending.expectedActionId, pending.baseRevision);
        } else { applied = false; this.port.warning(errorMessage("HISTORY_STALE")); await this.connection.reopen(); }
      } else await this.connection.reopen();
      this.queue.template.adoptDurable(this.connection.response);
      return applied;
    } catch (error) {
      this.historyNeedsRefresh = true;
      throw error;
    } finally {
      this.pendingNavigation = null;
      await this.retain();
    }
  }

  /** After a block, re-express every container with pending input from canonical text to the editor text. What text
   * cannot carry is not re-expressed: the saved state is shown and the notice names the affected text. */
  retry(keepEditorText: ReadonlySet<string> = new Set()): void {
    const editor = this.editor;
    if (!editor) return;
    const template = this.queue.template, locals = template.localBlocks, blocks = responseBlocks(template.durable), pending = template.pending;
    // As text, a refused split would delete what moved to its local block.
    if (pending.some(item => !["replace_text", "set_marks"].includes(item.intent.operation.kind))) { this.giveUp(); return; }
    const corrections: V7Intent[] = [], unchanged = new Set<string>();
    for (const key of template.unsavedBase().keys()) {
      const container = parseContainer(key), canonicalId = locals.get(container.blockId) ?? container.blockId;
      const group = blocks.get(canonicalId)?.groups.find(value => value.kind === container.kind
        && (container.kind !== "cell" || value.key === container.cellId));
      if (!group) { this.giveUp(); return; }
      const value = correctionOperation(editor._tiptapEditor.state.doc, container, contentText(group.content));
      if (value === null) { unchanged.add(key); continue; }
      if (!("operation" in value)) { console.warn(`V7 correction refused: ${value.reason}`); this.giveUp(); return; }
      corrections.push({ localId: `intent-${crypto.randomUUID()}`, operation: value.operation, prior: value.prior });
    }
    const marks = pending.filter(item => item.intent.operation.kind === "set_marks");
    if (!corrections.length) { if (marks.length) this.giveUp(); else this.discard(); return; }
    this.boundary();
    const id = this.history.commit("structure", [], null);
    if (!id) return;
    const token = this.history.capture(id, [])?.actionToken ?? 0;
    this.tokens.set(id, token);
    try { template.correct(corrections, id, token, { keepEditorText, unchanged }); }
    catch (error) { this.port.warning(errorMessage(error)); return; }
    this.action = id;
    this.boundary();
    if (marks.length) this.lost(marks, "V7_CHANGE_NOT_SAVED");
    this.schedule();
  }

  /** The block notice's first choice: the editor's text replaces whatever the saved text has become. */
  keepEditorText(): void { this.retry(new Set(this.queue.template.unsavedBase().keys())); }

  /** The block notice's second choice: unsaved input goes and the saved state is shown. */
  discard(): void { if (this.dropUnsaved()) void this.reproject(); }

  private giveUp(): void {
    const dropped = this.dropUnsaved();
    if (dropped) this.lost(dropped, "V7_CHANGE_NOT_SAVED");
  }

  private dropUnsaved(): readonly TemplateQueuedIntent[] | null {
    this.boundary();
    try { return this.queue.template.discardUnsaved(); }
    catch (error) { this.port.warning(errorMessage(error)); return null; }
  }

  close(): void {
    this.copied = null;
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    for (const resolve of this.waiters) resolve();
    this.waiters.clear();
    this.history.close();
    this.queue.close();
    this.setMode("closed");
  }
}

function parseContainer(key: string): LocalContainer {
  const value: unknown = JSON.parse(key);
  if (!Array.isArray(value) || typeof value[0] !== "string" || !["content", "caption", "cell"].includes(String(value[1]))
    || value[2] !== null && typeof value[2] !== "string") throw new Error("INVALID_RESULT");
  const kind = value[1] === "cell" ? "cell" : value[1] === "caption" ? "caption" : "content";
  return { blockId: value[0], kind, cellId: typeof value[2] === "string" ? value[2] : null };
}

/** The lines Python makes of put text: text with no line end is one line; text with line ends (CR LF, LF, a lone CR)
 * loses its lines of only white space; Enter adds a line after them. Only the caret reads this; Python owns the rule. */
function pastedLines(text: string, enter: boolean): string[] {
  const lines = !text ? [] : /[\r\n]/.test(text) ? text.replace(/\r\n?/g, "\n").split("\n").filter(line => line.trim()) : [text];
  return enter ? [...lines.length ? lines : [""], ""] : lines;
}

function rekey(point: TextPoint | null, locals: ReadonlyMap<string, string>): TextPoint | null {
  return point && { ...point, container: { ...point.container, blockId: locals.get(point.container.blockId) ?? point.container.blockId } };
}
