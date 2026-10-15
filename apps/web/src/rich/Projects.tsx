import { useState } from "react";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";

export function Projects({ list, busy, activeId, open, remove }: { list: GuiProjectListResponse | null; busy: boolean; activeId: string | null;
  open: (id: string) => Promise<boolean>; remove: (id: string) => Promise<boolean> }) {
  const [deleting, setDeleting] = useState<string | null>(null);
  return <section aria-label="Сохранённые резюме"><h2>Резюме</h2>
    {list && !list.entries.some(entry => !entry.tombstoned) && <p className="next-selected">Здесь появятся ваши резюме.</p>}
    {list?.entries.filter(entry => !entry.tombstoned).map(entry => <div className="rich-project-row" key={entry.projectId}>
      <button className="rich-project-title" aria-current={activeId === entry.projectId ? "page" : undefined} disabled={busy} onClick={() => void open(entry.projectId)}>
        <span>{entry.title}</span>{entry.subtitle && <small className="rich-project-subtitle">{entry.subtitle}</small>}
      </button>
      {list.errors.some(error => error.projectId === entry.projectId && error.errorCode === "PROJECT_VERSION_UNSUPPORTED") ? <span> Другая версия</span> : <div className="rich-project-actions">
        <button disabled={busy} aria-label={`Удалить проект: ${entry.title}`} onClick={() => setDeleting(entry.projectId)}>Удалить</button>
      </div>}
      {deleting === entry.projectId && <div><p>Удалить проект и его локальные файлы?</p><button disabled={busy} onClick={() => void remove(entry.projectId).then(deleted => { if (deleted) setDeleting(null); })}>Удалить окончательно</button>
        <button disabled={busy} onClick={() => setDeleting(null)}>Отмена</button></div>}
    </div>)}
  </section>;
}
