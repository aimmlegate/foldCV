import { useState } from "react";
import { Icon } from "../ui/Icon";
import { OriginalPreview } from "./OriginalPreview";
import { originalUrl } from "./original-source";

type SourceFile = { id: string; originalName: string; byteSha256: string };

export function SourceDialog({ projectId, sources, expanded, toggle, close, version = "v1" }: {
  projectId: string; sources: SourceFile[]; expanded: boolean; toggle: () => void; close: () => void; version?: "v1" | "v2";
}) {
  const [id, setId] = useState(sources[0]?.id ?? "");
  const source = sources.find(item => item.id === id) ?? sources[0];
  return <div id="original-source-panel" className="source-viewer"
    onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
    <div className="workspace-pane-heading">
      <div className="workspace-pane-title"><h2>Оригинал</h2><span>Только просмотр</span></div>
      {source && <a className="icon" aria-label="Скачать оригинал" title="Скачать оригинал" href={`${originalUrl(projectId, source.id, version)}/download`} download><Icon name="download" /></a>}
      <button className="icon" aria-label={expanded ? "Сравнить рядом" : "Развернуть оригинал"} title={expanded ? "Сравнить рядом" : "Развернуть оригинал"} onClick={toggle}><Icon name={expanded ? "panel" : "expand"} /></button>
      <button className="icon" aria-label="Закрыть оригинал" title="Закрыть оригинал" onClick={close}><Icon name="close" /></button></div>
    <div className="source-viewer-file">
      {sources.length > 1 ? <select aria-label="Источник" value={source?.id ?? ""} onChange={event => setId(event.currentTarget.value)}>
        {sources.map(item => <option key={item.id} value={item.id}>{item.originalName}</option>)}
      </select> : <span title={source?.originalName}>{source?.originalName ?? "Источник отсутствует"}</span>}
      <span className="source-file-type">{source?.originalName.split(".").pop()?.toUpperCase()}</span>
    </div>
    {source && <OriginalPreview key={`${projectId}:${source.id}:${source.byteSha256}`} projectId={projectId} source={source} version={version} />}
  </div>;
}
