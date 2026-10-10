import { useState } from "react";
import type { Facts } from "../contracts/generated/fact_sheet";
import type { ImportedSource } from "../import/workflow";
import type { FactView, FactWorkflow } from "./workflow";

const control = "rounded border border-outline bg-panel px-3 py-2 text-content hover:bg-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50";
const primary = "rounded border border-accent bg-accent px-3 py-2 text-accent-contrast focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50";
const field = "w-full rounded border border-outline bg-surface p-3 text-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

function label(fact: Facts[number]): string {
  if (fact.kind === "text") return fact.value.text;
  if (fact.kind === "technology") return `${fact.value.display} · ${fact.value.scope === "global" ? "общий навык" : "опыт в работе"}`;
  if (fact.kind === "date") return [fact.value.year, fact.value.month, fact.value.day].filter((part) => part !== null && part !== undefined).join("-");
  if (fact.kind === "metric") return `${fact.value.comparator} ${fact.value.number}${fact.value.upperNumber === null ? "" : `–${fact.value.upperNumber}`} ${fact.value.unit} · ${fact.value.attribution}`;
  return `${fact.value.action} · ${fact.value.attribution}`;
}

export function FactPanel({ view, workflow, sources }: { view: FactView; workflow: FactWorkflow; sources: ImportedSource[] }) {
  const [assertion, setAssertion] = useState("");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const sheet = view.sheet;
  const sourceUnit = (sourceId: string, unitId: string) => {
    const source = sources.find((entry) => entry.result.sourceId === sourceId);
    const unit = source?.result.units.find((entry) => entry.id === unitId);
    const gapText = /^gap:(0|[1-9]\d*)$/.test(unitId) ? source?.overlays[unitId] : undefined;
    return { name: source?.result.originalName ?? sourceId, original: unit?.text ?? "",
      overlay: gapText ?? source?.overlays[`unit:${unitId}`] };
  };
  const accounts = sheet?.units.slice(page * 50, (page + 1) * 50) ?? [];
  return <section aria-label="Лист фактов" className="mt-6 rounded border border-outline bg-panel p-5">
    <h2 className="text-lg font-semibold">Лист фактов</h2>
    <p className="mt-1 text-sm text-muted">Здесь видны буквальные факты, кандидаты и вопросы к исходнику. Неясные связи с работой требуют проверки.</p>
    {view.pending && <p role="status" className="mt-3 text-sm">Проверяем извлечённый текст… <button type="button" className={control} onClick={() => workflow.cancel()}>Отменить</button></p>}
    {view.stale && <p role="alert" className="mt-3 text-sm text-danger">Исходник или исправление изменились. Прежний лист фактов ожидает обновления.</p>}
    {view.error && <p role="alert" className="mt-3 text-sm text-danger">{view.error}</p>}
    <button type="button" className={`${primary} mt-2`} disabled={view.pending} onClick={() => void workflow.update(sources)}>{sheet ? "Обновить факты" : "Проверить факты"}</button>
    <div className="mt-4 rounded border border-outline p-3">
      <label htmlFor="user-assertion" className="mb-1 block font-semibold">Добавить подтверждённый вами факт</label>
      <textarea id="user-assertion" className={`${field} min-h-20`} maxLength={4096} value={assertion}
        onChange={(event) => setAssertion(event.target.value)} />
      <button type="button" className={`${primary} mt-2`} onClick={() => { workflow.addAssertion(assertion); if (assertion.trim()) setAssertion(""); }}>Добавить факт</button>
      <p className="mt-1 text-xs text-muted">Ваш факт отмечается как внесённый пользователем; исходный текст не меняется.</p>
    </div>
    {sheet && <>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div><h3 className="font-semibold">Факты · {sheet.facts.length}</h3>
          {sheet.facts.length === 0 && <p className="text-sm text-muted">Пока нет подтверждённых фактов. Проверьте вопросы ниже.</p>}
          <div className="mt-2 max-h-96 space-y-2 overflow-auto">{sheet.facts.map((fact) => <article key={fact.id} className="rounded border border-outline p-3 text-sm">
            <strong className="block break-words">{label(fact)}</strong>
            <span className="text-xs text-muted">{sheet.proposedFactIds?.includes(fact.id) ? "Предложено · проверьте по исходнику или исправлению" : fact.origin === "user" ? "Внесено пользователем" : "Из исходника"}</span>
            {[...fact.evidence, ...(sheet.overlayFactRefs?.[fact.id] ?? [])].map((evidence) => { const source = sourceUnit(evidence.sourceId, evidence.unitId); return <p key={`${evidence.sourceId}:${evidence.unitId}`} className="mt-2 break-words text-xs text-muted">{source.name} · {evidence.unitId}: {source.original}{source.overlay !== undefined && source.overlay !== source.original ? ` · исправление: ${source.overlay}` : ""}</p>; })}
            {fact.origin === "source" && <div className="mt-2"><label htmlFor={`correct-${fact.id}`} className="block">Исправить факт, сохранив исходник</label><input id={`correct-${fact.id}`} className={field} value={edits[fact.id] ?? ""} onChange={(event) => setEdits({ ...edits, [fact.id]: event.target.value })} /><button type="button" className={`${control} mt-1`} onClick={() => workflow.correctFact(fact.id, edits[fact.id] ?? "")}>Применить исправление</button>{sheet.userCorrections?.[fact.id] && <p className="mt-1 text-xs text-muted">Исправление связано с вашим фактом {sheet.userCorrections[fact.id]}</p>}</div>}
            {fact.origin === "user" && fact.kind === "text" && !sheet.proposedFactIds?.includes(fact.id) && <div className="mt-2"><label htmlFor={`edit-${fact.id}`} className="block">Изменить свой факт</label><input id={`edit-${fact.id}`} className={field} value={edits[fact.id] ?? fact.value.text} onChange={(event) => setEdits({ ...edits, [fact.id]: event.target.value })} /><button type="button" className={`${control} mt-1`} onClick={() => workflow.editAssertion(fact.id, edits[fact.id] ?? fact.value.text)}>Применить</button></div>}
          </article>)}</div>
        </div>
        <div><h3 className="font-semibold">Вопросы · {sheet.issues.length}</h3>
          <div className="mt-2 max-h-96 space-y-2 overflow-auto">{sheet.issues.map((issue) => <article key={issue.id} className="rounded border border-outline p-3 text-sm"><strong>{issue.code === "EXTRACTION_GAP" ? "Пробел в извлечении" : issue.code === "AMBIGUOUS_DATE" ? "Дата без связи" : issue.code === "AMBIGUOUS_TECHNOLOGY" ? "Неясная технология" : "Проверьте смысл"}</strong><p>{issue.message}</p><p className="break-words text-xs text-muted">{sourceUnit(issue.sourceId, issue.unitId ?? "").name} {issue.unitId ?? ""}</p></article>)}</div>
        </div>
      </div>
      {(sheet.employment?.length ?? 0) > 0 && <div className="mt-5"><h3 className="font-semibold">Работа и проекты · требуют проверки</h3>{sheet.employment?.map((job) => <article key={job.id} className="mt-2 rounded border border-outline p-3 text-sm"><strong>{job.employer} · {job.role}</strong><p className="text-xs text-muted">{job.periods.map((period) => `${period.start.year}–${period.end?.year ?? "сейчас"}`).join(", ")}</p>{job.subprojects.map((sub) => <p key={sub.id} className="mt-1">{sub.name}</p>)}</article>)}</div>}
      <h3 className="mt-5 font-semibold">Буквальные кандидаты · {sheet.candidates.length}</h3>
      <div className="mt-2 flex max-h-44 flex-wrap gap-2 overflow-auto">{sheet.candidates.map((item) => <span key={item.id} className="rounded border border-outline px-2 py-1 text-sm">{item.text} · {item.confident ? "буквально" : "проверьте контекст"}</span>)}</div>
      <h3 className="mt-5 font-semibold">Учёт фрагментов · {sheet.units.length}</h3>
      <p className="text-xs text-muted">Каждый извлечённый фрагмент имеет явный статус. Повтор не стирает оригинал.</p>
      <div className="mt-2 max-h-52 space-y-1 overflow-auto">{accounts.map((item) => { const source = sourceUnit(item.sourceId, item.unitId); return <p key={`${item.sourceId}:${item.unitId}`} className="break-words border-b border-outline py-1 text-sm">{source.name} · {item.unitId} · {item.disposition} · {source.original.slice(0, 160)}</p>; })}</div>
      {sheet.units.length > 50 && <div className="mt-2 flex gap-2"><button type="button" className={control} disabled={page === 0} onClick={() => setPage(page - 1)}>Назад</button><button type="button" className={control} disabled={(page + 1) * 50 >= sheet.units.length} onClick={() => setPage(page + 1)}>Далее</button></div>}
    </>}
  </section>;
}
