import { useState } from "react";
import type { AgentWebSource } from "../contracts/generated/agent_web_source";
import type { AgentFinding } from "../contracts/generated/agent_finding";
import { sourceUrl } from "./presentation";
export function Resources({ sources, findings, focus }: { sources: AgentWebSource[]; findings: AgentFinding[];
  focus: (anchor: AgentFinding["anchors"][number]) => boolean }) {
  const [stale, setStale] = useState<Set<string>>(() => new Set());
  return <div className="assistant-resources">{sources.length > 0 && <section aria-label="Источники"><h3>Источники</h3>{sources.map(source => {
    const url = sourceUrl(source.finalUrl);
    return <details key={source.id}><summary>{source.title || "Полученная страница"} · {url ? new URL(url).hostname : "Сохранённый источник"}</summary>
      {url && <a href={url} target="_blank" rel="noopener noreferrer">Открыть источник</a>}
      <small>Получен {new Date(source.retrievedAt).toLocaleString("ru")}{source.truncated ? " · текст сокращён" : ""}</small><p>{source.text}</p></details>;
  })}</section>}{findings.length > 0 && <section aria-label="Замечания"><h3>Замечания</h3>{findings.map(finding => <article key={finding.id}>
    <p>{finding.message}</p>{finding.anchors.map((anchor, index) => { const key = `${finding.id}:${index}`;
      return <div key={key}><button onClick={() => { if (!focus(anchor)) setStale(current => new Set([...current, key])); }}>К фрагменту</button>
        {stale.has(key) && <small className="text-danger">Фрагмент изменён. Прежнее место в резюме:</small>}<blockquote>{anchor.text}</blockquote>
        {anchor.end !== null && anchor.start !== null && anchor.end - anchor.start > anchor.text.length && <small>Сохранённый фрагмент сокращён.</small>}</div>;
    })}</article>)}</section>}</div>;
}
