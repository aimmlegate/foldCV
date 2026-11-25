import type { OrderDocument } from "../../rich/technology-order";
import { errorMessage } from "../../errors/messages";
import { useEffect, useRef, useState } from "react";
import type { WorkingFacts } from "../../contracts/generated/contracts";
import { panelSupport, type PanelCommand, type PanelPlan, type TechnologyTarget } from "../../rich/v7-panel";
import { labels, needsCheck, title, type Kind, type RecordValue } from "../../rich/fact-fields";
import { TechnologyGroups } from "./TechnologyGroups";
import { TechnologySelect } from "./TechnologySelect";
import { FactDialog, type FactTarget } from "./FactDialog";
import { OffPage } from "./OffPage";
import { Icon } from "../ui/Icon";
import { factError } from "./error";
import { dateText } from "./dates";
import { FocusYears, type FocusEntry } from "./FocusYears";
import { FocusIconDialog } from "./FocusIconDialog";
import type { FocusIconChoices } from "../../projects/api";
import { OperationStatus } from "../ui/OperationStatus";
import type { DateWarning } from "../../projects/api";
import { JobWarnings, overlapLine } from "./JobWarnings";

/** The records of a group as Facts lists them: jobs in the plan's order (D182), the others in record order. */
export function groupRecords(records: readonly RecordValue[], kind: Kind, order: readonly string[] | undefined): RecordValue[] {
  const listed = records.filter(record => record.kind === kind);
  if (kind !== "employment" || !order?.length) return listed;
  const place = new Map(order.map((id, index) => [id, index]));
  // A job the plan does not name yet keeps its record place after the named ones.
  return listed.map((record, index) => ({ record, at: place.get(record.id) ?? order.length + index })).sort((a, b) => a.at - b.at).map(value => value.record);
}

