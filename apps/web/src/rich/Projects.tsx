import { useState } from "react";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";

export function Projects({ list, busy, activeId, open, rename, remove }: { list: GuiProjectListResponse | null; busy: boolean; activeId: string | null;
  open: (id: string) => Promise<boolean>; rename: (id: string, title: string) => Promise<boolean>; remove: (id: string) => Promise<boolean> }) {
  const [editing, setEditing] = useState<string | null>(null), [deleting, setDeleting] = useState<string | null>(null);
  return <section aria-label="Сохранённые резюме"><h2>Резюме</h2>
    {list && !list.entries.some(entry => !entry.tombstoned) && <p className="next-selected">Здесь появятся ваши резюме.</p>}
    {list?.entries.filter(entry => !entry.tombstoned).map(entry => <div className="rich-project-row" key={entry.projectId}>
      <button className="rich-project-title" aria-current={activeId === entry.projectId ? "page" : undefined} disabled={busy} onClick={() => void open(entry.projectId)}>{entry.title}</button>
      {list.errors.some(error => error.projectId === entry.projectId && error.errorCode === "PROJECT_VERSION_UNSUPPORTED") ? <span> Другая версия</span> : <div className="rich-project-actions">
        <button disabled={busy} aria-label={`Переименовать: ${entry.title}`} onClick={() => setEditing(entry.projectId)}>Переименовать</button>
        <button disabled={busy} aria-label={`Удалить проект: ${entry.title}`} onClick={() => setDeleting(entry.projectId)}>Удалить</button>
      </div>}
      {editing === entry.projectId && <form onSubmit={event => {
        event.preventDefault(); const value = new FormData(event.currentTarget).get("title");
        if (typeof value === "string" && value.trim()) void rename(entry.projectId, value.trim()).then(saved => { if (saved) setEditing(null); });
      }}><label>Название проекта<input aria-label="Название проекта" name="title" defaultValue={entry.title} maxLength={200} disabled={busy} /></label>
        <button disabled={busy}>Сохранить название</button><button type="button" disabled={busy} onClick={() => setEditing(null)}>Отмена</button></form>}
      {deleting === entry.projectId && <div><p>Удалить проект и его локальные файлы?</p><button disabled={busy} onClick={() => void remove(entry.projectId).then(deleted => { if (deleted) setDeleting(null); })}>Удалить окончательно</button>
        <button disabled={busy} onClick={() => setDeleting(null)}>Отмена</button></div>}
    </div>)}
  </section>;
}
