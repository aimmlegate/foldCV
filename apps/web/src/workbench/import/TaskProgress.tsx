import { useEffect, useState } from "react";
import type { ImportDiscoveries, ProjectTask } from "../../projects/api";
import { Elapsed, Spinner } from "../ui/OperationStatus";
import { Icon } from "../ui/Icon";

export function TaskProgress({ task, cancel }: { task: ProjectTask; cancel: () => Promise<void> }) {
  const [stopping, setStopping] = useState(false);
  const found = task.detail["discoveries"] as ImportDiscoveries | undefined;
  const [quiet, setQuiet] = useState(false);
  const stamp = JSON.stringify(found);
  useEffect(() => {
    setQuiet(false);
    const timer = setTimeout(() => setQuiet(true), 20000);
    return () => clearTimeout(timer);
  }, [stamp]);
  return <section className="progress-screen" aria-label="Обработка резюме"><div className="progress-content">
    <div className="import-progress-heading"><div className="progress-icon"><Icon name="fold" /><Spinner /></div>
      <Elapsed startedAt={task.startedAt} /></div>
    <h2>Обработка резюме</h2>
    <p role="status">{task.stage === "publication" ? "Применяем макет и сохраняем документ."
      : quiet ? "Ждём следующую часть результата." : "Извлекаем и проверяем данные исходника."}</p>
    {found && <section className="import-discoveries" aria-label="Промежуточный результат">
      {(found.name || found.title) && <div className="import-found-candidate"><h3>{found.name}</h3><p>{found.title}</p></div>}
      <dl className="import-found-counts" aria-live="polite"><div><dt>Фактов</dt><dd>{found.facts}</dd></div>
        <div><dt>Мест работы</dt><dd>{found.jobCount}</dd></div><div><dt>Технологий</dt><dd>{found.technologyCount}</dd></div></dl>
      <ul className="import-found-jobs">{found.jobs.map(job => <li key={job.id}><strong>{job.employer}</strong><span>{job.role}</span></li>)}</ul>
      <ul className="import-found-technologies">{found.technologies.map(name => <li key={name}>{name}</li>)}</ul>
    </section>}
    <div className="import-progress-footer"><button type="button" className="text-button" disabled={stopping}
      onClick={() => { setStopping(true); void cancel().finally(() => setStopping(false)); }}>{stopping ? "Останавливаем…" : "Отменить обработку"}</button></div>
  </div></section>;
}