function summary(record: RecordValue, periods: readonly string[]): [string, string] {
  if (record.kind === "candidate") return [record.name.rawText || "Кандидат", [record.title.rawText, record.location.rawText].filter(Boolean).join("\n")];
  if (record.kind === "employment") return [record.employer.rawText || "Без названия", [record.role.rawText, ...periods].filter(Boolean).join("\n")];
  if (record.kind === "education") return [record.institution.rawText || "Без названия", [record.qualification.rawText, record.specialty.rawText, dateText(record.completion)].filter(Boolean).join("\n")];
  if (record.kind === "language") return [record.language.rawText || "Без названия", record.level.rawText];
  if (record.kind === "claim") return [record.value.rawText || "Новый факт", ""];
  return ["", ""];
}
function jobName(records: readonly RecordValue[], id: string): string {
  const record = records.find(value => value.id === id);
  return record ? title(record) : "Без названия";
}
export function FactsPanel({ facts, document, focusEntries = [], focusOptions = [], focusOnly, focusIcons = null, technologyTargets = [], plan = {}, submit,
  pending, paused, hidden, close, checkDates = null, focusRequest = null, onFocused, anchors, showBlock = () => {} }: {
  facts: WorkingFacts; document: OrderDocument; submit: (command: PanelCommand) => Promise<void>; pending: readonly PanelCommand[]; paused: boolean;
  focusEntries?: readonly FocusEntry[];
  focusOptions?: readonly FocusEntry[];
  /** Loads the template's icons for a Focus row's icon search; null when the template has none to choose from. */
  focusIcons?: (() => Promise<FocusIconChoices>) | null;
  /** Records only Focus rows show; the technology lists leave them out. */
  focusOnly?: ReadonlySet<string>;
  /** Where Python can show a new technology; a list without one offers no adding. */
  technologyTargets?: readonly TechnologyTarget[];
  plan?: PanelPlan;
  hidden: boolean; close: () => void;
  /** Python's warnings for the date dialog's values before Save (D182); null where the editor cannot ask. */
  checkDates?: ((recordId: string | null, values: Record<string, string>) => Promise<DateWarning[]>) | null;
  focusRequest?: { recordId: string } | null; onFocused?: () => void;
  /** Where each group's section is in the resume, by record kind; a group without one offers no jump. */
  anchors?: ReadonlyMap<string, string>; showBlock?: (blockId: string) => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const [target, setTarget] = useState<FactTarget | null>(null), [error, setError] = useState<string | null>(null);
  // The row whose icon is being chosen; the dialog closes when the row goes, as after an Undo.
  const [iconRow, setIconRow] = useState<string | null>(null);
  const iconEntry = focusIcons ? focusEntries.find(entry => entry.recordId === iconRow) : undefined;
  // One command at a time: the editor takes the next one only after Python's answer to this one is shown.
  const busy = paused || pending.length > 0;
  const groups: Kind[] = ["candidate", "employment", "technology", "education", "language"];
  if ((facts.mode === "digest" || facts.mode === "imported") && facts.records.some(record => record.kind === "claim")) groups.push("claim");
  useEffect(() => {
    if (!focusRequest || hidden) return;
    const frame = requestAnimationFrame(() => {
      const row = panel.current?.querySelector<HTMLElement>(`[data-fact-id="${CSS.escape(focusRequest.recordId)}"]`);
      for (let parent = row?.parentElement; parent && parent !== panel.current; parent = parent.parentElement)
        if (parent instanceof HTMLDetailsElement) parent.open = true;
      row?.scrollIntoView({ block: "center", behavior: "smooth" });
      // A focus that scrolls stops the smooth scroll in WebKit halfway and leaves the panel unpainted until the next scroll.
      row?.querySelector<HTMLElement>("button:not(:disabled), input:not(:disabled)")?.focus({ preventScroll: true });
      onFocused?.();
    });
    return () => cancelAnimationFrame(frame);
  }, [focusRequest, hidden, onFocused]);
  const editTechnology = (recordId: string) => {
    const record = facts.records.find(value => value.id === recordId);
    if (record) setTarget({ kind: "technology", record });
  };
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
    {groups.map(kind => {
      const anchor = anchors?.get(kind);
      return <div className="fact-group-frame" key={kind}><details className="fact-group" data-group={kind} open={kind !== "claim"}>
      <summary>{labels[kind]}</summary>
      {kind === "technology" ? <><FocusYears entries={focusEntries} options={focusOptions} paused={busy} submit={apply} edit={editTechnology} pickIcon={focusIcons ? setIconRow : null} />
        {/* D136: the resume's skill groups; a template without them keeps one general list. */}
        {technologyTargets.some(target => target.jobId === null)
          ? <TechnologyGroups facts={facts} document={document} targets={technologyTargets.filter(target => target.jobId === null)}
            creatable={plan.addTechnologyGroup === true} pending={pending} paused={busy} submit={apply} edit={editTechnology} excluded={focusOnly} />
          : <TechnologySelect facts={facts} document={document} jobId={null} label="общий список" pending={pending} paused={busy} submit={apply} edit={editTechnology}
            focusRecordId={focusRequest?.recordId} targets={[]} lines={plan.technologyLines} excluded={focusOnly} />}</>
        : groupRecords(facts.records, kind, plan.jobOrder).map(record => {
          const job = plan.jobs?.[record.id];
          const [name, sub] = summary(record, job?.periods ?? []);
          // D179, sketch A1: a card the page does not show, with its way back.
          const off = plan.offPage?.includes(record.id) === true;
          return <div key={record.id}><div className="fact-row" data-fact-id={record.id} data-off-page={off || undefined}>
            <button className="fact-edit" disabled={busy} onClick={() => setTarget({ kind, record })}><strong>{name}</strong>
              {sub && <small>{sub}</small>}{needsCheck(record) && <small>Проверьте значение</small>}</button>
            {/* D182: one place up or down among the cards of the job's list; Python says which way can go. */}
            {job?.move && <><button className="icon" aria-label={`Переместить выше: ${name}`} title="Выше" disabled={busy || !job.move.up}
              onClick={() => void apply({ operation: "move_job", recordId: record.id, values: { direction: "up" } }).catch(() => {})}><Icon name="up" /></button>
              <button className="icon" aria-label={`Переместить ниже: ${name}`} title="Ниже" disabled={busy || !job.move.down}
                onClick={() => void apply({ operation: "move_job", recordId: record.id, values: { direction: "down" } }).catch(() => {})}><Icon name="down" /></button></>}
            {panelSupport.remove.has(kind) && <button className="icon" aria-label={`Удалить: ${name}`} disabled={busy} onClick={() => setTarget({ kind, record, remove: true })}><Icon name="close" /></button>}
          </div>{job && <JobWarnings lines={[...(job.outOfOrder ? ["Стоит не по дате"] : []),
            ...(job.overlaps?.length ? [overlapLine(job.overlaps.map(id => jobName(facts.records, id)))] : [])]} />}
          {off && <OffPage name={name} busy={busy} restore={() => void apply({ operation: "restore", recordId: record.id }).catch(() => {})} />}
          {record.kind === "employment" && <TechnologySelect facts={facts} document={document} jobId={record.id} label={name} pending={pending} paused={busy} submit={apply} edit={editTechnology} focusRecordId={focusRequest?.recordId}
            targets={technologyTargets.filter(target => target.jobId === record.id)} lines={plan.technologyLines} excluded={focusOnly} />}</div>;
        })}
      {(plan.addKinds?.some(value => value === kind) || kind === "employment" && plan.sortJobs) && <div className="fact-add-row">
        {plan.addKinds?.some(value => value === kind) && <button className="text-button fact-add" disabled={busy}
          onClick={() => setTarget({ kind, record: null })}>+ {kind === "employment" ? "Место работы" : kind === "language" ? "Язык" : kind === "claim" ? "Факт" : labels[kind]}</button>}
        {kind === "employment" && plan.sortJobs && <button className="text-button fact-add" disabled={busy}
          onClick={() => void apply({ operation: "sort_jobs", recordKind: "employment" }).catch(() => {})}>Расставить по дате</button>}
      </div>}
    </details>
      {/* Beside the summary, not inside it: a click inside a summary also folds the group. */}
      {anchor && <button type="button" className="icon fact-group-jump" aria-label={`Показать в резюме: ${labels[kind]}`} title="Показать в резюме"
        onClick={() => showBlock(anchor)}><Icon name="locate" /></button>}</div>;
    })}
  </aside>{target && <FactDialog target={target} close={() => setTarget(null)} submit={apply}
      checkDates={target.kind === "employment" ? checkDates : null} jobName={id => jobName(facts.records, id)}
      offPage={target.record ? plan.offPageFields?.[target.record.id] : undefined}
      unshown={target.record ? plan.unshownFields?.[target.record.id] : undefined} addPeriod={Boolean(target.record && plan.jobs?.[target.record.id]?.addPeriod)} />}
    {iconEntry && focusIcons && <FocusIconDialog entry={iconEntry} load={focusIcons} submit={apply} close={() => setIconRow(null)} />}</>;
}
