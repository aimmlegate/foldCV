import { useState } from "react";
import type { AgentFinding } from "../../contracts/generated/agent_finding";
import type { AssistantView } from "../../assistant/controller";
import { sourceUrl } from "../../assistant/presentation";
import { Activity } from "./AgentActivity";
import { MessageText } from "../../assistant/MessageText";
import { Icon } from "../ui/Icon";

export function Transcript({ view, active, resource, focus, draft }: { view: AssistantView; active: boolean;
  resource: (kind: "sources" | "findings", id: string) => void; focus: (anchor: AgentFinding["anchors"][number]) => boolean; draft: (value: string) => void }) {
  const [stale, setStale] = useState<Set<string>>(() => new Set()), [copy, setCopy] = useState("");
  return <>
    {!view.messages.length && !active && <div className="chat-empty"><span className="chat-empty-icon"><Icon name="spark" /></span><h3>Чат по этому резюме</h3>
      <p>Проверьте резюме или попросите изменить выбранный фрагмент.<br />Правки попадут в общую историю отмены.</p><div className="chat-suggestions">
        {["Проверь резюме", "Сократи текст", "Сравни с вакансией"].map(text => <button key={text} onClick={() => { draft(text); document.getElementById("chat-input")?.focus(); }}><Icon name="spark" />{text}</button>)}
      </div></div>}
    {view.messages.map(message => <article key={message.id} className={`chat-message${message.role === "user" ? " from-user" : ""}`}>
      <div className="chat-message-heading"><span>{message.role !== "user" && <Icon name="spark" />}{message.role === "user" ? "Вы" : "Помощник"}</span>
        <small><time dateTime={message.timestamp}>{new Date(message.timestamp).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</time></small></div>
      <MessageText text={message.text} truncated={message.truncated} error={message.error?.code ?? null} />
      {message.sources.map(ref => <button className="chat-source" key={ref.id} onClick={() => resource("sources", ref.id)}><Icon name="file" />{ref.label || "Открыть источник"}<Icon name="arrow" /></button>)}
      {message.findings.map(ref => <button className="chat-source" key={ref.id} onClick={() => resource("findings", ref.id)}><Icon name="info" />{ref.label || "Открыть замечание"}<Icon name="arrow" /></button>)}
      {message.role !== "user" && <div className="chat-message-actions"><button className="chat-icon" aria-label="Скопировать ответ" title="Скопировать ответ"
        onClick={() => { void navigator.clipboard.writeText(message.text).then(() => setCopy("Ответ скопирован"), () => setCopy("Не удалось скопировать ответ")); }}><Icon name="copy" /></button>
        {message.error && !active && <button className="chat-retry" onClick={() => { const index = view.messages.indexOf(message); const prior = view.messages.slice(0, index).reverse().find(item => item.role === "user");
          if (prior) { draft(prior.text); document.getElementById("chat-input")?.focus(); } }}><Icon name="redo" />Повторить задачу</button>}</div>}
    </article>)}
    {(view.run || view.submitting || view.pendingSend) && <article className="chat-message"><Activity key={view.run?.id ?? "sending"} view={view} active={active} />
      {view.partial && <div className="chat-message-text" aria-label="Текущий ответ"><p>{view.partial}</p>{view.partialTruncated && <small>Ответ сокращён.</small>}</div>}
      {view.receipts.map(receipt => <div className="chat-receipt" key={receipt.batchId}><span><Icon name={receipt.durable && receipt.disposition === "saved" ? "check" : "info"} /><strong>{receipt.durable && receipt.disposition === "saved" ? "Изменения сохранены" : receipt.disposition === "outcome_unknown" ? "Проверяем результат сохранения" : "Правки не применены"}</strong>
        <small>{receipt.durable && receipt.disposition === "saved" ? `Одна отмена в истории редактора · версия ${String(receipt.projectRevision)}` : "Состояние сохранения"}</small></span></div>)}
    </article>}
    {view.sources.map(source => { const url = sourceUrl(source.finalUrl); return <details className="chat-message uir-chat-source" key={source.id} open><summary className="chat-source"><Icon name="file" />{source.title || "Полученная страница"} · {url ? new URL(url).hostname : "Сохранённый источник"}</summary>
      {url && <a href={url} target="_blank" rel="noopener noreferrer">Открыть источник</a>}<small>Получен {new Date(source.retrievedAt).toLocaleString("ru")}{source.truncated ? " · текст сокращён" : ""}</small><div className="chat-message-text"><p>{source.text}</p></div></details>; })}
    {view.findings.length > 0 && <section className="chat-findings" aria-label="Замечания">{view.findings.map(finding => <div key={finding.id}>{finding.anchors.length ? finding.anchors.map((anchor, index) => {
      const key = `${finding.id}:${String(index)}`; return <button key={key} onClick={() => { if (!focus(anchor)) setStale(current => new Set([...current, key])); }}><Icon name="info" /><span><strong>{finding.message}</strong>
        <small>{stale.has(key) && "Фрагмент изменён. Прежнее место в резюме: "}{anchor.text}{anchor.end !== null && anchor.start !== null && anchor.end - anchor.start > anchor.text.length ? " · фрагмент сокращён" : ""}</small></span><Icon name="arrow" /></button>;
    }) : <p>{finding.message}</p>}</div>)}</section>}
    {copy && <p role="status">{copy}</p>}
  </>;
}
