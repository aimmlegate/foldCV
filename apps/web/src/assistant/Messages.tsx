import type { AgentMessage } from "../contracts/generated/agent_message";
import { errorText } from "./presentation";
export function Messages({ items, partial, truncated, resource }: { items: AgentMessage[]; partial: string; truncated: boolean;
  resource: (kind: "sources" | "findings", id: string) => void }) {
  return <div className="assistant-messages" aria-label="Сообщения помощника">{items.map(message => <article key={message.id} className={`assistant-message ${message.role === "user" ? "assistant-user" : "assistant-reply"}`}>
    <header><strong>{message.role === "user" ? "Вы" : "Помощник"}</strong> <time dateTime={message.timestamp}>{new Date(message.timestamp).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</time></header>
    <p>{message.text}</p>{message.truncated && <small>Ответ сокращён.</small>}
    {message.error && <small className="text-danger">{errorText(message.error.code)}</small>}
    <div className="assistant-references">{message.sources.map(ref => <button key={ref.id} onClick={() => resource("sources", ref.id)}>Источник: {ref.label || "Открыть"}</button>)}
      {message.findings.map(ref => <button key={ref.id} onClick={() => resource("findings", ref.id)}>Замечание: {ref.label || "Открыть"}</button>)}</div>
  </article>)}{partial && <article className="assistant-message" aria-label="Текущий ответ"><strong>Помощник</strong><p>{partial}</p>{truncated && <small>Ответ сокращён.</small>}</article>}</div>;
}
