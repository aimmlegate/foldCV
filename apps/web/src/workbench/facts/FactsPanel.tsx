import type { OrderDocument } from "../../rich/technology-order";
import { errorMessage } from "../../errors/messages";
import { useEffect, useRef, useState } from "react";
import type { WorkingFacts } from "../../contracts/generated/working_facts";
import { panelSupport, type PanelCommand, type TechnologyTarget } from "../../rich/v7-panel";
import { labels, needsCheck, type Kind, type RecordValue } from "../../rich/fact-fields";
import { TechnologySelect } from "./TechnologySelect";
import { FactDialog, type FactTarget } from "./FactDialog";
import { Icon } from "../ui/Icon";
import { factError } from "./error";
import { dateText } from "./dates";
import { FocusYears, type FocusEntry } from "./FocusYears";
import { OperationStatus } from "../ui/OperationStatus";
import type { PlacedRemarks } from "../../rich/remarks";
import { CheckFooter, RemarkSections, type CheckState } from "./RemarkSections";

function summary(record: RecordValue): [string, string] {
  if (record.kind === "candidate") return [record.name.rawText || "Кандидат", [record.title.rawText, record.location.rawText].filter(Boolean).join("\n")];
  if (record.kind === "employment") return [record.employer.rawText || "Без названия", [record.role.rawText,
    ...record.periods.map(period => `${dateText(period.start) || "?"} — ${period.present.value ? "по настоящее время" : dateText(period.end) || "?"}`)].filter(Boolean).join("\n")];
  if (record.kind === "education") return [record.institution.rawText || "Без названия", [record.qualification.rawText, record.specialty.rawText, dateText(record.completion)].filter(Boolean).join("\n")];
  if (record.kind === "language") return [record.language.rawText || "Без названия", record.level.rawText];
  if (record.kind === "claim") return [record.value.rawText || "Новый факт", ""];
  return ["", ""];
}
export function FactsPanel({ facts, document, focusEntries = [], focusOptions = [], technologyTargets = [], submit, pending, paused, hidden, close,
  focusRequest = null, onFocused, remarks, showBlock = () => {}, check }: {
  facts: WorkingFacts; document: OrderDocument; submit: (command: PanelCommand) => Promise<void>; pending: readonly PanelCommand[]; paused: boolean;
  focusEntries?: readonly FocusEntry[];
  focusOptions?: readonly FocusEntry[];
  /** Where Python can show a new technology; a list without one offers no adding. */
  technologyTargets?: readonly TechnologyTarget[];
  hidden: boolean; close: () => void;
  focusRequest?: { recordId: string } | null; onFocused?: () => void;
  /** Remarks by resume section, with the place each one names in the document. */
  remarks?: PlacedRemarks; showBlock?: (blockId: string) => void;
  check?: { state: CheckState; run: () => void };
}) {
  const panel = useRef<HTMLElement>(null);
  const [target, setTarget] = useState<FactTarget | null>(null), [error, setError] = useState<string | null>(null);
  const groups: Kind[] = ["candidate", "employment", "technology", "education", "language"];
  if ((facts.mode === "digest" || facts.mode === "imported") && facts.records.some(record => record.kind === "claim")) groups.push("claim");
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
    catch (error) { setError(factError(error)); throw error; }
  }
  return <><aside ref={panel} className="facts-panel" aria-label="Факты" id="rich-facts-panel" hidden={hidden}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); } }}>
    <div className="panel-heading"><h2>Факты</h2><button className="icon" aria-label="Скрыть факты" onClick={close}><Icon name="close" /></button></div>
    <div className="facts-feedback">
      {error && <p className="notice warning" role="alert">{errorMessage(error)}</p>}
      {pending.length > 0 && <OperationStatus state={paused ? "error" : "working"} label={paused ? "Не сохранено" : `Сохраняем: ${pending.length}`} timed={!paused} />}
    </div>
    {facts.extraction && <div className="notice" role="status">
      <p>Фактов: {facts.extraction.factCount}{facts.extraction.status === "complete" ? "" : ", извлечены не все"}.</p>
      {facts.extraction.unresolved.length > 0 && <details><summary>Проверьте: {facts.extraction.unresolved.length}</summary>
        <ul>{facts.extraction.unresolved.map((issue, index) => <li key={`${issue.sourceId}:${issue.unitId ?? "result"}:${index}`}>
          {issue.code === "FACT_SECTION_OMITTED" ? `Не извлечён раздел: ${issue.section}` : issue.code === "FACT_ROWS_RECOVERED" ? "Часть ответа модели отклонена" : issue.section || "Не попало в факты"}
          {issue.page ? `, стр. ${issue.page}` : ""}</li>)}</ul>
        <p>Сверьте с исходником и исправьте вручную.</p></details>}
    </div>}
    {groups.map(kind => <details className="fact-group" key={kind} data-group={kind} open={kind !== "claim"}>
      <summary>{labels[kind]}</summary>
      {kind === "technology" ? <><FocusYears entries={focusEntries} options={focusOptions} paused={paused || pending.length > 0} submit={apply} />
        <TechnologySelect facts={facts} document={document} jobId={null} label="общий список" pending={pending} paused={paused} submit={apply} focusRecordId={focusRequest?.recordId}
          targets={technologyTargets.filter(target => target.jobId === null)} /></>
        : facts.records.filter(record => record.kind === kind).map(record => {
          const [name, sub] = summary(record);
          return <div key={record.id}><div className="fact-row" data-fact-id={record.id}>
            <button className="fact-edit" disabled={paused} onClick={() => setTarget({ kind, record })}><strong>{name}</strong>
              {sub && <small>{sub}</small>}{needsCheck(record) && <small>Проверьте значение</small>}</button>
            {panelSupport.remove.has(kind) && <button className="icon" aria-label={`Удалить: ${name}`} disabled={paused} onClick={() => setTarget({ kind, record, remove: true })}><Icon name="close" /></button>}
          </div>{record.kind === "employment" && <TechnologySelect facts={facts} document={document} jobId={record.id} label={name} pending={pending} paused={paused} submit={apply} focusRecordId={focusRequest?.recordId}
            targets={technologyTargets.filter(target => target.jobId === record.id)} />}</div>;
        })}
      {panelSupport.add.has(kind) && <button className="text-button fact-add" disabled={paused}
        onClick={() => setTarget({ kind, record: null })}>+ {kind === "employment" ? "Место работы" : kind === "language" ? "Язык" : kind === "claim" ? "Факт" : labels[kind]}</button>}
    </details>)}
    {remarks && <RemarkSections remarks={remarks} show={showBlock} />}
    {check && <CheckFooter state={check.state} run={check.run} disabled={paused} />}
  </aside>{target && <FactDialog target={target} close={() => setTarget(null)} submit={apply} />}</>;
}
