import { useEffect, useState } from "react";
import type { AssistantView } from "../../assistant/controller";
import { activityItems, currentActivity } from "./activity";
import { Elapsed, Spinner } from "../ui/OperationStatus";
import { Icon } from "../ui/Icon";

export function Activity({ view, active }: { view: AssistantView; active: boolean }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { if (!active) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [active]);
  const items = view.submitting || view.pendingSend ? [] : activityItems(view), latest = items.at(-1);
  const observed = Date.parse(latest?.timestamp ?? view.run?.createdAt ?? "");
  const quiet = active && Number.isFinite(observed) && now - observed >= 20000;
  const summary = [...items].reverse().find(item => item.state === "summary");
  const preview = view.run?.state === "queued" ? "Начнём, когда освободится модель."
    : quiet && view.run?.state === "running" ? "Новых событий пока нет. Ожидаем ответ модели."
    : summary?.text ?? (latest ? `${latest.label}${latest.state === "success" ? " · готово" : latest.state === "error" ? " · не удалось" : ""}` : "Ход работы появится здесь.");
  return <details className="chat-activity">
    <summary>{active && !view.pendingSend ? <Spinner /> : <Icon name={view.run?.state === "completed" ? "check" : "info"} />}
      <span className="operation-copy"><span role="status">{currentActivity(view, active)}</span>
        <span className="chat-activity-preview" title={preview}>{preview}</span></span>
      {view.run && !view.pendingSend && <Elapsed key={view.submitting ? "submitting" : view.run.id} startedAt={view.submitting ? undefined : view.run.createdAt}
        finishedAt={active ? null : view.run.finishedAt} active={active && !view.pendingSend} />}
      <Icon name="chevron" />
    </summary>
    <ol className="chat-activity-log" aria-label="Ход работы помощника">{items.map(item => <li key={item.id}>
      {item.state === "working" && active ? <Spinner /> : <Icon name={item.state === "success" ? "check" : item.state === "summary" ? "spark" : "info"} />}
      <span>{item.text || item.label}<small>{item.state === "summary" ? "Краткое сообщение модели" : item.state === "error" ? "Не удалось выполнить" : item.state === "success" ? "Готово" : active ? "В работе" : "Выполнение завершено"}</small></span>
    </li>)}</ol>
    <p className="chat-activity-note">Модель: {view.run?.model ?? "подготавливаем"}. Здесь показаны действия и доступные краткие сообщения модели.</p>
  </details>;
}
