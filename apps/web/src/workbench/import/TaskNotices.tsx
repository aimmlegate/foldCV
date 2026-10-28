import { useEffect, useState } from "react";
import { NotificationSection } from "../ui/NotificationCenter";
import { Elapsed } from "../ui/OperationStatus";
import type { ImportEntry } from "./progress";
import { taskNotices } from "./task-notice";

/** Imports of every project in «Уведомления» → «Задачи»; the import screen itself shows only inside its resume. */
export function TaskNotices({ entries, activeId, titleOf, stop, close, open }: {
  entries: ReadonlyMap<string, ImportEntry>; activeId: string | null; titleOf: (projectId: string) => string | undefined;
  stop: (projectId: string) => void; close: (projectId: string) => void; open: (projectId: string) => void;
}) {
  const [now, setNow] = useState(Date.now);
  const following = entries.size > 0;
  useEffect(() => {
    if (!following) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [following]);
  const notices = taskNotices(entries.values(), now, titleOf);
  return <NotificationSection count={notices.length}>
    {notices.length > 0 && <section className="notice-group" aria-label="Задачи"><h3>Задачи</h3>
      {notices.map(notice => <div className={`notice task-notice${notice.state === "failed" || notice.state === "stalled" ? " error" : ""}`}
        role="status" key={notice.projectId}>
        <p><strong>{notice.title}</strong><span>{notice.text}{(notice.state === "running" || notice.state === "queued")
          && <> · <Elapsed startedAt={notice.startedAt} /></>}</span></p>
        <div className="task-notice-actions">
          {notice.projectId !== activeId && <button type="button" className="text-button" onClick={() => open(notice.projectId)}>Открыть</button>}
          {notice.state === "running" || notice.state === "queued"
            ? <button type="button" className="text-button" disabled={notice.stopping} onClick={() => stop(notice.projectId)}>
              {notice.stopping ? "Останавливаем…" : "Остановить"}</button>
            : <button type="button" className="text-button" onClick={() => close(notice.projectId)}>Закрыть</button>}
        </div>
      </div>)}
    </section>}
  </NotificationSection>;
}
