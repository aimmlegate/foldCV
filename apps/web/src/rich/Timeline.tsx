import { useEffect, useRef, useState } from "react";
import type { TimelineReport } from "../contracts/generated/timeline_report";
import type { DateCascadeProposal } from "../contracts/generated/date_cascade_proposal";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { DateAnchor } from "./date-edit";
import { DatePreview } from "../workbench/facts/DatePreview";

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
export function Timeline({ facts, anchors, controls }: { facts: WorkingFacts; anchors: DateAnchor[]; controls: TimelineControls }) {
  const [report, setReport] = useState<TimelineReport | null>(null), [proposal, setProposal] = useState<DateCascadeProposal | null>(null);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const previewTrigger = useRef<HTMLButtonElement | null>(null);
  const factsKey = JSON.stringify(facts);
  useEffect(() => {
    let active = true;
    void controls.read().then(value => { if (active) { setReport(value); setError(""); } }).catch(error => {
      if (active) setError(error instanceof Error && /OUTCOME_UNKNOWN|WRITER_|DRAFT_/u.test(error.message)
        ? "Проверим даты после восстановления черновика."
        : "Не удалось проверить даты. Повторите после сохранения.");
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
  const estimateReasons: Readonly<Record<string, string>> = {
    DATE_INCOMPLETE: "В периодах не хватает дат или есть неразобранные значения.",
    SOURCE_OBSERVATION_REQUIRED: "Для текущей работы нужна указанная в исходнике дата наблюдения.",
    FUTURE_OR_INVALID_PERIOD: "Есть будущие даты или начало позже конца периода.",
    NO_DATED_EMPLOYMENT: "Нет мест работы с пригодными для расчёта датами.",
  };
  return <div className={"uir-timeline"} aria-label="Проверка периодов">
    {estimate?.monthsMin !== null && estimate?.monthsMin !== undefined ? <small>Месяцев опыта без двойного счёта: {estimate.monthsMin}{estimate.monthsMax !== estimate.monthsMin ? `–${estimate.monthsMax ?? "?"}` : ""}</small>
      : <small>Оценка опыта недоступна. {estimateReasons[estimate?.reason ?? ""] ?? "Проверьте даты и дату наблюдения источника."}</small>}
    {overlaps.length > 0 && <details open><summary>Пересечения: {overlaps.length}</summary><small>Параллельная работа допустима. Сохранение и экспорт доступны.</small>
      <ul>{overlaps.map(warning => <li key={warning.id}>{warning.certainty === "certain" ? "Пересечение" : "Возможное пересечение"}: {warning.periodIds.map(period).join(" / ")}</li>)}</ul>
      {anchors.filter(anchor => overlaps.some(warning => warning.periodIds.includes(anchor.periodId))).map(anchor => <button key={anchor.periodId} disabled={busy}
        onClick={event => { previewTrigger.current = event.currentTarget; void preview(anchor); }}>Предпросмотр сдвига: {period(anchor.periodId)}</button>)}
      <button disabled={busy} onClick={() => { setProposal(null); setError(""); }}>Оставить параллельные периоды</button>
    </details>}
    {report?.warnings.filter(warning => warning.kind !== "overlap").map(warning => <small key={warning.id}>
      {warning.kind === "future" ? "Дата может быть в будущем" : warning.code === "OPEN_PERIOD" ? "Открытый период" : "Проверьте дату"}: {warning.periodIds.map(period).join(" / ")}</small>)}
    {error && <p role="status">{error}</p>}
    {proposal && <DatePreview proposal={proposal} job={job} reason={reasons[proposal.reason ?? ""] ?? "Сдвиг недоступен. Проверьте периоды вручную."}
      busy={busy} error={error} returnFocus={previewTrigger.current} close={() => setProposal(null)} apply={() => { setBusy(true); setError(""); void controls.apply(proposal).then(() => setProposal(null))
        .catch(error => setError(error instanceof Error ? error.message : "Предпросмотр устарел")).finally(() => setBusy(false)); }} />}
  </div>;
}
