import { useEffect, useMemo, useState } from "react";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import { Icon } from "../ui/Icon";
import { elapsedLabel, importProgress, importStages, progressMessage } from "./progress-state";
import { Spinner } from "../ui/OperationStatus";

export function Progress({ response, sourceName, cancel, busy }: {
  response: RichProjectResponse & { generation: NonNullable<RichProjectResponse["generation"]> };
  sourceName: string; cancel: () => void; busy: boolean;
}) {
  const { generation } = response;
  const found = useMemo(() => importProgress(response), [response]);
  const [mountedAt] = useState(Date.now), [now, setNow] = useState(Date.now);
  const [observed, setObserved] = useState({ stamp: found.stamp, at: mountedAt });
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => { setObserved({ stamp: found.stamp, at: Date.now() }); }, [found.stamp]);
  const timestamp = Date.parse(generation.startedAt ?? "");
  const elapsed = now - (Number.isFinite(timestamp) ? timestamp : mountedAt);
  const step = Math.max(0, importStages.findIndex(item => item.stage === generation.stage));
  const message = progressMessage(generation, found.saved, (now - observed.at) / 1000);
  const jobs = found.jobs.filter(job => job.employer || job.role);
  return <section className="progress-screen" aria-label="Обработка резюме"><div className="progress-content">
    <div className="import-progress-heading"><div className="progress-icon"><Icon name="fold" /><Spinner /></div>
      <span className="import-elapsed" role="timer" aria-live="off" aria-label={`Прошло ${elapsedLabel(elapsed)}`}>{elapsedLabel(elapsed)}</span>
    </div>
    <h2>Обработка резюме</h2><p className="import-source-name">{sourceName}</p>
    <div className="import-progress-grid">
      <div className="import-process">
        <ol className="progress-list" aria-label="Этапы обработки">{importStages.map((item, index) => <li key={item.stage}
          className={index < step ? "done" : index === step ? "current" : ""} aria-current={index === step ? "step" : undefined}>
          <span className="step-indicator" aria-hidden="true">{index < step ? <Icon name="check" /> : index === step ? <Spinner /> : index + 1}</span>{item.label}
        </li>)}</ol>
        <div className="import-live-message" role="status"><span className="import-activity-dot" aria-hidden="true" /><p>{message}</p></div>
      </div>
      <section className="import-discoveries" aria-label="Промежуточный результат">
        <div className="import-discoveries-heading"><span>{found.saved ? "Уже в черновике" : "Исходный текст готов"}</span>
          <Icon name={found.saved ? "check" : "file"} /></div>
        {found.saved ? <>
          {(found.name || found.title) && <div className="import-found-candidate">{found.name && <h3>{found.name}</h3>}{found.title && <p>{found.title}</p>}</div>}
          <dl className="import-found-counts" aria-live="polite" aria-atomic="true">
            <div><dt>Фактов</dt><dd>{found.facts}</dd></div><div><dt>Мест работы</dt><dd>{found.jobs.length}</dd></div>
            <div><dt>Технологий</dt><dd>{found.technologies.length}</dd></div>
          </dl>
          {jobs.length > 0 && <div className="import-found-group"><h4>Опыт работы</h4><ul className="import-found-jobs">
            {jobs.slice(0, 3).map(job => <li key={job.id}><strong>{job.employer || job.role}</strong>{job.employer && job.role && <span>{job.role}</span>}</li>)}
          </ul>{jobs.length > 3 && <p className="import-found-more">Ещё мест работы: {jobs.length - 3}</p>}</div>}
          {found.technologies.length > 0 && <div className="import-found-group"><h4>Технологии</h4><ul className="import-found-technologies">
            {found.technologies.slice(0, 8).map(name => <li key={name}>{name}</li>)}
          </ul>{found.technologies.length > 8 && <p className="import-found-more">Ещё технологий: {found.technologies.length - 8}</p>}</div>}
          <p className="import-discovery-note">Это промежуточные сведения. После обработки их можно будет исправить.</p>
        </> : <>
          {found.pages > 0 && <p className="import-source-pages">Страниц с текстом: {found.pages}</p>}
          {found.excerpt && <blockquote className="import-source-excerpt">{found.excerpt}</blockquote>}
          <p className="import-discovery-note">Здесь появятся найденные места работы, технологии и другие факты.</p>
        </>}
      </section>
    </div>
    <div className="import-progress-footer"><button className="text-button" disabled={busy} onClick={cancel}>{busy && <Spinner />}{busy ? "Останавливаем…" : "Отменить обработку"}</button>
      <span>Редактирование откроется после обработки</span></div>
  </div></section>;
}
