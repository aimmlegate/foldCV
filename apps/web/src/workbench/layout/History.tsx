import { useState, type ReactNode } from "react";
import { errorMessage } from "../../errors/messages";
import type { ProjectList, ProjectListEntry } from "../../projects/api";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { historyGroups } from "./history-groups";

/** The refusal shows here: behind this modal dialog the notification badge cannot be reached. */
export function DeleteDialog({ open, busy, error, close, confirm }: { open: boolean; busy: boolean; error: string; close: () => void; confirm: () => void }) {
  return <Dialog open={open} close={close} title="Удалить резюме?">
    <p className="dialog-copy">Резюме и его файлы будут удалены навсегда.</p>
    {error && <p className="notice warning" role="alert">{errorMessage(error)}</p>}
    <div className="dialog-actions">
      <Button disabled={busy} onClick={close}>Отмена</Button><Button variant="danger" busy={busy} busyLabel="Удаляем…" onClick={confirm}>Удалить</Button>
    </div>
  </Dialog>;
}

export function History({ projects, activeId, busy, collapse, fresh, open, remove, archive, openFile, settings, connection, error, handle }: {
  projects: ProjectList | null; activeId: string | null; busy: boolean; collapse: () => void; handle?: ReactNode;
  fresh: () => void; open: (id: string) => Promise<boolean>; remove: (id: string) => Promise<boolean>;
  archive: (id: string, archived: boolean) => Promise<boolean>;
  openFile: () => void; settings: () => void; connection: string; error: string;
}) {
  const [deleting, setDeleting] = useState<string | null>(null), [refused, setRefused] = useState(false);
  const closeDelete = () => { setDeleting(null); setRefused(false); };
  const [archiveOpen, setArchiveOpen] = useState(false);
  const { current, archived } = historyGroups(projects?.entries ?? []);
  const row = (item: ProjectListEntry) => {
    const inArchive = Boolean(item.archived), archiveLabel = inArchive ? "Вернуть из архива" : "В архив";
    const status = item.tombstoned ? "Удалено не до конца — удалите снова"
      : projects?.errors.some(error => error.projectId === item.projectId) ? "Не удалось прочитать" : null;
    return <div className={`project-row${item.projectId === activeId ? " active" : ""}`} key={item.projectId}>
      <button className="project-select" disabled={busy || item.tombstoned} aria-current={item.projectId === activeId ? "page" : undefined}
        title={item.subtitle ? `${item.title} — ${item.subtitle}` : item.title} onClick={() => void open(item.projectId)}>
        <strong>{item.title}</strong>{item.subtitle && <small>{item.subtitle}</small>}{status && <em>{status}</em>}
      </button>
      <div className="project-actions">
        <button className="project-archive" disabled={busy || item.tombstoned} aria-label={`${archiveLabel}: ${item.title}`} title={archiveLabel}
          onClick={() => void archive(item.projectId, !inArchive)}><Icon name={inArchive ? "undo" : "archive"} /></button>
        <button className="project-delete" disabled={busy} aria-label={`Удалить: ${item.title}`} title="Удалить" onClick={() => setDeleting(item.projectId)}><Icon name="trash" /></button>
      </div>
    </div>;
  };
  return <aside className="history" aria-label="Список резюме" aria-busy={busy}>
    {handle}
    <div className="brand-row"><button className="brand" disabled={busy} aria-label="FoldCV — новое резюме" onClick={fresh}><Icon name="fold" /><span className="brand-name">FoldCV<span>.</span></span></button>
      <button className="icon" aria-label="Скрыть список резюме" onClick={collapse}><Icon name="panel" /></button></div>
    <Button className="new-button" disabled={busy} onClick={fresh}><Icon name="plus" />Новое резюме</Button>
    <div className="history-heading"><span className="eyebrow">Резюме</span><span>{current.length}</span></div>
    <div className="project-list">
      {!current.length && <p className="empty-state">{archived.length ? "Все резюме в архиве." : "Резюме пока нет."}</p>}
      {current.map(row)}
      {archived.length > 0 && <div className="history-archive">
        <button className="archive-toggle" aria-expanded={archiveOpen} aria-controls="history-archive-list" onClick={() => setArchiveOpen(value => !value)}>
          <Icon name="chevron" /><span className="eyebrow">Архив</span><span className="archive-count">{archived.length}</span>
        </button>
        <div className="archive-list" id="history-archive-list" hidden={!archiveOpen}>{archived.map(row)}</div>
      </div>}
    </div>
    <footer className="history-footer">
      <button className="history-file" disabled={busy} onClick={openFile}><Icon name="upload" />Открыть .foldcv</button>
      <div className="connection-mini"><span className="dot" /><span>{connection}</span></div>
      <button className="history-settings" disabled={busy} onClick={settings}><Icon name="settings" />Настройки<Icon name="chevron" /></button>
    </footer>
    <DeleteDialog open={deleting !== null} busy={busy} error={refused ? error : ""} close={closeDelete} confirm={() => {
      if (deleting) { setRefused(false); void remove(deleting).then(done => { if (done) closeDelete(); else setRefused(true); }); }
    }} />
  </aside>;
}
