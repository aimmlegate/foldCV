import { useEffect, useState } from "react";
import { errorMessage } from "../../errors/messages";
import type { ImportDiscoveries, ImportPhase } from "../../projects/api";
import { Elapsed, Spinner } from "../ui/OperationStatus";
import { Icon } from "../ui/Icon";
import { agoText, currentText, importProgress, importView, modelQuietSeconds, rotatingWord, stepText, type ImportEntry } from "./progress";

const stages = ["Читаем исходник", "Извлекаем данные", "Собираем документ"] as const;
const stageOf: Record<ImportPhase, number> = { starting: 0, queued: 0, processing: 1, publication: 2 };

// The step and its block already show in the stage list; the live line adds only what it lacks.
function liveText(phase: ImportPhase): string {
  if (phase === "queued") return "Модель занята, ждём очереди.";
  if (phase === "starting") return "Готовим импорт.";
  return "";
}

export function TaskProgress({ entry, source, busy, stop, retry, close, open }: {
  entry: ImportEntry; source: { name: string; pages: number; excerpt: string }; busy: boolean;
  stop: () => void; retry: () => void; close: () => void; open: () => void;
}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const view = importView(entry, now), progress = importProgress(entry.task);
  const found = entry.task.detail["discoveries"] as ImportDiscoveries | undefined;
  const running = view.kind === "running";
  const phase: ImportPhase = running ? view.phase : progress?.phase ?? "processing";
  const index = view.kind === "succeeded" ? stages.length : stageOf[phase];
  const step = stepText(progress), current = currentText(progress);
  const seconds = (now - Date.parse(entry.task.startedAt)) / 1000;
  const modelQuiet = modelQuietSeconds(entry, now);
  const finishedAt = running || view.kind === "stalled" ? undefined : Date.parse(entry.task.startedAt) + entry.task.elapsed * 1000;
  const jobs = found?.jobs.filter(job => job.employer || job.role) ?? [];
  const saved = !!found && found.facts > 0;
  return <section className="progress-screen" aria-label="Импорт резюме"><div className="progress-content">
    <div className="import-progress-heading"><div className="progress-icon"><Icon name="fold" />{running && <Spinner />}</div>
      <Elapsed startedAt={entry.task.startedAt} finishedAt={finishedAt} active={running || view.kind === "stalled"} /></div>
    <h2>Импорт резюме</h2>{source.name && <p className="import-source-name">{source.name}</p>}
    <div className="import-progress-grid">
      <div className="import-process">
        <ol className="progress-list" aria-label="Этапы импорта">{stages.map((label, position) => {
          const state = position < index ? "done" : position === index ? "current" : "";
          return <li key={label} className={state} aria-current={position === index ? "step" : undefined}>
            <span className="step-indicator" aria-hidden="true">{position < index ? <Icon name="check" />
              : position === index && running ? <Spinner /> : position + 1}</span>
            <span className="import-stage-copy">{label}
              {position === 1 && position === index && step && <small>{step}{current && ` · ${current}`}</small>}
              {position === 0 && position === index && phase === "queued" && <small>В очереди</small>}</span>
          </li>;
        })}</ol>
        {running && <>
          <div className="import-live-message" role="status"><span className="import-activity-dot" aria-hidden="true" />
            <p>{liveText(phase)} <span className="import-rotating">{rotatingWord(phase, seconds)}</span></p></div>
          <p className="import-signs">{modelQuiet === null ? "Модель ещё не вызывалась." : `Последняя активность модели: ${agoText(modelQuiet)}.`}</p>
        </>}
        {view.kind === "stalled" && <div className="import-problem" role="alert"><strong>Импорт не отвечает</strong>
          <p>{errorMessage(view.code)} Последнее событие: {agoText(view.quietSeconds)}.</p>
          <div className="import-problem-actions"><button type="button" className="button primary" disabled={entry.retrying} onClick={retry}>
            {entry.retrying ? "Повторяем…" : "Повторить"}</button>
            <button type="button" className="text-button" onClick={close}>Закрыть</button></div></div>}
        {view.kind === "failed" && <div className="import-problem" role="alert"><strong>{view.lost ? "Нет связи с импортом" : "Импорт не удался"}</strong>
          <p>{errorMessage(view.code)}</p>
          <div className="import-problem-actions"><button type="button" className="button primary" disabled={entry.retrying} onClick={retry}>
            {entry.retrying ? "Повторяем…" : "Повторить"}</button>
            <button type="button" className="text-button" onClick={close}>Закрыть</button></div></div>}
        {view.kind === "cancelled" && <div className="import-problem neutral" role="status"><strong>Импорт остановлен</strong>
          <p>Готовые шаги сохранены.</p>
          <div className="import-problem-actions"><button type="button" className="button primary" disabled={entry.retrying} onClick={retry}>
            {entry.retrying ? "Продолжаем…" : "Продолжить импорт"}</button>
            <button type="button" className="text-button" onClick={close}>Закрыть</button></div></div>}
        {view.kind === "succeeded" && <div className="import-problem neutral" role="status"><strong>Импорт завершён</strong>
          <div className="import-problem-actions"><button type="button" className="button primary" disabled={busy} onClick={open}>
            {busy ? "Открываем…" : "Открыть резюме"}</button></div></div>}
        {progress && progress.events.length > 0 && <section className="import-activity" aria-label="События импорта">
          <h4>События</h4>
          <ol>{progress.events.map(event => <li key={`${event.at}:${event.text}`}>
            <time dateTime={event.at}>{new Date(event.at).toLocaleTimeString("ru-RU")}</time><span>{event.text}</span></li>)}</ol>
        </section>}
      </div>
      <section className="import-discoveries" aria-label="Найдено">
        <div className="import-discoveries-heading"><span>{saved ? "Найдено" : "Текст исходника"}</span>
          <Icon name={saved ? "check" : "file"} /></div>
        {saved && found ? <>
          {(found.name || found.title) && <div className="import-found-candidate">{found.name && <h3>{found.name}</h3>}{found.title && <p>{found.title}</p>}</div>}
          <dl className="import-found-counts" aria-live="polite" aria-atomic="true">
            <div><dt>Фактов</dt><dd>{found.facts}</dd></div><div><dt>Мест работы</dt><dd>{found.jobCount}</dd></div>
            <div><dt>Технологий</dt><dd>{found.technologyCount}</dd></div>
          </dl>
          {jobs.length > 0 && <div className="import-found-group"><h4>Опыт работы</h4><ul className="import-found-jobs">
            {jobs.map(job => <li key={job.id}><strong>{job.employer || job.role}</strong>{job.employer && job.role && <span>{job.role}</span>}</li>)}
          </ul>{found.jobCount > jobs.length && <p className="import-found-more">Ещё {found.jobCount - jobs.length}</p>}</div>}
          {found.technologies.length > 0 && <div className="import-found-group"><h4>Технологии</h4><ul className="import-found-technologies">
            {found.technologies.map(name => <li key={name}>{name}</li>)}
          </ul>{found.technologyCount > found.technologies.length && <p className="import-found-more">Ещё {found.technologyCount - found.technologies.length}</p>}</div>}
        </> : <>
          {source.pages > 0 && <p className="import-source-pages">Страниц с текстом: {source.pages}</p>}
          {source.excerpt && <blockquote className="import-source-excerpt">{source.excerpt}</blockquote>}
        </>}
      </section>
    </div>
    {running && <div className="import-progress-footer"><button type="button" className="text-button" disabled={entry.stopping} onClick={stop}>
      {entry.stopping && <Spinner />}{entry.stopping ? "Останавливаем…" : "Остановить импорт"}</button>
      <span>Можно перейти к другому резюме: импорт продолжится.</span></div>}
  </div></section>;
}
