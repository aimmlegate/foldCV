import { useEffect, useImperativeHandle, useRef, useState, type Ref, type RefObject } from "react";
import { ConnectionWorkflow } from "../connection/workflow";
import type { CapturedEditorSelection, RichEditorHandle } from "../rich/Editor";
import { AgentApiFailure, AgentBrowserApi } from "./api";
import { AssistantController, type AssistantView } from "./controller";
import { drawerSize, errorText } from "./presentation";
import { DrawerView } from "../workbench/assistant/DrawerView";
import { projectJobs } from "../background/jobs";
import type { AgentProjectOperations } from "../contracts/generated/agent_project_operations";
import { limitsEditToSelection } from "./selection-intent";
import { OperationStatus } from "../workbench/ui/OperationStatus";

export type AssistantHandle = { stop: () => Promise<void>; history: () => void; fence: (saved: boolean) => void };
const key = "foldcv.assistant.drawer";
function storedSize() { try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null"); return drawerSize(value); } catch { return drawerSize(null); } }
export function AssistantDrawer({ projectId, editor, settingsOpen, settings, ref, title = "Резюме", background = false, onProjectLifecycle }: { projectId: string; editor: RefObject<RichEditorHandle | null>;
  settingsOpen: boolean; settings: () => void; ref: Ref<AssistantHandle>; title?: string; background?: boolean;
  onProjectLifecycle?: (kind: "archive" | "delete") => Promise<boolean> }) {
  const [view, setView] = useState<AssistantView | null>(null), [size, setSize] = useState(storedSize);
  const [captured, setCaptured] = useState<CapturedEditorSelection | null>(null), [fence, setFence] = useState<string | null>(null);
  const controller = useRef<AssistantController | null>(null), selectionKey = useRef(""), log = useRef<HTMLDivElement>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [operations, setOperations] = useState<AgentProjectOperations["items"]>([]);
  const lifecycle = useRef(onProjectLifecycle);
  lifecycle.current = onProjectLifecycle;
  useEffect(() => {
    let alive = true;
    let initialized = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const handled = new Set<string>(), api = new AgentBrowserApi(projectId);
    async function refreshOperations() {
      try {
        const value = await api.operations();
        if (!alive) return;
        setOperations(value.items);
        if (!initialized) { value.items.forEach(item => handled.add(item.id)); initialized = true; }
        for (const item of value.items) {
          if (!alive) break;
          const kind = item.action === "archive" && item.status === "completed" ? "archive" : item.action === "delete" && item.status === "deleted" ? "delete" : null;
          if (kind && !handled.has(item.id) && await lifecycle.current?.(kind)) handled.add(item.id);
        }
      } catch (error) { if (alive) setFailure(error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED"); }
      finally { if (alive) timer = setTimeout(() => { void refreshOperations(); }, 2000); }
    }
    void refreshOperations();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [projectId]);
  const report = (work: Promise<void> | undefined) => { void work?.catch(error => setFailure(error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED")); };
  useEffect(() => {
    const mounted = editor.current;
    if (!mounted) return;
    const api = new AgentBrowserApi(projectId), connection = new ConnectionWorkflow(() => {});
    const current = new AssistantController(api, { sessionId: mounted.sessionId,
      apply: (id, api) => { if (editor.current?.sessionId !== mounted.sessionId) return Promise.reject(new AgentApiFailure("AGENT_NO_OWNER")); return editor.current.applyAssistant(id, api); } }, setView, 5000, background ? projectJobs(projectId) : null);
    controller.current = current; setView(current.view);
    void (async () => {
      await connection.peek();
      if (connection.view.snapshot.state === "unchecked" && (await api.settings()).enabled) await connection.refresh();
      await current.init();
    })().catch(() => setFailure("REQUEST_FAILED"));
    const close = () => current.close(); window.addEventListener("pagehide", close);
    return () => { window.removeEventListener("pagehide", close); connection.close(); current.close(); if (controller.current === current) controller.current = null; };
  }, [projectId, editor, background]);
  useEffect(() => { if (!settingsOpen) report(controller.current?.refresh()); }, [settingsOpen]);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(size)); } catch { /* Size is optional when browser storage is unavailable. */ } }, [size]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.activeElement?.closest(".cv-document")) return;
      const next = editor.current?.captureSelection() ?? null;
      const id = JSON.stringify(next ? [next.selection, [...next.epochs]] : null);
      if (id !== selectionKey.current) { selectionKey.current = id; setCaptured(next); }
    }, 200);
    return () => clearInterval(timer);
  }, [editor]);
  useEffect(() => {
    const element = log.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 180) element.scrollTop = element.scrollHeight;
  }, [view?.messages, view?.partial, view?.findings, view?.sources, view?.activity]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [view?.conversationId, view?.run?.id]);
  useImperativeHandle(ref, () => ({ stop: async () => { if (controller.current?.active) await controller.current.stop(); },
    history: () => { if (!background && controller.current?.active) report(controller.current.stop()); },
    fence: saved => { setFence(saved ? "Правки сохранены. Откройте резюме заново, чтобы продолжить редактирование." : errorText("AGENT_OUTCOME_UNKNOWN")); if (!background) report(controller.current?.stop()); } }), [background]);
  function send() {
    const current = controller.current, mounted = editor.current, scope = captured;
    if (!current || !mounted) return;
    setFailure(null);
    report(current.send(async () => {
      const value = await mounted.assistantBaseline(scope);
      const onlySelection = limitsEditToSelection(current.view.draft);
      return { response: value.response, scope: onlySelection && value.selection ? { kind: "selection", selection: value.selection } : { kind: "resume" },
        selectionContext: value.selection, historyOffers: value.historyOffers };
    }));
  }
  const active = controller.current?.active ?? false;
  return view ? <DrawerView view={view} active={active} title={title} collapsed={size.collapsed} expanded={size.height >= 500}
    toggle={() => setSize(value => ({ ...value, collapsed: !value.collapsed }))} expand={() => setSize(value => ({ ...value, height: value.height >= 500 ? 320 : 520 }))}
    log={log} captured={captured ? `${String(captured.selection.blockIds.length)} ${captured.selection.blockIds.length === 1 ? "блок" : "блоков"}` : null}
    applying={active && !view.pendingSend && (!view.run || ["completed", "failed", "cancelled", "interrupted"].includes(view.run.state))}
    failure={failure || view.error ? errorText(failure || view.error) : null} fence={fence}
    draft={value => controller.current?.draft(value)} flags={(allowEdits, allowWeb) => controller.current?.flags({ allowEdits, allowWeb })}
    model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => setCaptured(null)} settings={settings}
    select={id => report(controller.current?.select(id))} fresh={() => report(controller.current?.newConversation())}
    more={() => report(controller.current?.moreConversations())} older={() => report(controller.current?.older())}
    operations={operations}
    resource={(kind, id) => report(controller.current?.resource(kind, id))} focus={anchor => editor.current?.focusFinding(anchor) ?? false} />
    : <section id="agent-chat-host" className="chat-loading" aria-label="Помощник"><OperationStatus label="Открываем помощника" /></section>;
}
