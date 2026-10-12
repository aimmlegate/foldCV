import { createExtension } from "@blocknote/core";
import type { Node as ProseNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";

export type FieldProjection = { fieldId: string; slotId: string; label: string; text: string };
export type FieldSpan = { fieldId: string; range: { start: number; end: number }; capturedText: string };
export type CapturedSelection = { direction: "forward" | "backward"; spans: FieldSpan[] };
export type FieldPatch = { fieldId: string; text: string; capturedText: string };
type PositionedField = FieldProjection & { from: number; to: number };
type AdapterState = { localVersion: number };
export type AdapterCallbacks = {
  buffer: (fields: FieldProjection[]) => void;
  selection: (selection: CapturedSelection | null) => void;
  slot: (slotId: string | null) => void;
  departure: (slotId: string) => void;
  restore: (slotId: string) => void;
  completion?: (fieldId: string, reason: "field" | "paragraph") => void;
};

function identity(value: unknown): Pick<FieldProjection, "fieldId" | "slotId" | "label"> | null {
  if (typeof value !== "object" || value === null) return null;
  const props = value as Record<string, unknown>;
  return typeof props.fieldId === "string" && typeof props.slotId === "string" && typeof props.label === "string"
    ? { fieldId: props.fieldId, slotId: props.slotId, label: props.label } : null;
}

export function positionedFields(document: ProseNode): PositionedField[] {
  const fields: PositionedField[] = [];
  document.descendants((node, position) => {
    if (node.type.name !== "resumeField") return;
    const props = identity(node.attrs);
    if (props) fields.push({ ...props, from: position + 1, to: position + 1 + node.content.size, text: node.textContent });
  });
  return fields;
}

function snap(text: string, offset: number, towardEnd: boolean): number {
  const points = [0, ...Array.from(new Intl.Segmenter("ru", { granularity: "grapheme" }).segment(text), part => part.index), text.length];
  return towardEnd ? points.find(point => point >= offset) ?? text.length : points.filter(point => point <= offset).at(-1) ?? 0;
}

export function capture(document: ProseNode, anchor: number, head: number): CapturedSelection | null {
  if (anchor === head) return null;
  const from = Math.min(anchor, head), to = Math.max(anchor, head);
  const spans: FieldSpan[] = [];
  for (const field of positionedFields(document)) {
    if (to <= field.from || from >= field.to) continue;
    const start = snap(field.text, Math.max(0, from - field.from), false);
    const end = snap(field.text, Math.min(field.text.length, to - field.from), true);
    spans.push({ fieldId: field.fieldId, range: { start, end }, capturedText: field.text.slice(start, end) });
  }
  return spans.length ? { direction: anchor <= head ? "forward" : "backward", spans } : null;
}

export function createAdapter(fields: readonly FieldProjection[], callbacks: () => AdapterCallbacks) {
  const key = new PluginKey<AdapterState>("foldcv-fields");
  const order = fields.map(field => field.fieldId);
  let activeSlot: string | null = null;
  let activeField: string | null = null;
  let composing = false;
  let ownedIntent: string | null = null;
  let lastSent = 0;
  let currentView: EditorView | null = null;

  function move(slot: string | null) {
    if (activeSlot === slot) return;
    if (activeSlot) callbacks().departure(activeSlot);
    activeSlot = slot;
    callbacks().slot(slot);
  }
  function emit(view: EditorView) {
    const version = key.getState(view.state)?.localVersion ?? 0;
    if (!composing && version !== lastSent) {
      lastSent = version;
      callbacks().buffer(positionedFields(view.state.doc).map(({ from: _from, to: _to, ...field }) => field));
    }
  }
  function restore() {
    if (activeSlot && !composing) callbacks().restore(activeSlot);
  }

  const plugin = new Plugin<AdapterState>({
    key,
    state: { init: () => ({ localVersion: 0 }), apply: (transaction, previous) => ({
      localVersion: previous.localVersion + (transaction.docChanged && transaction.getMeta("foldcv.patch") !== true ? 1 : 0),
    }) },
    filterTransaction: transaction => {
      if (!transaction.docChanged) return true;
      const projected = positionedFields(transaction.doc);
      return transaction.doc.firstChild?.childCount === order.length && projected.length === order.length
        && projected.every((field, index) => field.fieldId === order[index] && field.slotId === fields[index]?.slotId);
    },
    props: {
      handleKeyDown: (view, event) => {
        if ((event.metaKey || event.ctrlKey) && ["z", "y"].includes(event.key.toLowerCase())) {
          event.preventDefault();
          if (event.key.toLowerCase() === "z" && !event.shiftKey) restore();
          return true;
        }
        if (event.key === "Enter" && !event.isComposing && !composing) {
          event.preventDefault(); view.dispatch(view.state.tr.insertText("\n"));
          if (activeField) callbacks().completion?.(activeField, "paragraph");
          return true;
        }
        return false;
      },
      handleDOMEvents: {
        compositionstart: () => { composing = true; callbacks().selection(null); return false; },
        compositionend: view => { composing = false; queueMicrotask(() => emit(view)); return false; },
        beforeinput: (_view, event) => {
          if (event instanceof InputEvent && ["historyUndo", "historyRedo"].includes(event.inputType)) {
            event.preventDefault(); if (event.inputType === "historyUndo") restore(); return true;
          }
          return false;
        },
        paste: (view, event) => {
          event.preventDefault();
          const text = event.clipboardData?.getData("text/plain").replace(/\r\n?/g, "\n") ?? "";
          if (text) view.dispatch(view.state.tr.insertText(text));
          return true;
        },
        blur: (view, event) => {
          if (event instanceof FocusEvent && event.relatedTarget instanceof Element
            && event.relatedTarget.closest("[data-slot-owner]")?.getAttribute("data-slot-owner") === activeSlot) return false;
          queueMicrotask(() => {
            if (ownedIntent === activeSlot && activeSlot !== null) return;
            const focused = view.dom.ownerDocument.activeElement;
            if (focused instanceof Element && focused.closest("[data-slot-owner]")?.getAttribute("data-slot-owner") === activeSlot) return;
            if (!focused || !view.dom.contains(focused)) move(null);
          });
          return false;
        },
      },
    },
    view: view => {
      currentView = view;
      const owner = (target: EventTarget | null) => target instanceof Element
        ? target.closest("[data-slot-owner]")?.getAttribute("data-slot-owner") ?? null : null;
      const focus = (event: FocusEvent) => {
        const slot = owner(event.target);
        if (slot) move(slot);
        else if (event.target instanceof Node && !view.dom.contains(event.target)) move(null);
      };
      const pointer = (event: PointerEvent) => { ownedIntent = owner(event.target); if (ownedIntent) move(ownedIntent); };
      const history = (event: KeyboardEvent) => {
        if (!owner(event.target) || (event.target instanceof Node && view.dom.contains(event.target))) return;
        if ((event.ctrlKey || event.metaKey) && ["z", "y"].includes(event.key.toLowerCase())) {
          event.preventDefault(); if (event.key.toLowerCase() === "z" && !event.shiftKey) restore();
        }
      };
      view.dom.ownerDocument.addEventListener("focusin", focus);
      view.dom.ownerDocument.addEventListener("pointerdown", pointer, true);
      view.dom.ownerDocument.addEventListener("keydown", history, true);
      return { update: next => {
        const selected = next.state.selection;
        const field = positionedFields(next.state.doc).find(field => selected.head >= field.from && selected.head <= field.to);
        if (next.hasFocus()) {
          if (activeField && activeField !== field?.fieldId) callbacks().completion?.(activeField, "field");
          activeField = field?.fieldId ?? null;
          move(field?.slotId ?? null);
        }
        callbacks().selection(composing ? null : capture(next.state.doc, selected.anchor, selected.head));
        emit(next);
      }, destroy: () => {
        view.dom.ownerDocument.removeEventListener("focusin", focus);
        view.dom.ownerDocument.removeEventListener("pointerdown", pointer, true);
        view.dom.ownerDocument.removeEventListener("keydown", history, true);
        currentView = null;
      } };
    },
  });
  const extension = createExtension({ key: "foldcv-fields", prosemirrorPlugins: [plugin] });
  return {
    extension,
    capture: () => currentView && !composing ? capture(currentView.state.doc, currentView.state.selection.anchor, currentView.state.selection.head) : null,
    isComposing: () => composing,
    read: () => currentView ? positionedFields(currentView.state.doc) : [],
    patch: (patches: readonly FieldPatch[]) => {
      if (!currentView || composing) return false;
      const view = currentView;
      const projected = positionedFields(view.state.doc);
      const changes = patches.map(patch => ({ patch, field: projected.find(field => field.fieldId === patch.fieldId) }));
      if (changes.some(({ field, patch }) => !field || field.text !== patch.capturedText)) return false;
      const transaction = view.state.tr.setMeta("foldcv.patch", true);
      for (const { field, patch } of changes.sort((a, b) => (b.field?.from ?? 0) - (a.field?.from ?? 0))) {
        if (field && field.text !== patch.text) transaction.insertText(patch.text.replace(/\r\n?/g, "\n"), field.from, field.to);
      }
      if (transaction.docChanged) view.dispatch(transaction);
      return true;
    },
  };
}
