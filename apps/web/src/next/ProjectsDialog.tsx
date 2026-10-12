import { useEffect, useRef, useState } from "react";
import type { RegistryEntry } from "../contracts/generated/registry";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import type { useEdits } from "./useEdits";
import { deleteProjectRequest, projectListRequest, projectRequest, renameProjectRequest, type Workspace } from "./api";

type Props = { workspace: Workspace | null; edits: ReturnType<typeof useEdits>; accept: (response: GuiProjectResponse) => void; close: () => void };
export function ProjectsDialog({ workspace, edits, accept, close }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [list, setList] = useState<GuiProjectListResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [renaming, setRenaming] = useState<RegistryEntry | null>(null);
  const [title, setTitle] = useState("");
  const [deleting, setDeleting] = useState<RegistryEntry | null>(null);
  const deletedCurrent = useRef(false);
  async function refresh() {
    try { setList(await projectListRequest()); }
    catch { setError("Не удалось прочитать список проектов. Повторите открытие."); }
  }
  function dismiss() {
    if (deletedCurrent.current || list?.entries.some(entry => entry.projectId === workspace?.projectId && entry.tombstoned)) location.assign("/next.html");
    else close();
  }
  useEffect(() => {
    const element = dialog.current;element?.showModal();void refresh();
    return () => element?.close();
  }, []);
  async function navigate(id?: string) {
    setBusy(true);setError("");
    try {
      if (!await edits.flushBeforeAction(true)) { setError("Завершите ввод и сохраните правки перед переключением проекта.");return; }
      if (id) await projectRequest(`/v1/projects/${id}`);
      if (!await edits.flushBeforeAction(true)) { setError("Сначала сохраните новые правки.");return; }
      location.assign(id ? `/next.html?project=${encodeURIComponent(id)}` : "/next.html");
    } catch { setError("Не удалось открыть проект. Текущие правки остаются в редакторе."); }
    finally { setBusy(false); }
  }
  async function rename() {
    if (!renaming || !title.trim()) return;
    setBusy(true);setError("");
    try {
      if (renaming.projectId === workspace?.projectId && !await edits.flushBeforeAction()) { setError("Сначала сохраните правки.");return; }
      const current = await projectRequest(`/v1/projects/${renaming.projectId}`);
      const result = await renameProjectRequest(renaming.projectId, { title: title.trim(), baseRevision: current.workspace.projectRevision });
      if (renaming.projectId === workspace?.projectId) accept(result);
      if (result.durability !== "durable") { setError("Имя изменено в окне, но запись на диск не подтверждена. Повторите сохранение имени.");return; }
      setRenaming(null);await refresh();
    } catch { setError("Не удалось сохранить имя. Обновите список и повторите действие."); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!deleting) return;
    setBusy(true);setError("");
    try {
      const result = await deleteProjectRequest(deleting.projectId);
      if (deleting.projectId === workspace?.projectId) deletedCurrent.current = true;
      await refresh();
      if (result.status === "cleanup_incomplete") {
        setError("Не удалось подтвердить удаление всех файлов. Повторите очистку; остальные проекты доступны.");return;
      }
      setDeleting(null);
      if (deletedCurrent.current) location.assign("/next.html");
    } catch { setError("Не удалось подтвердить удаление. Обновите список и повторите действие.");await refresh(); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="next-projects" aria-label="Локальные проекты" onCancel={event => { event.preventDefault();if (!busy) dismiss(); }}>
    <header><h2>Локальные проекты</h2><button disabled={busy} onClick={dismiss}>Закрыть</button></header>
    <button disabled={busy} onClick={() => { void navigate(); }}>Новое резюме</button>
    {busy && <p role="status">Выполняем действие…</p>}{error && <p role="alert" className="text-danger">{error}</p>}
    {renaming ? <form onSubmit={event => { event.preventDefault();void rename(); }}>
      <label>Имя проекта<input autoFocus value={title} maxLength={200} onChange={event => setTitle(event.target.value)} /></label>
      <button disabled={busy || !title.trim()} type="submit">Сохранить имя</button>
      <button disabled={busy} type="button" onClick={() => setRenaming(null)}>Отменить переименование</button>
    </form> : deleting ? <section aria-label="Подтверждение удаления"><h3>Удалить «{deleting.title}»?</h3>
      <p>Проект, исходники и локальные версии будут удалены. Экспортированные файлы сохранятся.</p>
      <button disabled={busy} onClick={() => { void remove(); }}>{deleting.tombstoned ? "Повторить очистку" : "Удалить проект"}</button>
      <button disabled={busy} onClick={() => setDeleting(null)}>Вернуться к списку</button>
    </section> : <ul>{list?.entries.map(entry => {
      const unreadable = list.errors.some(error => error.projectId === entry.projectId);
      return <li key={entry.projectId} data-project-id={entry.projectId}>
        <div><strong>{entry.title}</strong>{entry.projectId === workspace?.projectId && <span> · текущий</span>}
          <p>{new Date(entry.updatedAt).toLocaleString()}{entry.tombstoned ? " · удаление не завершено" : unreadable ? " · не удалось открыть" : ""}</p></div>
        <div>{!entry.tombstoned && <><button disabled={busy || unreadable} onClick={() => { void navigate(entry.projectId); }}>Открыть</button>
          <button disabled={busy || unreadable} onClick={() => { setRenaming(entry);setTitle(entry.title);setError(""); }}>Переименовать</button></>}
          <button disabled={busy} onClick={() => { setDeleting(entry);setError(""); }}>{entry.tombstoned ? "Повторить очистку" : "Удалить"}</button></div>
      </li>;
    })}</ul>}
    {list?.entries.length === 0 && <p>Сохранённых проектов пока нет.</p>}
  </dialog>;
}
