import { useEffect, useImperativeHandle, useRef, useState, type Ref, type RefObject } from "react";
import * as Popover from "@radix-ui/react-popover";
import { ConnectionWorkflow } from "../connection/workflow";
import type { CapturedEditorSelection, RichEditorHandle } from "../rich/Editor";
import { AgentApiFailure, AgentBrowserApi } from "./api";
import { AssistantController, type AssistantView } from "./controller";
import { drawerSize, errorText } from "./presentation";
import { Composer } from "./Composer";
import { Messages } from "./Messages";
import { Resources } from "./Resources";
import { Activity } from "./Activity";
import { DrawerView } from "../workbench/assistant/DrawerView";

export type AssistantHandle = { stop: () => Promise<void>; history: () => void; fence: (saved: boolean) => void };
const key = "foldcv.assistant.drawer";
function storedSize() { try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null"); return drawerSize(value); } catch { return drawerSize(null); } }
export function AssistantDrawer({ projectId, editor, settingsOpen, settings, ref, appearance = "reference", title = "Резюме" }: { projectId: string; editor: RefObject<RichEditorHandle | null>;
  settingsOpen: boolean; settings: () => void; ref: Ref<AssistantHandle>; appearance?: "reference" | "prototype"; title?: string }) {
  const [view, setView] = useState<AssistantView | null>(null), [size, setSize] = useState(storedSize);
  const [captured, setCaptured] = useState<CapturedEditorSelection | null>(null), [fence, setFence] = useState<string | null>(null);
  const controller = useRef<AssistantController | null>(null), selectionKey = useRef(""), log = useRef<HTMLDivElement>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const report = (work: Promise<void> | undefined) => { void work?.catch(error => setFailure(error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED")); };
  useEffect(() => {
    const mounted = editor.current;
    if (!mounted) return;
    const api = new AgentBrowserApi(projectId), connection = new ConnectionWorkflow(() => {});
    const current = new AssistantController(api, { sessionId: mounted.sessionId,
      apply: (id, api) => { if (editor.current?.sessionId !== mounted.sessionId) return Promise.reject(new AgentApiFailure("AGENT_NO_OWNER")); return editor.current.applyAssistant(id, api); } }, setView);
    controller.current = current; setView(current.view);
    void (async () => {
      await connection.peek();
      if (connection.view.snapshot.state === "unchecked" && (await api.settings()).enabled) await connection.refresh();
      await current.init();
    })().catch(() => setFailure("REQUEST_FAILED"));
    const close = () => current.close(); window.addEventListener("pagehide", close);
    return () => { window.removeEventListener("pagehide", close); connection.close(); current.close(); if (controller.current === current) controller.current = null; };
  }, [projectId, editor]);
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
  }, [view?.messages, view?.partial, view?.findings, view?.sources]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [view?.conversationId, view?.run?.id]);
  useImperativeHandle(ref, () => ({ stop: async () => { if (controller.current?.active) await controller.current.stop(); },
    history: () => { if (controller.current?.active) report(controller.current.stop()); },
    fence: saved => { setFence(saved ? "Правки сохранены. Откройте резюме заново, чтобы продолжить редактирование." : errorText("AGENT_OUTCOME_UNKNOWN")); report(controller.current?.stop()); } }), []);
  function send() {
    const current = controller.current, mounted = editor.current, scope = captured;
    if (!current || !mounted) return;
    setFailure(null);
    report(current.send(async () => {
      const value = await mounted.assistantBaseline(scope);
      return { response: value.response, scope: value.selection ? { kind: "selection", selection: value.selection } : { kind: "resume" } };
    }));
  }
  const active = controller.current?.active ?? false;
  if (appearance === "prototype") return view ? <DrawerView view={view} active={active} title={title} collapsed={size.collapsed} expanded={size.height >= 500}
    toggle={() => setSize(value => ({ ...value, collapsed: !value.collapsed }))} expand={() => setSize(value => ({ ...value, height: value.height >= 500 ? 320 : 520 }))}
    log={log} captured={captured ? `${String(captured.selection.blockIds.length)} ${captured.selection.blockIds.length === 1 ? "блок" : "блоков"}` : null}
    applying={active && !view.pendingSend && (!view.run || ["completed", "failed", "cancelled", "interrupted"].includes(view.run.state))}
    failure={failure || view.error ? errorText(failure || view.error) : null} fence={fence}
    draft={value => controller.current?.draft(value)} flags={(allowEdits, allowWeb) => controller.current?.flags({ allowEdits, allowWeb })}
    model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => setCaptured(null)} settings={settings}
    select={id => report(controller.current?.select(id))} fresh={() => report(controller.current?.newConversation())}
    more={() => report(controller.current?.moreConversations())} older={() => report(controller.current?.older())}
    resource={(kind, id) => report(controller.current?.resource(kind, id))} focus={anchor => editor.current?.focusFinding(anchor) ?? false} />
    : <section id="agent-chat-host" aria-label="Помощник"><p role="status">Открываем помощника…</p></section>;
  return <section className="assistant-drawer" aria-label="Помощник" data-collapsed={size.collapsed} style={size.collapsed ? undefined : { height: size.height }}>
    <header className="assistant-header"><button aria-expanded={!size.collapsed} aria-controls="assistant-content" onClick={() => setSize(value => ({ ...value, collapsed: !value.collapsed }))}>Помощник {size.collapsed ? "↑" : "↓"}</button>
      {size.collapsed && active && <span role="status">Задача выполняется</span>}
      {size.collapsed && active && <button onClick={() => report(controller.current?.stop())}>Остановить</button>}
      {!size.collapsed && <><Popover.Root><Popover.Trigger aria-label="Размер панели помощника">Размер</Popover.Trigger><Popover.Portal><Popover.Content className="rich-block-menu" sideOffset={8}>
        <label>Высота панели<input aria-label="Высота панели помощника" type="range" min={200} max={520} step={20} value={size.height}
          onChange={event => setSize(value => ({ ...value, height: Number(event.target.value) }))} /></label><Popover.Close>Готово</Popover.Close></Popover.Content></Popover.Portal></Popover.Root>
        {view && <><label className="assistant-dialogs">Диалог<select aria-label="Диалог помощника" value={view.conversationId ?? ""} disabled={view.submitting}
          onChange={event => report(controller.current?.select(event.target.value))}><option value="">Новый диалог</option>{view.conversations.map(item => <option key={item.id} value={item.id}>{item.title || "Пустой диалог"}</option>)}</select></label>
          {view.conversationCursor && <button onClick={() => report(controller.current?.moreConversations())}>Ещё диалоги</button>}
          <button disabled={view.submitting} onClick={() => report(controller.current?.newConversation())}>Новый диалог</button></>}
      </>}</header>
    <div id="assistant-content" hidden={size.collapsed} className="assistant-content">{view ? <>
      <div ref={log} className="assistant-transcript"><Activity view={view} />{view.messageCursor && <button onClick={() => report(controller.current?.older())}>Ранее в диалоге</button>}
        {!view.messages.length && !active && <p className="assistant-empty">Проверьте резюме или попросите изменить выбранный фрагмент. Правки попадут в общую историю отмены.</p>}
        <Messages items={view.messages} partial={view.partial} truncated={view.partialTruncated} resource={(kind, id) => report(controller.current?.resource(kind, id))} />
        <Resources sources={view.sources} findings={view.findings} focus={anchor => editor.current?.focusFinding(anchor) ?? false} />
        {(failure || view.error) && <p className="text-danger" role="alert">{errorText(failure || view.error)}</p>}{fence && <p role="alert">{fence}</p>}
      </div><Composer view={view} captured={captured ? `${String(captured.selection.blockIds.length)} ${captured.selection.blockIds.length === 1 ? "блок" : "блоков"}` : null}
        active={active} applying={active && !view.pendingSend && (!view.run || ["completed", "failed", "cancelled", "interrupted"].includes(view.run.state))}
        draft={value => controller.current?.draft(value)} flags={(allowEdits, allowWeb) => controller.current?.flags({ allowEdits, allowWeb })}
        model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => setCaptured(null)} settings={settings} />
    </> : <p role="status">Открываем помощника…</p>}</div>
  </section>;
}
