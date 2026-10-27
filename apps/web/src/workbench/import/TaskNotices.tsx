import { useState } from "react";
import type { ProjectTask } from "../../projects/api";
import { NotificationSection } from "../ui/NotificationCenter";
import { Elapsed } from "../ui/OperationStatus";
import { taskNotice } from "./task-notice";

/** Background tasks in «Уведомления»; the floating import bar is gone (feedback items 16 and 19). */
export function TaskNotices({ task, stop }: { task: ProjectTask | null; stop?: (() => Promise<void>) | undefined }) {
  const [closed, setClosed] = useState<string | null>(null), [stopping, setStopping] = useState(false);
  const notice = taskNotice(task, closed);
  return <NotificationSection count={notice ? 1 : 0}>
    {notice && <section className="notice-group" aria-label="Задачи"><h3>Задачи</h3>
      <div className="notice" role="status"><p>{notice.text}{notice.state === "running" && <> · <Elapsed startedAt={notice.startedAt} /></>}</p>
        {notice.state === "running" ? stop && <button type="button" className="text-button" disabled={stopping}
          onClick={() => { setStopping(true); void stop().finally(() => setStopping(false)); }}>{stopping ? "Останавливаем…" : "Остановить"}</button>
          : <button type="button" className="text-button" onClick={() => setClosed(notice.id)}>Закрыть</button>}
      </div>
    </section>}
  </NotificationSection>;
}
