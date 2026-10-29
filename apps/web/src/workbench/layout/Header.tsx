import { messageText } from "../../errors/messages";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { useEffect, useState, type ReactNode } from "react";
import { Spinner } from "../ui/OperationStatus";

export function Header({ title, subtitle, collapsed, expand, status, ready, busy, save, exportFile, activity, retrySave, rename }: {
  title: string; subtitle: string; collapsed: boolean; expand: () => void; status: string; ready: boolean; busy: boolean;
  save: () => void; exportFile: () => void;
  activity?: ReactNode;
  retrySave?: (() => void) | undefined;
  rename?: ((title: string) => void) | undefined;
}) {
  const [editing, setEditing] = useState(false), [draft, setDraft] = useState(title);
  useEffect(() => { setDraft(title); }, [title]);
  return <header className="app-header" aria-busy={busy}>
    <button className="icon show-history" hidden={!collapsed} aria-label="Показать список резюме" onClick={expand}><Icon name="panel" /></button>
    <div className="project-heading"><span>{subtitle}</span>{editing && rename ? <form onSubmit={event => {
      event.preventDefault(); const next = draft.trim(); if (next && next !== title) rename(next); setEditing(false);
    }}>
      <input aria-label="Название резюме" value={draft} maxLength={200} onChange={event => setDraft(event.target.value)} />
      <button type="submit">Сохранить</button>
      <button type="button" onClick={() => { setDraft(title); setEditing(false); }}>Отмена</button>
    </form> : <h1>{title}</h1>}
    {rename && !editing && <button type="button" className="text-button" aria-label="Переименовать" disabled={busy} onClick={() => setEditing(true)}>Переименовать</button>}</div>
    {(ready || activity) && <div className="header-actions">{activity}{ready && <><span className={`session-status${retrySave ? " save-issue" : ""}`} role="status" title={messageText(status)}>{status === "Изменения сохраняются…" ? <Spinner /> : <span className="dot" />}<span className="save-status-label">{retrySave ? "Не сохранено" : messageText(status)}</span>
      {retrySave && <button className="text-button retry-save" aria-label="Повторить сохранение" title="Повторить сохранение" disabled={busy} onClick={retrySave}><Icon name="redo" /><span>Повторить</span></button>}</span>
      <Button variant="quiet" disabled={busy} onClick={save} aria-label="Сохранить" aria-keyshortcuts="Control+S Meta+S" title="Сохранить в файл .foldcv (⌘S)"><Icon name="download" /><span>Сохранить</span></Button>
      <Button variant="primary" disabled={busy} onClick={exportFile} aria-label="Экспорт DOCX"><span className="export-label">Экспорт</span>DOCX<Icon name="arrow" /></Button>
    </>}</div>}
  </header>;
}
