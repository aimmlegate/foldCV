import { useEffect, useRef, useState, type ReactNode } from "react";
import type { WorkingFacts } from "../../contracts/generated/working_facts";
import type { RichDocumentV1 } from "../../contracts/generated/rich_document_v1";
import type { PanelCommand } from "../../rich/synchronization";
import { labels, needsCheck, type Kind, type RecordValue } from "../../rich/fact-fields";
import { TechnologySelect } from "./TechnologySelect";
import { FactDialog, type FactTarget } from "./FactDialog";
import { Icon } from "../ui/Icon";
import { factError } from "./error";
import { AppliedIntentFailure } from "../../rich/intent-queue";
import { dateText } from "./dates";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import { FocusYears } from "./FocusYears";
import { OperationStatus } from "../ui/OperationStatus";

function summary(record: RecordValue): [string, string] {
  if (record.kind === "candidate") return [record.name.rawText || "Кандидат", [record.title.rawText, record.location.rawText].filter(Boolean).join("\n")];
  if (record.kind === "employment") return [record.employer.rawText || "Без названия", [record.role.rawText,
    ...record.periods.map(period => `${dateText(period.start) || "?"} — ${period.present.value ? "по настоящее время" : dateText(period.end) || "?"}`)].filter(Boolean).join("\n")];
  if (record.kind === "education") return [record.institution.rawText || "Без названия", [record.qualification.rawText, record.specialty.rawText, dateText(record.completion)].filter(Boolean).join("\n")];
  if (record.kind === "language") return [record.language.rawText || "Без названия", record.level.rawText];
  if (record.kind === "claim") return [record.value.rawText || "Новый факт", ""];
  return ["", ""];
}
export function FactsPanel({ facts, document, focusEntries = [], focusOptions = [], submit, pending, paused, timeline, hidden, close,
  focusRequest = null, onFocused }: {
  facts: WorkingFacts; document: RichDocumentV1; submit: (command: PanelCommand) => Promise<void>; pending: readonly PanelCommand[]; paused: boolean;
  focusEntries?: NonNullable<RichProjectResponse["presentation"]>["focusEntries"];
  focusOptions?: NonNullable<RichProjectResponse["presentation"]>["focusOptions"];
  timeline: ReactNode; hidden: boolean; close: () => void;
  focusRequest?: { recordId: string } | null; onFocused?: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const [target, setTarget] = useState<FactTarget | null>(null), [error, setError] = useState<{ message: string; save: boolean } | null>(null);
  const groups: Kind[] = ["candidate", "employment", "technology", "education", "language"];
  if ((facts.mode === "digest" || facts.mode === "imported") && facts.records.some(record => record.kind === "claim")) groups.push("claim");
  useEffect(() => { if (error?.save && !paused && !pending.length) setError(null); }, [error, paused, pending.length]);
  useEffect(() => {
    if (!focusRequest || hidden) return;
    const frame = requestAnimationFrame(() => {
      const row = panel.current?.querySelector<HTMLElement>(`[data-fact-id="${CSS.escape(focusRequest.recordId)}"]`);
      for (let parent = row?.parentElement; parent && parent !== panel.current; parent = parent.parentElement)
        if (parent instanceof HTMLDetailsElement) parent.open = true;
      row?.scrollIntoView({ block: "center", behavior: "smooth" });
      row?.querySelector<HTMLElement>("button:not(:disabled), input:not(:disabled)")?.focus();
      onFocused?.();
    });
    return () => cancelAnimationFrame(frame);
  }, [focusRequest, hidden, onFocused]);
  async function apply(command: PanelCommand) {
    setError(null);
    try { await submit(command); }
    catch (error) { setError({ message: factError(error), save: error instanceof AppliedIntentFailure }); throw error; }
  }
  return <><aside ref={panel} className="facts-panel" aria-label="Факты резюме" id="rich-facts-panel" hidden={hidden}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); } }}>
    <div className="panel-heading"><h2>Факты</h2><button className="icon" aria-label="Скрыть факты" onClick={close}><Icon name="close" /></button></div>
    <div className="facts-feedback">
      {error && <p className="notice warning" role="alert">{error.message}</p>}
      {pending.length > 0 && <OperationStatus state={paused ? "error" : "working"} label={paused ? "Ожидает повторного сохранения" : `Сохраняем изменения: ${pending.length}`} timed={!paused} />}
    </div>
    {facts.extraction && <div className="notice" role="status">
      <p>{facts.extraction.status === "complete" ? "Факты извлечены" : "Факты извлечены частично"}: {facts.extraction.factCount}.</p>
      {facts.extraction.unresolved.length > 0 && <details><summary>Требует проверки: {facts.extraction.unresolved.length}</summary>
        <ul>{facts.extraction.unresolved.map((issue, index) => <li key={`${issue.sourceId}:${issue.unitId ?? "result"}:${index}`}>
          {issue.code === "FACT_SECTION_OMITTED" ? `Не извлечён раздел: ${issue.section}` : issue.code === "FACT_ROWS_RECOVERED" ? "Часть строк ответа модели отклонена; подтверждённые факты сохранены" : issue.section || "Сведения исходника не представлены в фактах"}
          {issue.page ? `, стр. ${issue.page}` : ""}</li>)}</ul>
        <p>Сверьте исходник и внесите исправления вручную или повторите обработку.</p></details>}
    </div>}
    {groups.map(kind => <details className="fact-group" key={kind} data-group={kind} open={kind !== "claim"}>
      <summary>{labels[kind]}</summary>
      {kind === "technology" ? <><FocusYears entries={focusEntries} options={focusOptions} paused={paused || pending.length > 0} submit={apply} />
        <TechnologySelect facts={facts} document={document} jobId={null} label="общий список" pending={pending} paused={paused} submit={apply} focusRecordId={focusRequest?.recordId} /></>
        : facts.records.filter(record => record.kind === kind).map(record => {
          const [name, sub] = summary(record);
          return <div key={record.id}><div className="fact-row" data-fact-id={record.id}>
            <button className="fact-edit" disabled={paused} onClick={() => setTarget({ kind, record })}><strong>{name}</strong>
              {sub && <small>{sub}</small>}{needsCheck(record) && <small>Проверьте значение</small>}</button>
            <button className="icon" aria-label={`Удалить: ${name}`} disabled={paused} onClick={() => setTarget({ kind, record, remove: true })}><Icon name="close" /></button>
          </div>{record.kind === "employment" && <TechnologySelect facts={facts} document={document} jobId={record.id} label={name} pending={pending} paused={paused} submit={apply} focusRecordId={focusRequest?.recordId} />}</div>;
        })}
      {kind === "employment" && timeline}
      {kind !== "technology" && (kind !== "candidate" || !facts.records.some(record => record.kind === "candidate")) && <button className="text-button fact-add" disabled={paused}
        onClick={() => setTarget({ kind, record: null })}>+ {kind === "employment" ? "Место работы" : kind === "language" ? "Язык" : kind === "claim" ? "Факт" : labels[kind]}</button>}
    </details>)}
  </aside>{target && <FactDialog target={target} close={() => setTarget(null)} submit={apply} />}</>;
}
