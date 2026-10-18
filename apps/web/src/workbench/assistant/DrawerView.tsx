import { useEffect, useRef, useState, type RefObject } from "react";
import type { AgentFinding } from "../../contracts/generated/agent_finding";
import { Icon } from "../ui/Icon";
import { Composer, type ComposerProps } from "./Composer";
import type { AgentProjectOperations } from "../../contracts/generated/agent_project_operations";
import { Transcript } from "./Transcript";

export function DrawerView(props: ComposerProps & { collapsed: boolean; expanded: boolean; toggle: () => void; expand: () => void;
  log: RefObject<HTMLDivElement | null>; failure: string | null; fence: string | null;
  select: (id: string) => void; fresh: () => void; more: () => void; older: () => void;
  resource: (kind: "sources" | "findings", id: string) => void; focus: (anchor: AgentFinding["anchors"][number]) => boolean;
  operations?: AgentProjectOperations["items"] }) {
  const { view, active, collapsed, expanded, toggle, expand } = props;
  const [threads, setThreads] = useState(false), menu = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const wasCollapsed = useRef(collapsed);
  useEffect(() => {
    if (!threads) return;
    menu.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    const dismiss = (event: PointerEvent) => { if (event.target instanceof Node && !menu.current?.contains(event.target) && !trigger.current?.contains(event.target)) setThreads(false); };
    window.addEventListener("pointerdown", dismiss); return () => window.removeEventListener("pointerdown", dismiss);
  }, [threads]);
  useEffect(() => {
    if (!collapsed) document.getElementById("chat-input")?.focus();
    else if (!wasCollapsed.current) document.querySelector<HTMLButtonElement>("#agent-chat-host .chat-launcher")?.focus();
    wasCollapsed.current = collapsed;
  }, [collapsed]);
  return <section id="agent-chat-host" aria-label="Помощник" className={collapsed ? undefined : `chat-open${expanded ? " chat-expanded" : ""}`}>
    {collapsed ? <div className={active ? "uir-chat-active-bar" : undefined}><button className="chat-launcher" aria-expanded={false} aria-controls="assistant-content" onClick={toggle}><span><Icon name="chat" />Помощник</span>{active && <small><span className="chat-spinner" />Задача выполняется</small>}<Icon name="chevron" /></button>
      {active && <button className="chat-icon" aria-label="Остановить" title="Остановить" onClick={props.stop}><Icon name="stop" /></button>}</div> : <div className="agent-chat-panel" id="assistant-content">
      <header className="chat-header"><div className="chat-title"><Icon name="chat" /><h2>Помощник</h2><span className="chat-access">Весь проект · {view.flags.allowEdits ? "правки разрешены" : "только чтение"}</span></div><div className="chat-header-actions">
        <button className="chat-icon" title="Новый диалог" aria-label="Новый диалог" disabled={view.submitting} onClick={props.fresh}><Icon name="plus" /></button>
        <button ref={trigger} className="chat-icon" title="Диалоги" aria-label="Диалоги" aria-expanded={threads} aria-controls="chat-threads" onClick={() => setThreads(value => !value)}><Icon name="list" /></button>
        <button className="chat-icon" title={expanded ? "Уменьшить панель" : "Развернуть панель"} aria-label={expanded ? "Уменьшить панель" : "Развернуть панель"} onClick={expand}><Icon name="expand" /></button>
        <button className="chat-icon" title="Свернуть помощника" aria-label="Свернуть помощника" onClick={() => { setThreads(false); toggle(); }}><Icon name="close" /></button></div></header>
      {threads && <div className="chat-thread-menu" id="chat-threads" ref={menu} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setThreads(false); trigger.current?.focus(); } }}><span>Диалоги по этому резюме</span>
        <button disabled={view.submitting} onClick={() => { props.fresh(); setThreads(false); }}><Icon name="plus" /><span>Новый диалог</span></button>
        {view.conversations.map(item => <button key={item.id} disabled={view.submitting} aria-current={view.conversationId === item.id ? "true" : undefined}
          onClick={() => { props.select(item.id); setThreads(false); }}><Icon name="chat" /><span>{item.title || "Пустой диалог"}</span></button>)}
        {view.conversationCursor && <button onClick={props.more}>Ещё диалоги</button>}</div>}
      <div ref={props.log} className="chat-messages" role="log" aria-live="polite" aria-relevant="additions text" aria-busy={active}>
        {view.messageCursor && <button className="text-button" onClick={props.older}>Ранее в диалоге</button>}
        <Transcript view={view} active={active} resource={props.resource} focus={props.focus} draft={props.draft} />
        {props.operations?.filter(item => item.durable && item.downloadUrl).map(item => <p key={item.id} className="chat-project-file">
          <a href={item.downloadUrl ?? ""} download={item.action === "export_docx" ? "resume.docx" : "resume.foldcv"}>{item.action === "export_docx" ? "Скачать DOCX" : "Скачать .foldcv"}</a></p>)}
        {props.failure && <p className="chat-error" role="alert">{props.failure}</p>}{props.fence && <p className="chat-error" role="alert">{props.fence}</p>}
      </div><Composer {...props} /></div>}
  </section>;
}
