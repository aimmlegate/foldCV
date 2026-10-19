import { useEffect, useState } from "react";
import { rewriteActive, rewriteCancellable, rewriteLabels, type RewriteActivity } from "../../rich/rewrite-progress";
import { elapsedLabel } from "../import/progress-state";
import { Icon } from "../ui/Icon";

export function RewriteActivities({ activities, cancel, dismiss }: { activities: readonly RewriteActivity[];
  cancel: (id: string) => void; dismiss: (id: string) => void }) {
  const [now, setNow] = useState(Date.now);
  const running = activities.some(activity => rewriteActive(activity.stage));
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!activities.length) return null;
  return <section className="rewrite-activities" aria-label="Состояние изменения текста">{activities.map(activity => {
    const active = rewriteActive(activity.stage), elapsed = Math.max(0, (activity.finishedAt ?? now) - activity.startedAt);
    return <div className="rewrite-activity" key={activity.actionId} data-rewrite-stage={activity.stage}>
      <span className={active ? "rewrite-spinner" : "rewrite-result-icon"} aria-hidden="true">{!active && <Icon name={activity.stage === "saved" ? "check" : "file"} />}</span>
      <div className="rewrite-activity-copy"><strong role="status">{rewriteLabels[activity.stage]}</strong>
        {activity.detail ? <p>{activity.detail}</p> : activity.stage === "running" && elapsed >= 20000
          ? <p>Ответ ещё не получен. Можно продолжать работу с другими фрагментами или отменить запрос.</p>
          : activity.stage === "queued" ? <p>Начнём, когда освободится модель.</p> : null}</div>
      <span className="rewrite-elapsed" role="timer" aria-live="off" aria-label={`Прошло ${elapsedLabel(elapsed)}`}>{elapsedLabel(elapsed)}</span>
      {rewriteCancellable(activity.stage) && <button className="text-button" onClick={() => cancel(activity.actionId)}>Отменить правку</button>}
      {!active && <button className="icon" aria-label="Скрыть состояние правки" onClick={() => dismiss(activity.actionId)}><Icon name="close" /></button>}
    </div>;
  })}</section>;
}
