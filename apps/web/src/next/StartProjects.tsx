import { useEffect, useState } from "react";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import { projectListRequest } from "./api";

export function StartProjects({ refreshKey, disabled, open, manage }: { refreshKey: string; disabled: boolean; open: (id: string) => void; manage: () => void }) {
  const [list, setList] = useState<GuiProjectListResponse | null>(null), [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let alive = true;setError(false);
    void projectListRequest().then(value => { if (alive) setList(value); }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [refreshKey, reload]);
  const entries = list?.entries.filter(entry => !entry.tombstoned) ?? [];
  return <section className="next-recent" aria-label="Сохранённые проекты">
    <div><h2>Сохранённые проекты</h2><button disabled={disabled} onClick={manage}>Все проекты</button></div>
    {error ? <p role="alert">Не удалось прочитать проекты. <button onClick={() => setReload(value => value + 1)}>Обновить список</button></p>
      : list === null ? <p role="status">Читаем список проектов…</p> : entries.length === 0 ? <p>Пока нет сохранённых проектов.</p>
        : <ul>{entries.slice(0, 5).map(entry => <li key={entry.projectId} data-start-project={entry.projectId}>
          <button disabled={disabled || list.errors.some(error => error.projectId === entry.projectId)} onClick={() => open(entry.projectId)}>{entry.title}</button>
          <time dateTime={entry.updatedAt}>{new Date(entry.updatedAt).toLocaleString()}</time>
        </li>)}</ul>}
  </section>;
}
