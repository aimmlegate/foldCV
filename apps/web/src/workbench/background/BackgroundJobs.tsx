import { useEffect, useRef, useState } from "react";
import type { JobSummaryV1 } from "../../contracts/generated/background_summary_v1";
import type { JobSnapshotV1 } from "../../contracts/generated/background_snapshot_v1";
import { JobsApi } from "../../background/api";
import type { GlobalJobs, GlobalJobsView } from "../../background/global";
import { active, attention, failureLabel, jobKey, operationLabel, statusLabel } from "../../background/status";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

type Details = { key: string; job: JobSnapshotV1; text: string | null };
type Props = { registry: GlobalJobs; view: GlobalJobsView; openProject: (project: string) => Promise<boolean> };

export function BackgroundJobs({ registry, view, openProject }: Props) {
  const [open, setOpen] = useState(false), [page, setPage] = useState(0), [details, setDetails] = useState<Details | null>(null);
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set()), [error, setError] = useState("");
  const host = useRef<HTMLDivElement>(null), ticket = useRef(0);
  function close() { ticket.current++; setOpen(false); setDetails(null); setError(""); }
  useEffect(() => () => { ticket.current++; }, []);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !host.current?.contains(event.target)) close(); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  async function command(job: JobSummaryV1, action: "stop" | "discard") {
    const key = jobKey(job);
    setPending(current => new Set([...current, key])); setError("");
    try { await registry.command(job, action); }
    catch { setError("Не удалось выполнить действие. Обновите состояние и повторите попытку."); }
    finally { setPending(current => new Set([...current].filter(value => value !== key))); }
  }
  async function inspect(job: JobSummaryV1) {
    const request = ++ticket.current, key = jobKey(job);
    setDetails(null); setError("");
    try {
      const api = new JobsApi(job.projectId), current = await api.read(job.jobId);
      if (current.id !== job.jobId || current.submission.identity.lineage !== job.lineage
        || current.submission.identity.projectId !== job.projectId) throw new Error("INVALID_RESULT");
      const conversation = current.submission.kind === "agent" ? await api.conversation(job.jobId) : null;
      const text = conversation?.messages.filter(message => message.runId === job.jobId && message.role === "assistant").at(-1)?.text ?? null;
      if (request === ticket.current) setDetails({ key, job: current, text });
    } catch { if (request === ticket.current) setError("Не удалось прочитать результат. Повторите попытку."); }
  }
  async function show(job: JobSummaryV1) { if (await openProject(job.projectId)) close(); }
  const ordered = [...view.jobs].sort((a, b) => Number(active(b)) - Number(active(a)) || Number(attention(b)) - Number(attention(a))
    || b.updatedAt.localeCompare(a.updatedAt) || jobKey(a).localeCompare(jobKey(b)));
  const pages = Math.max(1, Math.ceil(ordered.length / 20)), currentPage = Math.min(page, pages - 1);
  const rows = ordered.slice(currentPage * 20, (currentPage + 1) * 20), count = view.jobs.filter(active).length;
  const review = view.jobs.filter(attention).length;
  return <div className="global-job-control" ref={host}>
    <Button variant="quiet" aria-label="Фоновая работа" aria-expanded={open} aria-controls="global-jobs" onClick={() => {
      if (open) close(); else { setOpen(true); setPage(0); void registry.refresh().catch(() => {}); }
    }}><Icon name="list" />Задачи{count > 0 && <span className="job-count">{count}</span>}{review > 0 && <span className="job-attention" aria-label="Есть задачи для проверки">!</span>}</Button>
    <section id="global-jobs" className="global-jobs" role="region" aria-label="Фоновая работа" hidden={!open}
      onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
      <div className="job-panel-heading"><h2>Фоновая работа</h2><button className="icon" aria-label="Закрыть список задач" onClick={close}><Icon name="close" /></button></div>
      {(view.error || error) && <p role="alert" className="job-error">{error || "Не удалось обновить задачи. Последнее известное состояние сохранено."}</p>}
      {view.error && <button className="text-button" onClick={() => void registry.refresh().catch(() => {})}>Обновить состояние</button>}
      {!rows.length && <p className="dialog-copy">Фоновых задач пока нет.</p>}
      <ul className="job-list">{rows.map(job => {
        const key = jobKey(job), reason = failureLabel(job.publicationError?.code ?? job.error?.code);
        return <li key={key} data-job-id={job.jobId} data-project-id={job.projectId}>
          <strong>{job.projectTitle}</strong><small>{operationLabel(job)}</small><p className={attention(job) ? "job-warning" : "job-status"}>{statusLabel(job)}</p>
          {reason && <p className="job-reason">{reason}</p>}
          <div className="job-actions">
            <button className="text-button" onClick={() => void show(job)}>Открыть резюме</button>
            <button className="text-button" onClick={() => void inspect(job)}>Сведения</button>
            {active(job) && <button className="text-button" disabled={pending.has(key)} onClick={() => void command(job, "stop")}>Остановить задачу</button>}
            {["needs_review", "save_failed"].includes(job.publication) && !job.saved && <button className="text-button" disabled={pending.has(key)} onClick={() => void command(job, "discard")}>Отбросить результат</button>}
          </div>
          {details?.key === key && <div className="job-details">
            <p>{details.job.submission.allowEdits ? "Правки проходят проверку перед сохранением." : "Проверка без изменения резюме."}</p>
            {details.text && <p className="job-answer">{details.text}</p>}
            {job.saved && <p>Результат сохранён в этом резюме.</p>}
            {job.publication === "needs_review" && <p>Откройте резюме, проверьте изменённые данные и при необходимости отправьте новый запрос. Этот результат не заменяет текущий текст.</p>}
            {job.publication === "waiting_for_sync" && <p>Откройте резюме и завершите восстановление ввода. Сохранение продолжится после синхронизации.</p>}
          </div>}
        </li>;
      })}</ul>
      {pages > 1 && <div className="job-pages"><button className="text-button" disabled={currentPage === 0} onClick={() => { ticket.current++; setDetails(null); setPage(currentPage - 1); }}>Назад</button>
        <span>{currentPage + 1} / {pages}</span><button className="text-button" disabled={currentPage + 1 >= pages} onClick={() => { ticket.current++; setDetails(null); setPage(currentPage + 1); }}>Далее</button></div>}
    </section>
    <div className="job-notices" aria-live="polite" aria-atomic="false">{view.notices.map(notice => <article key={notice.key} className="job-notice" data-project-id={notice.job.projectId}>
      <div><strong>{notice.job.projectTitle}</strong><p>{operationLabel(notice.job)} · {statusLabel(notice.job)}</p></div>
      <button className="icon" aria-label="Скрыть уведомление" onClick={() => registry.dismiss(notice.key)}><Icon name="close" /></button>
    </article>)}</div>
  </div>;
}
