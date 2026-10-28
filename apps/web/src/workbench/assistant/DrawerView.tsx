import { errorMessage } from "../../errors/messages";
import { useEffect, useRef, useState, type RefObject } from "react";
import { Icon } from "../ui/Icon";
import { Composer, type ComposerProps } from "./Composer";
import { Transcript } from "./Transcript";
import { currentActivity } from "./activity";
import { Elapsed, OperationStatus, Spinner } from "../ui/OperationStatus";
import { ProposalPreview } from "../../assistant/proposal";
import type { Proposal } from "../../assistant/api";
import type { AssistantFinding } from "../../assistant/controller";

export function DrawerView(props: ComposerProps & { collapsed: boolean; expanded: boolean; toggle: () => void; expand: () => void;
  log: RefObject<HTMLDivElement | null>; failure: string | null; fence: string | null;
  select: (id: string) => void; fresh: () => void;
  resource: (kind: "sources" | "findings", id: string) => void; focus: (anchor: AssistantFinding["anchors"][number]) => boolean;
  applyProposal: (value: Proposal) => void; discardProposal: (value: Proposal) => void }) {
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
    {collapsed ? <div className={active ? "uir-chat-active-bar" : undefined}><button className="chat-launcher" aria-expanded={false} aria-controls="assistant-content" onClick={toggle}><span><Icon name="chat" />Помощник</span>{active && <small><Spinner /><span className="agent-compact-label" role="status">{currentActivity(view, active)}</span>{view.run && <Elapsed key={view.run.id} startedAt={view.run.createdAt} />}</small>}<Icon name="chevron" /></button>
      {active && <button className="chat-icon" aria-label="Остановить" title="Остановить" disabled={view.run?.state === "cancelling" || view.loading === "Останавливаем"} onClick={props.stop}>{view.run?.state === "cancelling" || view.loading === "Останавливаем" ? <Spinner /> : <Icon name="stop" />}</button>}</div> : <div className="agent-chat-panel" id="assistant-content">
      <header className="chat-header"><div className="chat-title"><Icon name="chat" /><h2>Помощник</h2><span className="chat-access">{view.flags.allowEdits ? "Правки разрешены" : "Только чтение"}</span></div><div className="chat-header-actions">
        <button className="chat-icon" title="Новый диалог" aria-label="Новый диалог" disabled={view.submitting} onClick={props.fresh}><Icon name="plus" /></button>
        <button ref={trigger} className="chat-icon" title="Диалоги" aria-label="Диалоги" aria-expanded={threads} aria-controls="chat-threads" onClick={() => setThreads(value => !value)}><Icon name="list" /></button>
        <button className="chat-icon" title={expanded ? "Уменьшить панель" : "Развернуть панель"} aria-label={expanded ? "Уменьшить панель" : "Развернуть панель"} onClick={expand}><Icon name="expand" /></button>
        <button className="chat-icon" title="Свернуть помощника" aria-label="Свернуть помощника" onClick={() => { setThreads(false); toggle(); }}><Icon name="close" /></button></div></header>
      {threads && <div className="chat-thread-menu" id="chat-threads" ref={menu} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setThreads(false); trigger.current?.focus(); } }}><span>Диалоги</span>
        <button disabled={view.submitting} onClick={() => { props.fresh(); setThreads(false); }}><Icon name="plus" /><span>Новый диалог</span></button>
        {view.conversations.map(item => <button key={item.id} disabled={view.submitting} aria-current={view.conversationId === item.id ? "true" : undefined}
          onClick={() => { props.select(item.id); setThreads(false); }}><Icon name="chat" /><span>{item.title || "Пустой диалог"}</span></button>)}</div>}
      <div ref={props.log} className="chat-messages" role="log" aria-live="off" aria-busy={active}>
        <p className="visually-hidden" role="status" aria-live="polite">{currentActivity(view, active)}</p>
        <Transcript view={view} active={active} resource={props.resource} focus={props.focus} draft={props.draft} />
        {view.proposals.map(value => <ProposalPreview key={value.id} value={value} busy={active || view.proposalBusy !== null}
          stale={view.staleProposals.includes(value.id)} allowEdits={view.flags.allowEdits}
          apply={() => props.applyProposal(value)} discard={() => props.discardProposal(value)} />)}
        {view.loading && <div className="chat-load-status"><OperationStatus label={view.loading} /></div>}
        {view.files.map(file => <p key={file.id} className="chat-project-file">
          <a href={file.url} download={file.filename}>{file.format === "docx" ? "Скачать DOCX" : "Скачать .foldcv"}</a></p>)}
        {props.failure && <p className="chat-error" role="alert">{errorMessage(props.failure)}</p>}{props.fence && <p className="chat-error" role="alert">{errorMessage(props.fence)}</p>}
      </div><Composer {...props} /></div>}
  </section>;
}
