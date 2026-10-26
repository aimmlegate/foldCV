import { selectedFragmentToHTML, type BlockNoteEditor } from "@blocknote/core";
import { Plugin, PluginKey, TextSelection, type Transaction } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";
import type { AttachedTemplateWriter } from "../background/connection";
import { TemplateBackgroundWriter, type TemplateDraftQueue } from "../background/template-writer";
import type { WriterMode } from "../background/writer-lifecycle";
import type { RichDocumentV2, TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import { jsonWireAt } from "../contracts/lossless-json";
import { contentText, responseBlocks } from "../contracts/template-address";
import { templateProjectWire } from "../contracts/template-validate";
import { errorMessage } from "../errors/messages";
import { projectRegionChildren } from "../workbench/editor/regions";
import { SessionHistory, type HistoryKind, type HistoryReservation } from "./history";
import { RichSaveQueue, type TemplateAdoption, type TemplateQueueState } from "./save-queue";
import { restoreTableIdentities } from "./table-identity";
import type { templateSchema } from "./template-schema";
import { blockAt, containerText, copySource, correctionOperation, extractOperations, foldComposition, insertionAt, mergeAt, placementOf,
  itemContaining, replacementAt, selectedBlocks, showText, splitAt, textPoint, textPosition, type ExtractedOperation, type TextPoint } from "./v7-extraction";
import { wireMarks } from "./inline";
import type { PanelCommand } from "./synchronization";
import { employmentPanelCommands } from "./v7-panel";
import { projectTemplateBlock, templateTableIdentities } from "./v7-projection";
import { clipboardSelection, containerKey, correctionRange, verifiedRange, type ClipboardSource, type LocalContainer, type Placement,
  type V7Intent, type V7Operation } from "./v7-translation";

type Schema = typeof templateSchema;
export type TemplateEditor = BlockNoteEditor<Schema["blockSchema"], Schema["inlineContentSchema"], Schema["styleSchema"]>;
export type TemplateSessionPort = {
  status: (text: string) => void;
  warning: (text: string) => void;
  mode: (mode: WriterMode) => void;
  /** The verified canonical state now shown in the editor. */
  shown: (response: TemplateProjectResponseV1) => void;
};

const projectionMeta = "foldcv.v7.projection";
// Marks a copy from this editor; the token finds the session's own server capture, never wording.
export const clipboardType = "application/x-foldcv-v7-copy";
type Captured = { id: string; kind: ClipboardSource["kind"] };
type Copied = { token: string; text: string; capture: Promise<Captured | null> };
/** A generated replacement for one selected range, shown before anything changes. */
export type TemplateRewrite = { requestId: string; instruction: string; container: LocalContainer; start: number; end: number;
  prior: string; source: string; text: string };

/** Binds one BlockNote editor to the shared V7 queue, writer and server-retained SessionHistory. */
export class TemplateEditorSession {
  readonly writer: TemplateBackgroundWriter;
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
  private readonly generations = new Map<string, number>();
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
  private panelBusy = false;
  private closed = false;

  constructor(connection: AttachedTemplateWriter, private readonly port: TemplateSessionPort, private readonly debounce = 400) {
    this.writer = new TemplateBackgroundWriter(connection, {
      compositionEnd: () => this.composing ? new Promise(resolve => this.waiters.add(resolve)) : Promise.resolve(),
      lock: locked => this.lock(locked),
      changed: (mode, error) => { port.mode(mode); if (error) port.warning(errorMessage(error)); },
    });
    const sessionId = connection.proof?.sessionId ?? crypto.randomUUID();
    this.queue = new RichSaveQueue({ durable: this.writer.durable, sessionId, ports: this.writer.queuePorts({
      adopted: adoption => this.adopted(adoption), changed: state => this.queueChanged(state),
      retained: () => {}, released: actionId => { this.history.acknowledgeServerAction(actionId, this.tokens.get(actionId) ?? 0, false); },
    }) });
    this.writer.attach(this.queue);
    this.writer.useDraftSource(() => this.draftQueue());
    // V7 content is server-owned: actions carry no local cells, only identity, order and tokens.
    this.history = new SessionHistory(sessionId, new Map(), () => {}, () => !this.closed, `${sessionId}:${crypto.randomUUID()}`, "server");
    this.plugin = new Plugin({ key: new PluginKey("foldcv-v7-session"),
      filterTransaction: transaction => this.filter(transaction),
      appendTransaction: transactions => {
        for (const transaction of transactions) { const operations = this.stash.get(transaction); if (operations) this.accept(operations); }
        return null;
      },
      props: {
        handleKeyDown: (_view, event) => this.key(event),
        handleDOMEvents: {
          compositionstart: () => { this.compositionStart(); return false; },
          compositionend: () => { queueMicrotask(() => this.compositionEnd()); return false; },
          blur: () => { if (!this.composing) this.boundary(); return false; },
          beforeinput: (_view, event) => {
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
    if (this.writer.mode === "read_only" || this.writer.mode === "recovering") editor.isEditable = false;
  }

  /** After an outside canonical advance (export records), adopt it as base while idle and show it. */
  async refresh(): Promise<void> {
    if (await this.writer.refresh()) await this.reproject();
  }

  /** Explicit continuation after a writer fault: resolve any fenced head from the durable record, then show it. */
  async recoverWriter(): Promise<void> {
    try { await this.writer.recover(); await this.reproject(); this.schedule(); }
    catch (error) { this.port.warning(errorMessage(error)); }
  }

  /** Back from a clean detach (settings): reattach the same session and show the verified state. */
  async resume(): Promise<void> {
    await this.writer.resume();
    await this.reproject();
  }

  private lock(locked: boolean): void {
    if (this.editor) this.editor.isEditable = !locked && this.writer.mode !== "read_only";
    if (locked && this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (!locked && this.deferred.length && this.writer.writable) {
      const deferred = this.deferred;
      this.deferred = [];
      for (const { value, kind } of deferred) this.enqueue(value, kind);
    }
  }

  private refuse(reason: string): void {
    console.warn(`V7 input refused: ${reason}`);
    this.port.warning(errorMessage("V7_INPUT_UNSUPPORTED"));
  }

  private filter(transaction: Transaction): boolean {
    if (this.probe && transaction.docChanged) { this.probe.placement = placementOf(transaction.doc, this.probe.blockId); return false; }
    if (!transaction.docChanged || this.projecting || transaction.getMeta(projectionMeta)) return true;
    if (this.closed || this.navigating || this.panelBusy || !this.writer.writable) return false;
    const result = extractOperations(transaction);
    if (result.kind === "unsupported") { this.refuse(result.reason); return false; }
    if (result.operations.length) this.stash.set(transaction, result.operations);
    return true;
  }

  private accept(operations: readonly ExtractedOperation[]): void {
    for (const value of operations) {
      if (this.composing) this.composed.push(value);
      else this.enqueue(value, value.operation.kind === "replace_text" ? "typing" : "structure");
    }
  }

  private recordKinds(): Map<string, string> {
    const kinds = new Map<string, string>(), facts = jsonWireAt(this.queue.template.durable, ["workspace", "project", "facts"]);
    for (const record of jsonWireAt(facts, ["records"]).children.values()) {
      const id = jsonWireAt(record, ["id"]).value, kind = jsonWireAt(record, ["kind"]).value;
      if (typeof id === "string" && typeof kind === "string") kinds.set(id, kind);
    }
    return kinds;
  }

  /** A facts-panel command: typing drains first; input stays locked until Python's verified result is adopted and shown. */
  async panel(command: PanelCommand): Promise<void> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.writer.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    const commands = employmentPanelCommands(command, this.recordKinds());
    if (!commands) { this.refuse(`panel ${command.operation} is not a V7 employment command`); throw new Error("V7_INPUT_UNSUPPORTED"); }
    await this.command(commands.map(value => ({ operation: { kind: "builtin_panel", command: value }, prior: new Map() })), "panel");
  }

  /** One server-first action: typing drains, input locks, and Python's verified result is shown before input continues. */
  private async command(items: { operation: V7Operation; prior: ReadonlyMap<string, string> }[], kind: HistoryKind): Promise<void> {
    if (!this.editor || this.closed || this.composing || this.panelBusy || this.writer.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    await this.flush();
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
      for (const item of items) {
        const localId = `intent-${crypto.randomUUID()}`;
        this.serverFirst.add(localId);
        this.writer.input();
        this.queue.template.enqueue({ localId, operation: item.operation, prior: item.prior }, id, token);
      }
      this.action = id;
      this.boundary();
      try { await this.queue.flush(); this.port.status("Сохранено"); }
      catch (error) {
        // Typing drained first, so only this command is pending; a definitive answer drops it and input continues.
        const state = this.queue.template.state.kind;
        if (state === "rejected" || state === "conflict") this.queue.template.discardUnsaved();
        throw error;
      }
      await this.reproject();
    } finally {
      this.panelBusy = false;
      this.lock(!this.writer.writable);
      if (focused && this.editor?.isEditable) this.editor.focus();
    }
  }

  /** Editor structure commands report a refusal as a notice; the editor keeps showing the verified state. */
  private async structure(items: { operation: V7Operation; prior?: ReadonlyMap<string, string> }[]): Promise<void> {
    try { await this.command(items.map(item => ({ operation: item.operation, prior: item.prior ?? new Map() })), "structure"); }
    catch (error) { this.port.warning(errorMessage(error)); }
  }

  /** Shift+Mod+Arrow: BlockNote decides the target as usual; Python moves the block and decides any owner change. */
  async move(direction: "up" | "down"): Promise<void> {
    const editor = this.editor;
    if (!editor || this.closed || this.composing || this.panelBusy || !this.writer.writable) return;
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

  /** Remove whole selected blocks; their facts stay, as in Python's occurrence removal. */
  async removeBlocks(blockIds: string[]): Promise<void> {
    await this.structure([{ operation: { kind: "remove_occurrences", blockIds } }]);
  }

  /** The text a rewrite would read: one non-empty range inside one block or cell. */
  rewriteSource(): { container: LocalContainer; start: number; end: number; prior: string; text: string } | null {
    const editor = this.editor;
    if (!editor) return null;
    const at = insertionAt(editor._tiptapEditor.state);
    if ("reason" in at || at.start === at.end) return null;
    return { container: at.container, start: at.start, end: at.end, prior: at.prior, text: at.prior.slice(at.start, at.end) };
  }

  /** One generation for the selected range after typing drains; the document and history do not change. */
  async rewritePreview(instruction: string, requestId: string = crypto.randomUUID()): Promise<TemplateRewrite> {
    const source = this.rewriteSource();
    if (!source) throw new Error("V7_INPUT_UNSUPPORTED");
    if (this.closed || this.composing || this.panelBusy || this.writer.mode !== "normal") throw new Error("WRITER_INPUT_BLOCKED");
    await this.flush();
    const template = this.queue.template;
    const range = verifiedRange(source, { response: template.durable, map: null, locals: template.localBlocks });
    if ("conflict" in range) throw new Error("V7_INPUT_CONFLICT");
    const preview = await this.writer.rewritePreview(requestId, range, instruction);
    if (preview.source !== source.text) throw new Error("INVALID_RESULT");
    return { requestId, instruction, container: source.container, start: source.start, end: source.end, prior: source.prior,
      source: preview.source, text: preview.text };
  }

  cancelRewrite(requestId: string): Promise<boolean> { return this.writer.rewriteCancel(requestId); }

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
    if (!editor || !data || this.closed) return false;
    event.preventDefault();
    if (cut && (!copySource(view.state) || !this.writer.writable || this.composing || this.panelBusy)) {
      this.refuse("cut needs whole blocks or text inside one block"); return true;
    }
    const { clipboardHTML, externalHTML, markdown } = selectedFragmentToHTML(view, editor);
    data.clearData();
    data.setData("blocknote/html", clipboardHTML);
    data.setData("text/html", externalHTML);
    data.setData("text/plain", markdown);
    const copied = this.copySelection(cut);
    if (copied) data.setData(clipboardType, JSON.stringify({ projectId: this.writer.connection.api.project, token: copied.token }));
    return true;
  }

  /** Start a same-project copy of the selection: Python captures it after typing drains. A cut removes the source
   * once the capture exists. Null when the selection names nothing Python copies. */
  copySelection(cut = false): (Copied & { done: Promise<void> }) | null {
    const editor = this.editor;
    if (!editor || this.closed || !this.writer.writable || this.composing || this.panelBusy) return null;
    const state = editor._tiptapEditor.state, source = copySource(state);
    if (!source) return null;
    const previous = this.copied, capture = this.capture(source);
    const copied: Copied = { token: crypto.randomUUID(), text: state.doc.textBetween(state.selection.from, state.selection.to, "\n"), capture };
    this.copied = copied;
    if (previous) void previous.capture.then(value => value ? this.writer.releaseClipboard(value.id) : undefined).catch(() => {});
    return { ...copied, done: cut ? this.cut(source, capture) : capture.then(() => {}) };
  }

  /** Python captures the copied source against the drained verified state; a failed capture leaves plain text only. */
  private async capture(source: ClipboardSource): Promise<Captured | null> {
    try {
      await this.flush();
      const template = this.queue.template;
      const selection = clipboardSelection(source, { response: template.durable, map: null, locals: template.localBlocks });
      if ("conflict" in selection) { console.warn(`V7 copy not captured: ${selection.conflict}`); return null; }
      const captured = await this.writer.captureClipboard(selection);
      return { id: captured.clipboardCaptureId, kind: source.kind };
    } catch (error) {
      console.warn(`V7 copy not captured: ${error instanceof Error ? error.message : String(error)}`);
      return null;
    }
  }

  /** Cut removes the source only after Python holds the copy. */
  private async cut(source: ClipboardSource, capture: Promise<Captured | null>): Promise<void> {
    if (!await capture) { this.port.warning(errorMessage("V7_INPUT_UNSUPPORTED")); return; }
    if (source.kind === "blocks") { await this.removeBlocks(source.blockIds); return; }
    await this.structure([{ operation: { kind: "replace_text", container: source.container, start: source.start, end: source.end, text: "",
      styles: wireMarks({}), side: null }, prior: new Map([[containerKey(source.container), source.prior]]) }]);
  }

  private paste(event: ClipboardEvent): boolean {
    const data = event.clipboardData;
    if (!this.editor || !data || this.closed) return false;
    event.preventDefault();
    if (!this.writer.writable || this.composing || this.panelBusy) return true;
    let marker: unknown = null;
    try { marker = JSON.parse(data.getData(clipboardType) || "null"); } catch { marker = null; }
    const own = this.copied && typeof marker === "object" && marker !== null && Reflect.get(marker, "token") === this.copied.token
      && Reflect.get(marker, "projectId") === this.writer.connection.api.project ? this.copied : null;
    void this.pasteFrom(own, own?.text ?? data.getData("text/plain"));
    return true;
  }

  /** Same-project copies paste through Python with their bindings; other text enters as typing in one block. */
  async pasteFrom(copied: Copied | null, text: string): Promise<void> {
    const captured = copied ? await copied.capture : null, editor = this.editor;
    if (!editor || this.closed) return;
    const state = editor._tiptapEditor.state;
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
    // Several paragraphs need a block-boundary representation Python does not offer yet.
    if (text.includes("\n")) { this.refuse("multi-paragraph text paste"); return; }
    if (text) editor._tiptapEditor.view.dispatch(state.tr.insertText(text));
  }

  /** Moving the caret to another container ends the current typing action, as in the V1 editor. */
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
    if (!this.writer.writable || this.deferred.length) { this.deferred.push({ value, kind }); return; }
    const now = Date.now();
    if (kind === "structure" || now - this.lastInput > 500) this.boundary();
    this.lastInput = now;
    const id = this.history.commit(kind, [], kind === "structure" ? null : `typing:${this.group}`);
    if (!id) { this.refuse("history is closed or reserved"); return; }
    if (this.action !== id) { if (this.action) this.queue.template.seal(this.action); this.action = id; }
    const token = this.history.capture(id, [])?.actionToken ?? 0;
    this.tokens.set(id, token);
    this.writer.input();
    this.queue.template.enqueue({ localId: `intent-${crypto.randomUUID()}`, operation: value.operation, prior: value.prior }, id, token);
    if (kind === "structure") this.boundary();
    this.retainSoon();
    this.schedule();
  }

  private retaining = false;
  /** Every accepted input is retained locally before it is saved; writes in one task coalesce. */
  private retainSoon(): void {
    if (this.retaining || this.closed) return;
    this.retaining = true;
    queueMicrotask(() => {
      this.retaining = false;
      if (!this.closed) void this.writer.retain().catch(error => this.port.warning(errorMessage(error)));
    });
  }

  /** The draft's queue record: pending intents, the frozen head, local block IDs and the editor text of each touched container. */
  private draftQueue(): TemplateDraftQueue | null {
    // Server-first commands are input-locked and never retained; only text input is re-expressed after a crash.
    const template = this.queue.template, pending = template.pending.flatMap(item =>
      textOperation(item.intent.operation) && !this.serverFirst.has(item.intent.localId) ? [item] : []);
    const unqueued = [...this.deferred.map(item => item.value), ...this.composed];
    if (!pending.length && !unqueued.length) return null;
    const containers = new Map<string, LocalContainer>();
    for (const value of [...pending.map(item => item.intent), ...unqueued]) {
      for (const key of value.prior.keys()) containers.set(key, parseContainer(key));
      if (value.operation.kind === "split_block") {
        const created: LocalContainer = { blockId: value.operation.created, kind: "content", cellId: null };
        containers.set(containerKey(created), created);
      }
    }
    const doc = this.editor?._tiptapEditor.state.doc;
    const editorTexts = [...containers.values()].flatMap(container => {
      const text = doc ? containerText(doc, container) : null;
      return text === null ? [] : [{ container, text }];
    });
    const first = pending[0];
    const head = first?.frozen ? { clientMutationId: first.clientMutationId, preparationWire: JSON.stringify(first.frozen.request.preparation),
      stage: first.stage === "prepared" ? "prepared" as const : "frozen" as const } : null;
    return { schemaVersion: 1, head, editorTexts, locals: [...template.localBlocks].map(([local, canonical]) => ({ local, canonical })),
      intents: pending.map(item => ({ localId: item.intent.localId, actionId: item.actionId, actionToken: item.actionToken,
        clientMutationId: item.clientMutationId, operation: wireOperation(textOperation(item.intent.operation)),
        prior: wirePrior(item.intent.prior) })) };
  }

  /** A recovering opening: show the retained editor texts, reattach, and save them as corrections against the saved state.
   * A container whose saved text is none of its own pending states needs the user's choice (keep editor text or use saved). */
  async recoverDraft(choice: "keep" | "saved" | null = null): Promise<{ conflicts: number }> {
    const editor = this.editor, record = this.writer.connection.local?.payload.templateQueue;
    if (!editor || this.writer.mode !== "recovering") return { conflicts: 0 };
    if (!record) { await this.writer.reattach(); await this.reproject(); await this.writer.clearCleanDraft(); return { conflicts: 0 }; }
    const structural = record.intents.filter(item => item.operation.kind === "split_block" || item.operation.kind === "merge_blocks");
    if (structural.length) {
      // Text corrections cannot prove where an unacknowledged split or merge ended up.
      if (choice !== "saved") return { conflicts: structural.length };
      await this.writer.discardDraft(); await this.reproject();
      return { conflicts: 0 };
    }
    const locals = new Map(record.locals.map(item => [item.local, item.canonical]));
    const canonical = (container: LocalContainer): LocalContainer => ({ ...container, blockId: locals.get(container.blockId) ?? container.blockId });
    const blocks = responseBlocks(this.writer.durable), states = new Map<string, Set<string>>();
    for (const intent of record.intents) for (const prior of intent.prior) {
      const key = containerKey(canonical(prior.container));
      states.set(key, (states.get(key) ?? new Set()).add(prior.text));
    }
    const saved = (container: LocalContainer) => {
      const group = blocks.get(container.blockId)?.groups.find(value => value.kind === container.kind
        && (container.kind !== "cell" || value.key === container.cellId));
      return group ? contentText(group.content) : null;
    };
    const texts = record.editorTexts.map(item => ({ container: canonical(item.container), text: item.text }));
    const conflicts = texts.filter(item => {
      const current = saved(item.container);
      return current === null || current !== item.text && !states.get(containerKey(item.container))?.has(current);
    });
    if (conflicts.length && choice === null) return { conflicts: conflicts.length };
    if (choice === "keep" && texts.some(item => saved(item.container) === null)) return { conflicts: conflicts.length };
    const shown = texts.filter(item => saved(item.container) !== null && (choice === "keep" || !conflicts.includes(item)));
    this.projecting = true;
    try { editor.transact(tr => { tr.setMeta(projectionMeta, true); for (const item of shown) showText(tr, item.container, item.text); }); }
    finally { this.projecting = false; }
    await this.writer.reattach();
    const corrections: V7Intent[] = [];
    for (const item of shown) {
      const value = correctionOperation(editor._tiptapEditor.state.doc, item.container, saved(item.container) ?? "");
      if (value === null) continue;
      if (!("operation" in value)) { this.refuse(value.reason); continue; }
      corrections.push({ localId: `intent-${crypto.randomUUID()}`, operation: value.operation, prior: value.prior });
    }
    if (corrections.length) {
      this.boundary();
      const id = this.history.commit("structure", [], null);
      if (id) {
        const token = this.history.capture(id, [])?.actionToken ?? 0;
        this.tokens.set(id, token);
        for (const intent of corrections) { this.writer.input(); this.queue.template.enqueue(intent, id, token); }
        this.action = id;
        this.boundary();
      }
    }
    this.retainSoon();
    await this.flush();
    if (!corrections.length) await this.reproject();
    await this.writer.clearCleanDraft();
    return { conflicts: 0 };
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.port.status("Изменения сохраняются…");
    if (this.composing || this.closed) return;
    this.timer = setTimeout(() => { this.timer = null; void this.flush().catch(() => {}); }, this.debounce);
  }

  /** Drain buffered input; a fenced head is resolved from the durable record before anything else moves. */
  async flush(): Promise<void> {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    try {
      await this.queue.flush();
      this.port.status("Сохранено");
    } catch (error) {
      // The head may now be prepared: keep the draft's record of it current.
      this.retainSoon();
      this.port.status(errorMessage(error));
      if (error instanceof Error && error.message === "V7_OUTCOME_UNKNOWN") {
        await this.writer.recover();
        await this.queue.flush();
        this.port.status("Сохранено");
        return;
      }
      throw error;
    }
  }

  private adopted(adoption: TemplateAdoption): void {
    const ack = adoption.verification?.kind === "committed" ? adoption.verification.acknowledgment.localHistoryAck : null;
    if (ack) this.generations.set(ack.actionId, ack.generation);
    if (this.queue.template.pending.length) { this.retainSoon(); return; }
    queueMicrotask(() => { void this.reproject(); });
    // Everything retained is saved; a draft remains only while the editor holds unqueued input.
    if (!this.composing && !this.deferred.length) void this.writer.clearCleanDraft().catch(error => this.port.warning(errorMessage(error)));
  }

  private queueChanged(state: TemplateQueueState): void {
    if (state.kind === "conflict") this.port.warning(errorMessage("V7_INPUT_CONFLICT"));
    else if (state.kind === "rejected") this.port.warning(errorMessage("V7_INPUT_REJECTED"));
    else if (state.kind === "fenced") this.port.warning(errorMessage("V7_OUTCOME_UNKNOWN"));
  }

  /** Containers are re-projected from canonical content only after the queue drains; local block IDs end there. */
  async reproject(): Promise<boolean> {
    const editor = this.editor, durable = this.queue.template.durable;
    if (!editor || this.closed || this.composing || this.queue.template.pending.length) return false;
    const response = await templateProjectWire(durable), project = response?.workspace.project;
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
    if (!editor) return true;
    const result = splitAt(editor._tiptapEditor.state, `local-${crypto.randomUUID()}`);
    if ("reason" in result) this.refuse(result.reason);
    else editor._tiptapEditor.view.dispatch(result.transaction);
    return true;
  }

  /** Backspace/Delete at a block edge merge siblings; elsewhere the default deletion is plain text input. */
  join(direction: "backward" | "forward"): boolean {
    const editor = this.editor;
    if (!editor || this.composing) return false;
    const state = editor._tiptapEditor.state, result = mergeAt(state, direction);
    if ("transaction" in result) { editor._tiptapEditor.view.dispatch(result.transaction); return true; }
    if (/caret is not at the block edge|structure input needs a caret/.test(result.reason)) return false;
    this.refuse(result.reason);
    return true;
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
      const blocks = this.editor ? selectedBlocks(this.editor._tiptapEditor.state) : null;
      if (blocks) { event.preventDefault(); if (!this.composing) void this.removeBlocks(blocks); return true; }
      return this.join(event.key === "Backspace" ? "backward" : "forward");
    }
    if (event.key === "Tab") { event.preventDefault(); return true; }
    return false;
  }

  compositionStart(): void { this.boundary(); this.composing = true; this.composed = []; }

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
    this.boundary();
    this.navigating = true;
    // The command locks input, and a contenteditable that turns read-only loses focus; give it back afterwards.
    const focused = this.editor?.isFocused() ?? false;
    let reservation: HistoryReservation | null = null;
    try {
      await this.flush();
      const actionId = this.history.actionFor(direction), generation = actionId ? this.generations.get(actionId) : undefined;
      if (!actionId || generation === undefined) return;
      reservation = this.history.reserveNavigation(direction, `${actionId}:${direction}:${crypto.randomUUID()}`);
      if (!reservation) throw new Error("WRITER_RECOVERY_REQUIRED");
      const view = await this.writer.history(direction, actionId, generation);
      if (view.localHistoryAck) this.generations.set(view.localHistoryAck.actionId, view.localHistoryAck.generation);
      if (!this.history.publishNavigation(reservation, direction, [])) throw new Error("WRITER_RECOVERY_REQUIRED");
      reservation = null;
      this.navigating = false;
      await this.reproject();
    } catch (error) {
      this.port.warning(errorMessage(error));
    } finally {
      if (reservation) this.history.discard(reservation);
      this.navigating = false;
      if (focused && this.editor?.isEditable) this.editor.focus();
    }
  }

  /** After a block, re-express every container with pending input from canonical text to the editor text. */
  retry(keepEditorText: ReadonlySet<string> = new Set()): void {
    const editor = this.editor;
    if (!editor) return;
    const template = this.queue.template, locals = template.localBlocks, blocks = responseBlocks(template.durable);
    const corrections: V7Intent[] = [], unchanged = new Set<string>();
    for (const key of template.unsavedBase().keys()) {
      const container = parseContainer(key), canonicalId = locals.get(container.blockId) ?? container.blockId;
      const group = blocks.get(canonicalId)?.groups.find(value => value.kind === container.kind
        && (container.kind !== "cell" || value.key === container.cellId));
      if (!group) { this.port.warning(errorMessage("V7_CORRECTION_NOT_ALLOWED")); return; }
      const value = correctionOperation(editor._tiptapEditor.state.doc, container, contentText(group.content));
      if (value === null) { unchanged.add(key); continue; }
      if (!("operation" in value)) { this.refuse(value.reason); return; }
      corrections.push({ localId: `intent-${crypto.randomUUID()}`, operation: value.operation, prior: value.prior });
    }
    this.boundary();
    const id = this.history.commit("structure", [], null);
    if (!id) return;
    const token = this.history.capture(id, [])?.actionToken ?? 0;
    this.tokens.set(id, token);
    try { template.correct(corrections, id, token, { keepEditorText, unchanged }); }
    catch (error) { this.port.warning(errorMessage(error)); return; }
    this.action = id;
    this.boundary();
    this.schedule();
  }

  close(): void {
    const copied = this.copied;
    this.copied = null;
    if (copied) void copied.capture.then(value => value ? this.writer.releaseClipboard(value.id) : undefined).catch(() => {});
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    for (const resolve of this.waiters) resolve();
    this.waiters.clear();
    this.history.close();
    this.queue.close();
    this.writer.close();
  }
}

function wirePrior(prior: ReadonlyMap<string, string>): TemplateDraftQueue["intents"][number]["prior"] {
  const [first, second, ...rest] = [...prior].map(([key, text]) => ({ container: parseContainer(key), text }));
  if (!first || rest.length) throw new Error("INVALID_RESULT");
  return second ? [first, second] : [first];
}

type TextOperation = Extract<V7Operation, { kind: "replace_text" | "set_marks" | "split_block" | "merge_blocks" }>;
function textOperation(operation: V7Operation): TextOperation | null {
  return operation.kind === "replace_text" || operation.kind === "set_marks" || operation.kind === "split_block"
    || operation.kind === "merge_blocks" ? operation : null;
}
function wireOperation(operation: TextOperation | null): TemplateDraftQueue["intents"][number]["operation"] {
  if (!operation) throw new Error("INVALID_RESULT");
  return structuredClone(operation);
}

function parseContainer(key: string): LocalContainer {
  const value: unknown = JSON.parse(key);
  if (!Array.isArray(value) || typeof value[0] !== "string" || !["content", "caption", "cell"].includes(String(value[1]))
    || value[2] !== null && typeof value[2] !== "string") throw new Error("INVALID_RESULT");
  const kind = value[1] === "cell" ? "cell" : value[1] === "caption" ? "caption" : "content";
  return { blockId: value[0], kind, cellId: typeof value[2] === "string" ? value[2] : null };
}

function rekey(point: TextPoint | null, locals: ReadonlyMap<string, string>): TextPoint | null {
  return point && { ...point, container: { ...point.container, blockId: locals.get(point.container.blockId) ?? point.container.blockId } };
}
