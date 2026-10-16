import { useEffect, useState } from "react";
import type { TimelineReport } from "../contracts/generated/timeline_report";
import type { DateCascadeProposal } from "../contracts/generated/date_cascade_proposal";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { DateAnchor } from "./date-edit";
import { DatePreview } from "../workbench/facts/DatePreview";
import { RichApiFailure } from "./api";

export type TimelineControls = {
  read: () => Promise<TimelineReport>;
  preview: (anchor: DateAnchor) => Promise<DateCascadeProposal>;
  apply: (proposal: DateCascadeProposal) => Promise<void>;
};
const reasons: Record<string, string> = {
  EXACT_CLOSED_PERIOD_REQUIRED: "Для сдвига нужны закрытые периоды с точностью до месяца или дня.",
  EARLIER_OR_UNCERTAIN_OVERLAP: "Есть более раннее или неясное пересечение. Проверьте даты вручную.",
  CHAIN_PRECISION_OR_OPEN_BOUNDARY: "В цепочке есть открытые или неоднозначные даты либо разная точность. Сдвиг не рассчитан.",
  FUTURE_BOUNDARY: "Сдвиг выходит за дату расчёта. Будущие даты можно оставить или изменить вручную.",
  DATE_RANGE_EXCEEDED: "Сдвиг выходит за допустимый диапазон дат.",
  NO_FORWARD_OVERLAP: "Последующие периоды не требуют сдвига.",
};
export function Timeline({ facts, anchors, controls, prototype = false }: { facts: WorkingFacts; anchors: DateAnchor[]; controls: TimelineControls; prototype?: boolean }) {
  const [report, setReport] = useState<TimelineReport | null>(null), [proposal, setProposal] = useState<DateCascadeProposal | null>(null);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const factsKey = JSON.stringify(facts);
  useEffect(() => {
    let active = true;
    void controls.read().then(value => { if (active) { setReport(value); setError(""); } }).catch(error => {
      if (active) setError(error instanceof RichApiFailure || error instanceof TypeError ? "Не удалось проверить даты. Повторите после сохранения." : error instanceof Error ? error.message : "Не удалось проверить даты");
    });
    return () => { active = false; };
  }, [controls, factsKey]);
  const job = (id: string) => { const record = facts.records.find(record => record.id === id); return record?.kind === "employment" ? record.employer.rawText || "Без названия" : id; };
  const period = (id: string) => {
    for (const record of facts.records) if (record.kind === "employment") {
      const period = record.periods.find(period => period.id === id);
      if (period) return `${job(record.id)}: ${period.start.rawText || "?"} — ${period.present.value ? "по настоящее время" : period.end.rawText || "?"}`;
    }
    return id;
  };
  async function preview(anchor: DateAnchor) {
    setBusy(true); setError("");
    try { setProposal(await controls.preview(anchor)); }
    catch (error) { setError(error instanceof Error ? error.message : "Не удалось рассчитать сдвиг"); }
    finally { setBusy(false); }
  }
  const overlaps = report?.warnings.filter(warning => warning.kind === "overlap") ?? [];
  const estimate = report?.estimates.find(estimate => estimate.scopeId === "employment");
  return <div className={prototype ? "uir-timeline" : "rich-timeline"} aria-label="Проверка периодов">
    {estimate?.monthsMin !== null && estimate?.monthsMin !== undefined ? <small>Месяцев опыта без двойного счёта: {estimate.monthsMin}{estimate.monthsMax !== estimate.monthsMin ? `–${estimate.monthsMax ?? "?"}` : ""}</small>
      : <small>Оценка опыта недоступна. Проверьте даты и дату наблюдения источника.</small>}
    {overlaps.length > 0 && <details open><summary>Пересечения: {overlaps.length}</summary><small>Параллельная работа допустима. Сохранение и экспорт доступны.</small>
      <ul>{overlaps.map(warning => <li key={warning.id}>{warning.certainty === "certain" ? "Пересечение" : "Возможное пересечение"}: {warning.periodIds.map(period).join(" / ")}</li>)}</ul>
      {anchors.filter(anchor => overlaps.some(warning => warning.periodIds.includes(anchor.periodId))).map(anchor => <button key={anchor.periodId} disabled={busy}
        onClick={() => void preview(anchor)}>Предпросмотр сдвига: {period(anchor.periodId)}</button>)}
      <button disabled={busy} onClick={() => { setProposal(null); setError(""); }}>Оставить параллельные периоды</button>
    </details>}
    {report?.warnings.filter(warning => warning.kind !== "overlap").map(warning => <small key={warning.id}>
      {warning.kind === "future" ? "Дата может быть в будущем" : warning.code === "OPEN_PERIOD" ? "Открытый период" : "Проверьте дату"}: {warning.periodIds.map(period).join(" / ")}</small>)}
    {error && <p role="status">{error}</p>}
    {proposal && prototype ? <DatePreview proposal={proposal} job={job} reason={reasons[proposal.reason ?? ""] ?? "Сдвиг недоступен. Проверьте периоды вручную."}
      busy={busy} error={error} close={() => setProposal(null)} apply={() => { setBusy(true); setError(""); void controls.apply(proposal).then(() => setProposal(null))
        .catch(error => setError(error instanceof Error ? error.message : "Предпросмотр устарел")).finally(() => setBusy(false)); }} /> : proposal && <div className="rich-cascade" role="region" aria-label="Предпросмотр сдвига">
      {proposal.status === "available" ? <><p>Предлагаемые изменения</p><ul>{proposal.shifts.map(shift => <li key={shift.periodId}>
        {job(shift.jobId)}: {shift.before.start.rawText} — {shift.before.end.rawText} → {shift.after.start.rawText} — {shift.after.end.rawText}
        <small>{shift.inclusiveSpan} {shift.unit === "month" ? "мес." : "дн."}, длительность сохранена</small></li>)}</ul>
        <small>После сдвига предупреждений: {proposal.warnings.length}</small>
        <button disabled={busy} onClick={() => { setBusy(true); setError(""); void controls.apply(proposal).then(() => setProposal(null))
          .catch(error => setError(error instanceof Error ? error.message : "Предпросмотр устарел")).finally(() => setBusy(false)); }}>Применить сдвиг</button></>
        : <p>{reasons[proposal.reason ?? ""] ?? "Сдвиг недоступен. Проверьте периоды вручную."}</p>}
      <button disabled={busy} onClick={() => setProposal(null)}>Закрыть предпросмотр</button>
    </div>}
  </div>;
}
