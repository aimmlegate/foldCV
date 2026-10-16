import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

export function Header({ title, subtitle, collapsed, expand, status, ready, busy, save, exportFile }: {
  title: string; subtitle: string; collapsed: boolean; expand: () => void; status: string; ready: boolean; busy: boolean;
  save: () => void; exportFile: () => void;
}) {
  return <header className="app-header">
    <button className="icon show-history" hidden={!collapsed} aria-label="Развернуть историю" onClick={expand}><Icon name="panel" /></button>
    <div className="project-heading"><span>{subtitle}</span><h1>{title}</h1></div>
    {ready && <div className="header-actions"><span className="session-status" role="status"><span className="dot" />{status}</span>
      <Button variant="quiet" disabled={busy} onClick={save} aria-keyshortcuts="Control+S Meta+S" title="Сохранить файл проекта (⌘S / Ctrl+S)"><Icon name="download" /><span>Сохранить</span></Button>
      <Button variant="primary" disabled={busy} onClick={exportFile}>Экспорт DOCX<Icon name="arrow" /></Button>
    </div>}
  </header>;
}
