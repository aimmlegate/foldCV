import { BlockNoteSchema, createExtension, defaultBlockSpecs, defaultInlineContentSpecs, type Block } from "@blocknote/core";
import { createReactBlockSpec, createReactInlineContentSpec, useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { createRoot } from "react-dom/client";
import { useEffect, useMemo, useState } from "react";
import { SessionHistory, type CellChange, type CellValue, type DependencyCapture, type HistoryKind } from "./history";
import { readTableIdentities, restoreTableIdentities, tableIdentityAttributes, tableIdentityPlugin, type TableRowIdentity } from "./table-identity";
import "@blocknote/shadcn/style.css";
import "../shell/theme.css";
import "./spike.css";

const region = createReactBlockSpec({ type: "region", content: "none",
  propSchema: { role: { default: "main", values: ["header", "sidebar", "main"] } },
}, { render: ({ block }) => <div className="rich-region-label" contentEditable={false}>{block.props.role}</div> });
const section = createReactBlockSpec({ type: "section", content: "inline",
  propSchema: { recordId: { default: "" } },
}, { render: ({ contentRef }) => <h2 className="rich-section-title" ref={contentRef} /> });
const factField = createReactInlineContentSpec({ type: "factField", content: "styled", propSchema: {
  bindingId: { default: "" }, recordId: { default: "" }, fieldKey: { default: "" }, syncedFactRevision: { default: 1 },
} }, { render: ({ inlineContent, contentRef }) => <span data-binding-id={inlineContent.props.bindingId}
  data-record-id={inlineContent.props.recordId} data-field-key={inlineContent.props.fieldKey} ref={contentRef} /> });
const { file: _file, audio: _audio, video: _video, heading: defaultHeading, ...supported } = defaultBlockSpecs;
const { isToggleable: _toggleHeading, ...headingProps } = defaultHeading.config.propSchema;
const heading = createReactBlockSpec({ type: "heading", content: "inline",
  propSchema: { ...headingProps, level: { default: 1, values: [1, 2, 3] } },
}, { render: ({ block, contentRef }) => block.props.level === 1 ? <h1 ref={contentRef} />
  : block.props.level === 2 ? <h2 ref={contentRef} /> : <h3 ref={contentRef} /> });
const schema = BlockNoteSchema.create({ blockSpecs: { ...supported, heading: heading(), region: region(), section: section() },
  inlineContentSpecs: { ...defaultInlineContentSpecs, factField } });
type SpikeBlock = Block<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;
type StoredBlock = { block: SpikeBlock; children: string[]; tableIds: TableRowIdentity[] | null };
type SpikeAPI = {
  summary: () => { position: number; actions: number; clock: number; composing: boolean; historyDisabled: boolean; facts: Record<string, CellValue>; factRevisions: Record<string, number>; roots: string[] };
  capture: () => DependencyCapture | null;
  reconcile: (ticket: DependencyCapture) => string;
  selectAcrossRegions: () => string[];
  tables: () => Record<string, TableRowIdentity[]>;
};
declare global { interface Window { foldcvSpike?: SpikeAPI } }

function Spike() {
  const [, refresh] = useState(0);
  const bridge = useMemo(() => ({ composing: false, group: 0, kind: "typing" as HistoryKind,
    lastTypingAt: 0,
    observing: false, replaying: false, ticket: null as DependencyCapture | null,
    current: new Map<string, CellValue>(), values: new Map<string, StoredBlock>(),
    factRevisions: new Map<string, number>([["fact:name", 1], ["fact:period", 1], ["fact:claim-owner", 1]]),
    history: null as SessionHistory | null, complete: () => {}, undo: (): boolean => false, redo: (): boolean => false }), []);
  const extension = useMemo(() => createExtension({ key: "foldcv-rich-proof", tiptapExtensions: [tableIdentityAttributes],
    prosemirrorPlugins: [tableIdentityPlugin(), new Plugin({
    key: new PluginKey("foldcv-rich-proof"),
    filterTransaction: transaction => {
      if (!transaction.docChanged) return true;
      const group = transaction.doc.firstChild;
      if (!group || group.childCount !== 3) return false;
      return ["header", "sidebar", "main"].every((id, index) => {
        const root = group.child(index);
        const actualId: unknown = root.attrs["id"];
        return actualId === id && root.firstChild?.type.name === "region";
      });
    }, props: {
      handleKeyDown: (_view, event) => {
        if (!(event.ctrlKey || event.metaKey) || !["z", "y"].includes(event.key.toLowerCase())) return false;
        event.preventDefault();
        if (!bridge.composing) {
          bridge.group++;
          if (event.key.toLowerCase() === "y" || event.shiftKey) bridge.redo(); else bridge.undo();
        }
        return true;
      },
      handleDOMEvents: {
        compositionstart: () => { bridge.group++; bridge.composing = true; return false; },
        compositionend: () => { queueMicrotask(() => { bridge.complete(); bridge.composing = false; bridge.group++; }); return false; },
        beforeinput: (_view, event) => {
          if (!(event instanceof InputEvent) || !["historyUndo", "historyRedo"].includes(event.inputType)) return false;
          event.preventDefault();
          if (!bridge.composing) { bridge.group++; if (event.inputType === "historyUndo") bridge.undo(); else bridge.redo(); }
          return true;
        },
        blur: () => { if (!bridge.composing) bridge.group++; return false; },
      },
    },
  })] }), [bridge]);
  const editor = useCreateBlockNote({ schema, disableExtensions: ["history"], extensions: [extension], initialContent: [
    { id: "header", type: "region", props: { role: "header" }, children: [
      { id: "name", type: "paragraph", content: [{ type: "factField", props: { bindingId: "name-binding", recordId: "candidate-1", fieldKey: "name", syncedFactRevision: 1 }, content: [{ type: "text", text: "Alex Example", styles: { italic: true } }] }] },
      { id: "title", type: "heading", props: { level: 1 }, content: "Engineer" },
    ] },
    { id: "sidebar", type: "region", props: { role: "sidebar" }, children: [
      { id: "education", type: "section", props: { recordId: "education-1" }, content: "Education", children: [
        { id: "degree", type: "paragraph", content: "Example University · May 2018" },
        { id: "language", type: "paragraph", content: "English · level unknown" },
      ] },
    ] },
    { id: "main", type: "region", props: { role: "main" }, children: [
      { id: "job", type: "section", props: { recordId: "job-1" }, content: "Example Company", children: [
        { id: "narrative", type: "paragraph", content: [ { type: "text", text: "Alex leads ", styles: { bold: true } }, { type: "link", href: "https://example.com", content: "work" } ] },
        { id: "period", type: "paragraph", content: "January–April 2024" },
        { id: "list", type: "bulletListItem", content: "Nested work", children: [ { id: "nested", type: "checkListItem", props: { checked: true }, content: "Checked detail" } ] },
        { id: "table", type: "table", content: { type: "tableContent", rows: [ { cells: ["Language", "Scope"] }, { cells: ["Python", "Work"] } ] } },
        { id: "image", type: "image", props: { url: "/rich-proof.png", name: "Synthetic local asset", caption: "Local image proof", previewWidth: 120 } },
      ] },
      { id: "job-2", type: "section", props: { recordId: "job-2" }, content: "Second Company", children: [
        { id: "second-detail", type: "paragraph", content: "Independent second job" },
      ] },
      { id: "other", type: "paragraph", content: "Other job stays independent" },
    ] },
  ] }, []);

  useEffect(() => {
    editor.transact(tr => tr.setMeta("foldcv.table.initialize", true));
    function project(blocks: readonly SpikeBlock[]): Map<string, CellValue> {
      const tables = editor.transact(tr => readTableIdentities(tr.doc));
      const result = new Map<string, CellValue>();
      const visit = (block: SpikeBlock) => {
        const logical = block.type === "paragraph" ? { ...block, content: block.content.map(inline => inline.type === "factField"
          ? { ...inline, props: { ...inline.props, syncedFactRevision: 1 } } : inline) } : block;
        const stored: StoredBlock = { block: { ...logical, children: [] }, children: block.children.map(child => child.id), tableIds: tables.get(block.id) ?? null };
        const value = JSON.stringify(stored);
        bridge.values.set(value, stored);
        result.set(`block:${block.id}`, value);
        block.children.forEach(visit);
      };
      blocks.forEach(visit);
      return result;
    }
    bridge.current = project(editor.document);
    bridge.current.set("fact:name", "Alex Example");
    bridge.current.set("fact:period", "January–April 2024");
    bridge.current.set("fact:education", "2018-05");
    bridge.current.set("fact:language-level", null);
    bridge.current.set("fact:claim-owner", "job-1");
    bridge.current.set("evidence:claim-source", "source-job-1");
    function rebuild(id: string): SpikeBlock {
      const value = bridge.current.get(`block:${id}`);
      const stored = value ? bridge.values.get(value) : undefined;
      if (!stored) throw new Error(`Missing block ${id}`);
      return { ...stored.block, children: stored.children.map(rebuild) };
    }
    const history = new SessionHistory(crypto.randomUUID(), bridge.current, changes => {
      for (const change of changes) {
        bridge.current.set(change.key, change.after);
        if (change.key.startsWith("fact:") && change.before !== change.after) bridge.factRevisions.set(change.key, (bridge.factRevisions.get(change.key) ?? 1) + 1);
      }
      if (!bridge.observing && changes.some(change => change.key.startsWith("block:") || change.key === "fact:name")) {
        const changed = new Set(changes.filter(change => change.key.startsWith("block:")).map(change => change.key.slice(6)));
        const targets: string[] = [];
        const visit = (id: string) => {
          if (changed.has(id)) { targets.push(id); return; }
          const value = bridge.current.get(`block:${id}`);
          const stored = value ? bridge.values.get(value) : undefined;
          stored?.children.forEach(visit);
        };
        ["header", "sidebar", "main"].forEach(visit);
        bridge.replaying = true;
        try { editor.transact(tr => {
          targets.forEach(id => editor.updateBlock(id, rebuild(id)));
          const tableIds = new Map<string, TableRowIdentity[]>();
          for (const [key, value] of bridge.current) {
            const stored = value ? bridge.values.get(value) : undefined;
            if (key.startsWith("block:") && stored?.tableIds) tableIds.set(key.slice(6), stored.tableIds);
          }
          restoreTableIdentities(tr, tableIds);
          const name = editor.getBlock("name");
          if (name?.type === "paragraph" && name.content.some(inline => inline.type === "factField"
            && inline.props.syncedFactRevision !== (bridge.factRevisions.get("fact:name") ?? 1))) editor.updateBlock(name, { content: name.content.map(inline => inline.type === "factField"
            ? { ...inline, props: { ...inline.props, syncedFactRevision: bridge.factRevisions.get("fact:name") ?? 1 } } : inline) });
        }); }
        finally { bridge.replaying = false; }
      }
      refresh(value => value + 1);
    });
    bridge.history = history;
    bridge.undo = () => history.undo();
    bridge.redo = () => history.redo();
    function observe() {
      if (bridge.replaying) return;
      const next = project(editor.document);
      const changes: CellChange[] = [];
      for (const key of new Set([...next.keys(), ...bridge.current.keys()].filter(key => key.startsWith("block:")))) {
        const before = history.read(key), after = next.get(key) ?? null;
        if (before !== after) changes.push({ key, before, after });
      }
      if (!changes.length) return;
      const now = performance.now();
      if (!bridge.composing && bridge.kind === "typing" && now - bridge.lastTypingAt > 500) bridge.group++;
      bridge.lastTypingAt = now;
      bridge.observing = true;
      try { history.commit(bridge.composing ? "composition" : bridge.kind, changes,
        bridge.kind === "typing" ? `typing:${bridge.group}` : null); }
      finally { bridge.observing = false; }
    }
    bridge.complete = observe;
    const stop = editor.onChange(observe);
    window.foldcvSpike = {
      summary: () => ({ position: history.position, actions: history.length, clock: history.revisionClock,
        composing: bridge.composing, historyDisabled: !Object.hasOwn(editor.extensions, "history"),
        factRevisions: Object.fromEntries(bridge.factRevisions), facts: Object.fromEntries([...bridge.current].filter(([key]) => key.startsWith("fact:"))), roots: editor.document.map(block => block.id) }),
      capture: () => {
        const id = history.currentActionId;
        return id ? history.capture(id, ["fact:name", "block:narrative", "block:job"]) : null;
      },
      reconcile: ticket => {
        const old = editor.getBlock("narrative");
        if (!old || old.type !== "paragraph") return "stale";
        const stored: StoredBlock = { block: { ...old, content: old.content.map(inline => inline.type === "text"
          ? { ...inline, text: "Sam leads " } : inline), children: [] }, children: old.children.map(child => child.id), tableIds: null };
        const value = JSON.stringify(stored);
        bridge.values.set(value, stored);
        return history.attach(ticket, [{ key: "block:narrative", before: history.read("block:narrative"), after: value }]);
      },
      selectAcrossRegions: () => { editor.setSelection("degree", "other"); editor.focus(); return editor.getSelection()?.blocks.map(block => block.id) ?? []; },
      tables: () => Object.fromEntries(editor.transact(tr => readTableIdentities(tr.doc))),
    };
    return () => { stop(); history.close(); delete window.foldcvSpike; };
  }, [bridge, editor]);

  function command(kind: HistoryKind, run: () => void, facts: Record<string, string> = {}) {
    const history = bridge.history;
    if (!history || bridge.composing) return;
    bridge.group++;
    bridge.kind = kind;
    // One public transaction is captured together with its fact changes.
    bridge.replaying = true;
    try { editor.transact(run); } finally { bridge.replaying = false; }
    for (const [key, value] of Object.entries(facts)) {
      const current = bridge.current.get(key) ?? null;
      bridge.current.set(key, current);
      // Include facts in the same action emitted below.
      pendingFacts.set(key, value);
    }
    bridge.complete();
    if (pendingFacts.size) {
      const id = history.currentActionId;
      const changes = [...pendingFacts].map(([key, value]) => ({ key, before: history.read(key), after: value }));
      const ticket = id ? history.capture(id, changes.map(change => change.key)) : null;
      if (ticket) history.attach(ticket, changes);
      pendingFacts.clear();
    }
    bridge.kind = "typing";
    bridge.group++;
  }
  const pendingFacts = useMemo(() => new Map<string, string>(), []);
  return <main className="rich-proof bg-surface text-content">
    <h1>NE03A · Synthetic public API proof</h1>
    <nav className="rich-proof-controls">
      <button onClick={() => bridge.undo()}>Undo</button><button onClick={() => bridge.redo()}>Redo</button>
      <button onClick={() => command("panel", () => editor.updateBlock("name", { content: [{ type: "factField", props: {
        bindingId: "name-binding", recordId: "candidate-1", fieldKey: "name", syncedFactRevision: 2 },
        content: [{ type: "text", text: "Sam Example", styles: { italic: true } }] }] }), { "fact:name": "Sam Example" })}>Panel name</button>
      <button onClick={() => command("rewrite", () => editor.updateBlock("narrative", { content: "A scoped rewrite" }))}>Rewrite</button>
      <button onClick={() => command("cascade", () => editor.updateBlock("period", { content: "May–July 2024" }), { "fact:period": "May–July 2024" })}>Cascade</button>
      <button onClick={() => command("structure", () => {
        const table = editor.getBlock("table"), ids = editor.transact(tr => readTableIdentities(tr.doc)).get("table");
        if (table?.type === "table" && ids) editor.transact(tr => {
          editor.updateBlock(table, { content: { ...table.content, rows: [...table.content.rows].reverse() } });
          restoreTableIdentities(tr, new Map([["table", [...ids].reverse()]]));
        });
      })}>Reverse table rows</button>
      <button onClick={() => command("structure", () => {
        const block = editor.getBlock("other"), main = editor.getBlock("main"), sidebar = editor.getBlock("sidebar");
        if (block && main && sidebar) {
          editor.updateBlock(main, { children: main.children.filter(child => child.id !== "other") });
          editor.updateBlock(sidebar, { children: [...sidebar.children, block] });
        }
      })}>Move to sidebar</button>
      <button onClick={() => command("structure", () => {
        const job = editor.getBlock("job"), main = editor.getBlock("main"), header = editor.getBlock("header");
        if (job && main && header) {
          editor.updateBlock(main, { children: main.children.filter(child => child.id !== "job") });
          editor.updateBlock(header, { children: [...header.children, job] });
        }
      })}>Move job to header</button>
      <button onClick={() => command("structure", () => {
        const claim = editor.getBlock("narrative"), job = editor.getBlock("job"), destination = editor.getBlock("job-2");
        if (claim && job && destination) {
          editor.updateBlock(job, { children: job.children.filter(child => child.id !== "narrative") });
          editor.updateBlock(destination, { children: [...destination.children, claim] });
        }
      }, { "fact:claim-owner": "job-2" })}>Move claim to job 2</button>
      <button onClick={() => { bridge.ticket = window.foldcvSpike?.capture() ?? null; }}>Capture reply</button>
      <button onClick={() => { if (bridge.ticket) window.foldcvSpike?.reconcile(bridge.ticket); }}>Apply reply</button>
      <button onClick={() => window.foldcvSpike?.selectAcrossRegions()}>Select across regions</button>
    </nav>
    <output aria-label="History">Actions {bridge.history?.length ?? 0} · Cursor {bridge.history?.position ?? 0} · Revision {bridge.history?.revisionClock ?? 0}</output>
    <div className="rich-proof-document"><BlockNoteView editor={editor} theme="light" /></div>
  </main>;
}
const root = document.getElementById("root");
if (!root) throw new Error("Missing root");
const mountedRoot = createRoot(root);
mountedRoot.render(<Spike />);
if (import.meta.hot) import.meta.hot.dispose(() => mountedRoot.unmount());
