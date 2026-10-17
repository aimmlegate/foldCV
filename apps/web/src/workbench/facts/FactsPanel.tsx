import { useEffect, useState, type ReactNode } from "react";
import type { WorkingFacts } from "../../contracts/generated/working_facts";
import type { RichDocumentV1 } from "../../contracts/generated/rich_document_v1";
import type { PanelCommand } from "../../rich/synchronization";
import { labels, needsCheck, type RecordValue } from "../../rich/fact-fields";
import { TechnologySelect } from "./TechnologySelect";
import { FactDialog, type FactTarget } from "./FactDialog";
import { Icon } from "../ui/Icon";
import { factError } from "./error";
import { AppliedIntentFailure } from "../../rich/intent-queue";
import { dateText } from "./dates";

function summary(record: RecordValue): [string, string] {
  if (record.kind === "candidate") return [record.name.rawText || "Кандидат", [record.title.rawText, record.location.rawText].filter(Boolean).join("\n")];
  if (record.kind === "employment") return [record.employer.rawText || "Без названия", [record.role.rawText,
    ...record.periods.map(period => `${dateText(period.start) || "?"} — ${period.present.value ? "по настоящее время" : dateText(period.end) || "?"}`)].filter(Boolean).join("\n")];
  if (record.kind === "education") return [record.institution.rawText || "Без названия", [record.qualification.rawText, record.specialty.rawText, dateText(record.completion)].filter(Boolean).join("\n")];
  if (record.kind === "language") return [record.language.rawText || "Без названия", record.level.rawText];
  return ["", ""];
}
export function FactsPanel({ facts, document, submit, pending, paused, timeline, hidden, close }: {
  facts: WorkingFacts; document: RichDocumentV1; submit: (command: PanelCommand) => Promise<void>; pending: readonly PanelCommand[]; paused: boolean;
  timeline: ReactNode; hidden: boolean; close: () => void;
}) {
  const [target, setTarget] = useState<FactTarget | null>(null), [error, setError] = useState<{ message: string; save: boolean } | null>(null);
  useEffect(() => { if (error?.save && !paused && !pending.length) setError(null); }, [error, paused, pending.length]);
  async function apply(command: PanelCommand) {
    setError(null);
    try { await submit(command); }
    catch (error) { setError({ message: factError(error), save: error instanceof AppliedIntentFailure }); throw error; }
  }
  return <><aside className="facts-panel" aria-label="Факты резюме" id="rich-facts-panel" hidden={hidden}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); } }}>
    <div className="panel-heading"><h2>Факты</h2><button className="icon" aria-label="Скрыть факты" onClick={close}><Icon name="close" /></button></div>
    {error && <p className="notice warning" role="alert">{error.message}</p>}
    {pending.length > 0 && <small className="uir-facts-pending" role="status">{paused ? "Ожидает повторного сохранения" : `Сохраняем изменения: ${pending.length}`}</small>}
    {(["candidate", "employment", "technology", "education", "language"] as const).map(kind => <details className="fact-group" key={kind} data-group={kind} open>
      <summary>{labels[kind]}</summary>
      {kind === "technology" ? <TechnologySelect facts={facts} document={document} jobId={null} label="общий список" pending={pending} paused={paused} submit={apply} />
        : facts.records.filter(record => record.kind === kind).map(record => {
          const [name, sub] = summary(record);
          return <div key={record.id}><div className="fact-row" data-fact-id={record.id}>
            <button className="fact-edit" disabled={paused} onClick={() => setTarget({ kind, record })}><strong>{name}</strong>
              {sub && <small>{sub}</small>}{needsCheck(record) && <small>Проверьте значение</small>}</button>
            <button className="icon" aria-label={`Удалить: ${name}`} disabled={paused} onClick={() => setTarget({ kind, record, remove: true })}><Icon name="close" /></button>
          </div>{record.kind === "employment" && <TechnologySelect facts={facts} document={document} jobId={record.id} label={name} pending={pending} paused={paused} submit={apply} />}</div>;
        })}
      {kind === "employment" && timeline}
      {kind !== "technology" && (kind !== "candidate" || !facts.records.some(record => record.kind === "candidate")) && <button className="text-button fact-add" disabled={paused}
        onClick={() => setTarget({ kind, record: null })}>+ {kind === "employment" ? "Место работы" : kind === "language" ? "Язык" : labels[kind]}</button>}
    </details>)}
  </aside>{target && <FactDialog target={target} close={() => setTarget(null)} submit={apply} />}</>;
}
