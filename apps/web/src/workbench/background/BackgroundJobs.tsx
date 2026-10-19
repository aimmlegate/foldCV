import { useEffect, useRef, useState } from "react";
import type { JobSummaryV1 } from "../../contracts/generated/background_summary_v1";
import type { JobSnapshotV1 } from "../../contracts/generated/background_snapshot_v1";
import { JobsApi } from "../../background/api";
import type { GlobalJobs, GlobalJobsView } from "../../background/global";
import { active, attention, failureLabel, jobKey, operationLabel, statusLabel } from "../../background/status";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { OperationStatus, Spinner } from "../ui/OperationStatus";
import { NotificationSection } from "../ui/NotificationCenter";

type Details = { key: string; job: JobSnapshotV1; text: string | null };
type Props = { registry: GlobalJobs; view: GlobalJobsView; openProject: (project: string) => Promise<boolean> };

export function BackgroundJobs({ registry, view, openProject }: Props) {
  const [open, setOpen] = useState(false), [page, setPage] = useState(0), [details, setDetails] = useState<Details | null>(null);
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set()), [error, setError] = useState("");
  const [inspecting, setInspecting] = useState<string | null>(null), [refreshing, setRefreshing] = useState(false);
  const host = useRef<HTMLDivElement>(null), ticket = useRef(0);
  function close() { ticket.current++; setOpen(false); setDetails(null); setInspecting(null); setError(""); }
  async function refresh() { setRefreshing(true); try { await registry.refresh(); } catch { /* The registry keeps its last state and exposes the error. */ } finally { setRefreshing(false); } }
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
    setDetails(null); setError(""); setInspecting(key);
    try {
      const api = new JobsApi(job.projectId), current = await api.read(job.jobId);
      if (current.id !== job.jobId || current.submission.identity.lineage !== job.lineage
        || current.submission.identity.projectId !== job.projectId) throw new Error("INVALID_RESULT");
      const conversation = current.submission.kind === "agent" ? await api.conversation(job.jobId) : null;
      const text = conversation?.messages.filter(message => message.runId === job.jobId && message.role === "assistant").at(-1)?.text ?? null;
      if (request === ticket.current) setDetails({ key, job: current, text });
    } catch { if (request === ticket.current) setError("Не удалось прочитать результат. Повторите попытку."); }
    finally { if (request === ticket.current) setInspecting(null); }
  }
  async function show(job: JobSummaryV1) { if (await openProject(job.projectId)) close(); }
  const ordered = [...view.jobs].sort((a, b) => Number(active(b)) - Number(active(a)) || Number(attention(b)) - Number(attention(a))
    || b.updatedAt.localeCompare(a.updatedAt) || jobKey(a).localeCompare(jobKey(b)));
  const pages = Math.max(1, Math.ceil(ordered.length / 20)), currentPage = Math.min(page, pages - 1);
  const rows = ordered.slice(currentPage * 20, (currentPage + 1) * 20), count = view.jobs.filter(active).length;
  const review = view.jobs.filter(attention).length;
  return <div className="global-job-control" ref={host}>
    <Button variant="quiet" aria-label="Фоновая работа" aria-expanded={open} aria-controls="global-jobs" onClick={() => {
      if (open) close(); else { setOpen(true); setPage(0); void refresh(); }
    }}>{count > 0 ? <Spinner /> : <Icon name="list" />}Задачи{count > 0 && <span className="job-count">{count}</span>}{review > 0 && <span className="job-attention" aria-label="Есть задачи для проверки">!</span>}</Button>
    <section id="global-jobs" className="global-jobs" role="region" aria-label="Фоновая работа" hidden={!open}
      onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
      <div className="job-panel-heading"><h2>Фоновая работа</h2>{refreshing && <Spinner />}<button className="icon" aria-label="Закрыть список задач" onClick={close}><Icon name="close" /></button></div>
      {(view.error || error) && <p role="alert" className="job-error">{error || "Не удалось обновить задачи. Последнее известное состояние сохранено."}</p>}
      {view.error && <Button variant="quiet" busy={refreshing} busyLabel="Обновляем…" onClick={() => void refresh()}>Обновить состояние</Button>}
      {!rows.length && (refreshing ? <OperationStatus label="Загружаем задачи" /> : <p className="dialog-copy">Фоновых задач пока нет.</p>)}
      <ul className="job-list">{rows.map(job => {
        const key = jobKey(job), reason = failureLabel(job.publicationError?.code ?? job.error?.code);
        return <li key={key} data-job-id={job.jobId} data-project-id={job.projectId}>
          <strong>{job.projectTitle}</strong><small>{operationLabel(job)}</small>
          <div className="job-status-line">{active(job) ? <OperationStatus state={job.publication === "outcome_unknown" ? "error" : job.execution === "queued" ? "waiting" : "working"} label={statusLabel(job)} />
            : <p className={attention(job) ? "job-warning" : "job-status"}>{statusLabel(job)}</p>}</div>
          {reason && <p className="job-reason">{reason}</p>}
          <div className="job-actions">
            <button className="text-button" onClick={() => void show(job)}>Открыть резюме</button>
            <Button variant="quiet" busy={inspecting === key} busyLabel="Читаем…" onClick={() => void inspect(job)}>Сведения</Button>
            {active(job) && <Button variant="quiet" busy={pending.has(key)} busyLabel="Останавливаем…" onClick={() => void command(job, "stop")}>Остановить задачу</Button>}
            {["needs_review", "save_failed"].includes(job.publication) && !job.saved && <Button variant="quiet" busy={pending.has(key)} busyLabel="Отбрасываем…" onClick={() => void command(job, "discard")}>Отбросить результат</Button>}
          </div>
          {details?.key === key && <div className="job-details">
            <p>{details.job.submission.allowEdits ? "Правки проходят проверку перед сохранением." : "Проверка без изменения резюме."}</p>
            {details.text && <p className="job-answer">{details.text}</p>}
            {job.saved && <p>Результат сохранён в этом резюме.</p>}
            {job.publication === "needs_review" && <p>Откройте резюме, проверьте изменённые данные и при необходимости отправьте новый запрос. Этот результат не заменяет текущий текст.</p>}
            {job.publication === "waiting_for_sync" && <p>{details.job.submission.approvalRequired ? "Откройте резюме, чтобы посмотреть и применить вариант текста." : "Откройте резюме и завершите восстановление ввода. Сохранение продолжится после синхронизации."}</p>}
          </div>}
        </li>;
      })}</ul>
      {pages > 1 && <div className="job-pages"><button className="text-button" disabled={currentPage === 0} onClick={() => { ticket.current++; setDetails(null); setPage(currentPage - 1); }}>Назад</button>
        <span>{currentPage + 1} / {pages}</span><button className="text-button" disabled={currentPage + 1 >= pages} onClick={() => { ticket.current++; setDetails(null); setPage(currentPage + 1); }}>Далее</button></div>}
    </section>
    <NotificationSection count={view.notices.length}>
      <section className="notice-group" aria-label="Фоновые задачи"><h3>Фоновые задачи</h3>
      <div className="notification-job-list">{view.notices.map(notice => <article key={notice.key} className="job-notice" data-project-id={notice.job.projectId}>
      <div><strong>{notice.job.projectTitle}</strong><p>{operationLabel(notice.job)} · {statusLabel(notice.job)}</p></div>
      <button className="icon" aria-label="Скрыть уведомление" onClick={() => registry.dismiss(notice.key)}><Icon name="close" /></button>
    </article>)}</div></section></NotificationSection>
  </div>;
}
