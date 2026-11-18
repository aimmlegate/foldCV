import { useState } from "react";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { Icon } from "../ui/Icon";
import { OriginalPreview } from "./OriginalPreview";
import { originalKind, originalUrl } from "./original-source";
import { unshownClass, unshownLabels, type Unshown, type UnshownReason } from "./unshown";

type SourceFile = { id: string; originalName: string; byteSha256: string };

const reasons: readonly UnshownReason[] = ["no_field", "hidden", "dropped", "changed"];

/** `unshown`: the lines of the original the resume does not show; a PDF and a DOCX mark them. */
export function SourceDialog({ projectId, sources, expanded, toggle, close, unshown }: {
  projectId: string; sources: SourceFile[]; expanded: boolean; toggle: () => void; close: () => void; unshown: readonly Unshown[];
}) {
  const [id, setId] = useState(sources[0]?.id ?? "");
  const source = sources.find(item => item.id === id) ?? sources[0];
  const kind = source ? originalKind(source.originalName) : "unsupported";
  const marked = kind === "pdf" || kind === "docx" ? reasons.filter(reason => unshown.some(line => line.reason === reason)) : [];
  return <div id="original-source-panel" className="source-viewer"
    onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
    <div className="workspace-pane-heading">
      <div className="workspace-pane-title"><h2>Оригинал</h2></div>
      {source && <a className="icon" aria-label="Скачать оригинал" title="Скачать оригинал" href={`${originalUrl(projectId, source.id)}/download`} download><Icon name="download" /></a>}
      <button className="icon" aria-label={expanded ? "Сравнить рядом" : "Развернуть оригинал"} title={expanded ? "Сравнить рядом" : "Развернуть оригинал"} onClick={toggle}><Icon name={expanded ? "panel" : "expand"} /></button>
      <button className="icon" aria-label="Закрыть оригинал" title="Закрыть оригинал" onClick={close}><Icon name="close" /></button></div>
    <div className="source-viewer-file">
      {sources.length > 1 ? <select aria-label="Файл оригинала" value={source?.id ?? ""} onChange={event => setId(event.currentTarget.value)}>
        {sources.map(item => <option key={item.id} value={item.id}>{item.originalName}</option>)}
      </select> : <span title={source?.originalName}>{source?.originalName ?? "Нет файла"}</span>}
      <span className="source-file-type">{source?.originalName.split(".").pop()?.toUpperCase()}</span>
    </div>
    {marked.length > 0 && <p className="source-unshown-legend"><span><i className={`${unshownClass}-key`} />Красным — то, чего нет в резюме:</span>
      {marked.map(reason => unshownLabels[reason]).join(", ")}</p>}
    {source && <ErrorBoundary key={`${projectId}:${source.id}:${source.byteSha256}`}
      fallback={<p className="source-viewer-message" role="alert">Не удалось показать оригинал. Скачайте его.</p>}>
      <OriginalPreview projectId={projectId} source={source} unshown={unshown} /></ErrorBoundary>}
  </div>;
}
