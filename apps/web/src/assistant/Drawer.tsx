import { useEffect, useImperativeHandle, useRef, useState, type Ref, type RefObject } from "react";
import { ConnectionWorkflow } from "../connection/workflow";
import type { TemplateEditorHandle } from "../rich/TemplateEditor";
import { AgentApiFailure, AssistantApi } from "./api";
import { AssistantController, type AssistantSelection, type AssistantView } from "./controller";
import { drawerSize, errorText } from "./presentation";
import { DrawerView } from "../workbench/assistant/DrawerView";

export type AssistantHandle = { stop: () => Promise<void> };
const key = "foldcv.assistant.drawer";
function storedSize() { try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null"); return drawerSize(value); } catch { return drawerSize(null); } }

/** The assistant drawer of the open V7 editor: runs read a pinned snapshot, proposals change the resume only through
 * the editor's Apply (D093, D109). */
export function AssistantDrawer({ projectId, editor, settingsOpen, settings, ref, title = "Резюме", onProjectLifecycle }: {
  projectId: string; editor: RefObject<TemplateEditorHandle | null>; settingsOpen: boolean; settings: () => void; ref: Ref<AssistantHandle>;
  title?: string; onProjectLifecycle?: (kind: "archive" | "delete") => Promise<boolean> }) {
  const [view, setView] = useState<AssistantView | null>(null), [size, setSize] = useState(storedSize);
  const [captured, setCaptured] = useState<AssistantSelection | null>(null);
  const controller = useRef<AssistantController | null>(null), selectionKey = useRef(""), log = useRef<HTMLDivElement>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const lifecycle = useRef(onProjectLifecycle);
  lifecycle.current = onProjectLifecycle;
  const report = (work: Promise<void> | undefined) => { void work?.catch(error => setFailure(error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED")); };
  useEffect(() => {
    const api = new AssistantApi(projectId), connection = new ConnectionWorkflow(() => {});
    const current = new AssistantController(api, {
      applyProposal: (id, allowEdits) => {
        const mounted = editor.current;
        return mounted ? mounted.applyAssistant(id, allowEdits) : Promise.reject(new AgentApiFailure("EDITOR_TOKEN_UNKNOWN"));
      },
      actionApplied: async action => {
        if (action.action === "archive" || action.action === "delete") { await lifecycle.current?.(action.action); return; }
        if (action.action !== "restore") await editor.current?.refresh();
      } }, setView);
    controller.current = current; setView(current.view);
    void (async () => {
      await connection.peek();
      if (connection.view.snapshot.state === "unchecked" && (await api.settings()).enabled) await connection.refresh();
      await current.init();
    })().catch(() => setFailure("REQUEST_FAILED"));
    return () => { connection.close(); current.close(); if (controller.current === current) controller.current = null; };
  }, [projectId, editor]);
  useEffect(() => { if (!settingsOpen) report(controller.current?.refresh()); }, [settingsOpen]);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(size)); } catch { /* Size is optional when browser storage is unavailable. */ } }, [size]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.activeElement?.closest(".cv-document")) return;
      const next = editor.current?.captureSelection() ?? null;
      const id = JSON.stringify(next);
      if (id !== selectionKey.current) { selectionKey.current = id; setCaptured(next); }
    }, 200);
    return () => clearInterval(timer);
  }, [editor]);
  useEffect(() => {
    const element = log.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 180) element.scrollTop = element.scrollHeight;
  }, [view?.messages, view?.partial, view?.findings, view?.sources, view?.activity, view?.proposals]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [view?.conversationId, view?.run?.id]);
  useImperativeHandle(ref, () => ({ stop: async () => { if (controller.current?.active) await controller.current.stop(); } }), []);
  function send() {
    const current = controller.current, mounted = editor.current, scope = captured;
    if (!current || !mounted) return;
    setFailure(null);
    // The run reads the saved project, so typing is saved first.
    report(current.send(async () => { await mounted.flush(); return scope; }));
  }
  const active = controller.current?.active ?? false;
  return view?.settings?.enabled ? <DrawerView view={view} active={active} title={title} collapsed={size.collapsed} expanded={size.height >= 500}
    toggle={() => setSize(value => ({ ...value, collapsed: !value.collapsed }))} expand={() => setSize(value => ({ ...value, height: value.height >= 500 ? 320 : 520 }))}
    log={log} captured={captured ? `${String(captured.blockIds.length)} ${captured.blockIds.length === 1 ? "блок" : "блоков"}` : null}
    applying={view.proposalBusy !== null}
    failure={failure ? errorText(failure) : view.error ? errorText(view.error) : null} fence={null}
    draft={value => controller.current?.draft(value)} flags={(allowEdits, allowWeb) => controller.current?.flags({ allowEdits, allowWeb })}
    model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => setCaptured(null)} settings={settings}
    select={id => report(controller.current?.select(id))} fresh={() => report(controller.current?.newConversation())}
    applyProposal={value => report(controller.current?.applyProposal(value))}
    discardProposal={value => report(controller.current?.discardProposal(value))}
    resource={(kind, id) => report(controller.current?.resource(kind, id))} focus={anchor => editor.current?.focusFinding(anchor) ?? false} />
    : null;
}
