import { useState } from "react";
import type { GuiProjectListResponse } from "../../contracts/generated/gui_project_list_response";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";

export function History({ projects, activeId, busy, collapse, fresh, open, remove, archive, openFile, settings, connection, activity }: {
  projects: GuiProjectListResponse | null; activeId: string | null; busy: boolean; collapse: () => void;
  fresh: () => void; open: (id: string) => Promise<boolean>; remove: (id: string) => Promise<boolean>;
  archive: (id: string, archived: boolean) => Promise<boolean>;
  openFile: () => void; settings: () => void; connection: string;
  activity?: ReadonlyMap<string, string>;
}) {
  const [deleting, setDeleting] = useState<string | null>(null);
  const [archived, setArchived] = useState(false);
  const entries = (projects?.entries.filter(item => Boolean(item.archived) === archived) ?? [])
    .sort((a, b) => Number(b.projectId === activeId) - Number(a.projectId === activeId)
      || (b.lastOpenedAt || b.updatedAt).localeCompare(a.lastOpenedAt || a.updatedAt) || b.projectId.localeCompare(a.projectId));
  return <aside className="history" aria-label="История резюме" aria-busy={busy}>
    <div className="brand-row"><button className="brand" disabled={busy} aria-label="FoldCV — новый исходник" onClick={fresh}><Icon name="fold" />FoldCV<span>.</span></button>
      <button className="icon" aria-label="Свернуть историю" onClick={collapse}><Icon name="panel" /></button></div>
    <Button className="new-button" disabled={busy} onClick={fresh}><Icon name="plus" />Новое резюме</Button>
    <div className="history-heading"><span className="eyebrow">{archived ? "Архив" : "Ваши резюме"}</span><span>{entries.length}</span></div>
    <button className="history-open" aria-pressed={archived} onClick={() => setArchived(value => !value)}>{archived ? "Активные резюме" : "Архив"}</button>
    <div className="project-list">{!entries.length && <p className="empty-state">{archived ? "Архив пуст." : "Здесь появятся ваши резюме."}</p>}
      {entries.map(item => <div className={`project-row${item.projectId === activeId ? " active" : ""}`} key={item.projectId}>
        <button className="project-select" disabled={busy || item.tombstoned} aria-current={item.projectId === activeId ? "page" : undefined} onClick={() => void open(item.projectId)}>
          <strong>{item.title}</strong>{item.subtitle && <small>{item.subtitle}</small>}<em>{item.tombstoned ? "Очистка не завершена — повторите удаление" : projects?.errors.some(error => error.projectId === item.projectId) ? "Не удалось прочитать" : activity?.get(item.projectId) ?? "Рабочая версия"}</em>
        </button><button className="project-archive" disabled={busy || item.tombstoned} aria-label={`${archived ? "Восстановить" : "В архив"}: ${item.title}`}
          onClick={() => void archive(item.projectId, !archived)}>{archived ? "Вернуть" : "В архив"}</button>
        <button className="project-delete" disabled={busy} aria-label={`Удалить проект: ${item.title}`} title="Удалить резюме" onClick={() => setDeleting(item.projectId)}><Icon name="trash" /></button>
      </div>)}
    </div>
    <button className="history-open" disabled={busy} onClick={openFile}><Icon name="upload" />Открыть .foldcv</button>
    <footer className="history-footer"><div className="connection-mini"><span className="dot" /><span>{connection}</span></div>
      <button disabled={busy} onClick={settings}><Icon name="settings" />Настройки<Icon name="chevron" /></button></footer>
    <Dialog open={deleting !== null} close={() => setDeleting(null)} title="Удалить резюме?">
      <p className="dialog-copy">Проект и его локальные файлы будут удалены.</p><div className="dialog-actions">
        <Button disabled={busy} onClick={() => setDeleting(null)}>Отмена</Button><Button variant="danger" busy={busy} busyLabel="Удаляем…" onClick={() => { if (deleting) void remove(deleting).then(done => { if (done) setDeleting(null); }); }}>Удалить окончательно</Button>
      </div>
    </Dialog>
  </aside>;
}
