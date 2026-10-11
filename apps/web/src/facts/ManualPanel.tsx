import { useRef, useState } from "react";
import type { ManualEmployment, ManualInput, ManualLeadership, ManualMetric, ManualSubproject } from "./working";
import type { DraftView } from "./draftWorkflow";

const control = "rounded border border-outline bg-panel px-3 py-2 text-content hover:bg-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const field = "w-full rounded border border-outline bg-surface p-2 text-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const freshJob = (): ManualEmployment => ({ id: `job_user_${crypto.randomUUID()}`, employer: "", role: "", start: "", end: "", description: "", subprojects: [] });
const freshSubproject = (): ManualSubproject => ({ id: `sub_user_${crypto.randomUUID()}`, name: "", start: "", end: "", description: "" });
const freshMetric = (): ManualMetric => ({ id: `fact_user_${crypto.randomUUID()}`, jobId: null, number: 0,
  upperNumber: null, comparator: "exact", unit: "", period: null, baseline: null, result: null, scope: null,
  attribution: "unknown", qualifiers: [] });
const freshLeadership = (): ManualLeadership => ({ id: `fact_user_${crypto.randomUUID()}`, jobId: "", action: "",
  attribution: "unknown", teamSize: null, teamUnit: "", teamBaseline: null });

export function ManualPanel({ onOpen, onDraft, draftView, onCancelDraft, onManualChange, initialInput, onInput }: {
  onOpen: (input: ManualInput) => void;
  onDraft?: ((input: ManualInput, isCurrent: () => boolean) => void) | undefined;
  draftView?: DraftView | undefined;
  onCancelDraft?: (() => void) | undefined;
  onManualChange?: (() => void) | undefined;
  initialInput: ManualInput; onInput: (input: ManualInput) => void;
}) {
  const [input, setInput] = useState<ManualInput>(initialInput);
  const manualRevision = useRef(0);
  const changed = () => { manualRevision.current += 1; onManualChange?.(); };
  const changeInput = (update: (current: ManualInput) => ManualInput) => { changed(); setInput((current) => {
    const next = update(current); onInput(next); return next;
  }); };
  const setField = <K extends keyof ManualInput>(key: K, value: ManualInput[K]) =>
    changeInput((current) => ({ ...current, [key]: value }));
  const setJob = (id: string, change: Partial<ManualEmployment>) => changeInput((current) => ({ ...current,
    employment: current.employment.map((job) => job.id === id ? { ...job, ...change } : job) }));
  const setMetric = (id: string, change: Partial<ManualMetric>) => changeInput((current) => ({ ...current,
    metrics: current.metrics.map((metric) => metric.id === id ? { ...metric, ...change } : metric) }));
  const setLeadership = (id: string, change: Partial<ManualLeadership>) => changeInput((current) => ({ ...current,
    leadership: current.leadership.map((item) => item.id === id ? { ...item, ...change } : item) }));
  return <section aria-label="Ручные данные" className="mt-5 rounded border border-outline p-4">
    <h3 className="font-semibold">Ручной путь к редактору</h3>
    <p className="mt-1 text-sm text-muted">Укажите данные, которых нет в проверенных фактах. Исходник и лист фактов останутся в памяти отдельно. Текст работы сохраняется дословно.</p>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <label>Имя кандидата<input className={field} value={input.name} onChange={(event) => setField("name", event.target.value)} /></label>
      <label>Должность<input className={field} value={input.title} onChange={(event) => setField("title", event.target.value)} /></label>
      <label>Дата наблюдения, YYYY-MM-DD<input className={field} placeholder="2026-10-11" value={input.asOf} onChange={(event) => setField("asOf", event.target.value)} /></label>
      <label>Язык<select className={field} value={input.language} onChange={(event) => {
        const value = event.target.value;
        if (value === "ru" || value === "en" || value === "mixed") setField("language", value);
      }}><option value="ru">Русский</option><option value="en">English</option><option value="mixed">Смешанный</option></select></label>
    </div>
    <label className="mt-3 block">Образование<textarea className={field} value={input.education} onChange={(event) => setField("education", event.target.value)} /></label>
    <label className="mt-3 block">Языки, через запятую<input className={field} value={input.languages.join(", ")} onChange={(event) => setField("languages", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} /></label>
    <label className="mt-3 block">Другие навыки, через запятую<input className={field} value={input.skills.join(", ")} onChange={(event) => setField("skills", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} /></label>
    <h4 className="mt-4 font-semibold">Работа и проекты</h4>
    {input.employment.map((job) => <div key={job.id} className="mt-2 rounded border border-outline p-3">
      <div className="grid gap-2 sm:grid-cols-2"><label>Организация<input className={field} value={job.employer} onChange={(event) => setJob(job.id, { employer: event.target.value })} /></label>
        <label>Роль<input className={field} value={job.role} onChange={(event) => setJob(job.id, { role: event.target.value })} /></label>
        <label>Начало, YYYY или YYYY-MM<input className={field} value={job.start} onChange={(event) => setJob(job.id, { start: event.target.value })} /></label>
        <label>Конец, пусто если текущая<input className={field} value={job.end} onChange={(event) => setJob(job.id, { end: event.target.value })} /></label></div>
      <label className="mt-2 block">Дословный текст работы<textarea className={field} value={job.description} onChange={(event) => setJob(job.id, { description: event.target.value })} /></label>
      {job.subprojects.map((sub) => <div key={sub.id} className="mt-2 grid gap-2 border-l-2 border-outline pl-3 sm:grid-cols-2">
        <label>Подпроект<input className={field} value={sub.name} onChange={(event) => setJob(job.id, { subprojects: job.subprojects.map((item) => item.id === sub.id ? { ...item, name: event.target.value } : item) })} /></label>
        <label>Начало<input className={field} value={sub.start} onChange={(event) => setJob(job.id, { subprojects: job.subprojects.map((item) => item.id === sub.id ? { ...item, start: event.target.value } : item) })} /></label>
        <label>Конец<input className={field} value={sub.end} onChange={(event) => setJob(job.id, { subprojects: job.subprojects.map((item) => item.id === sub.id ? { ...item, end: event.target.value } : item) })} /></label>
        <label>Дословный текст<input className={field} value={sub.description} onChange={(event) => setJob(job.id, { subprojects: job.subprojects.map((item) => item.id === sub.id ? { ...item, description: event.target.value } : item) })} /></label>
      </div>)}
      <div className="mt-2 flex gap-2"><button type="button" className={control} onClick={() => setJob(job.id, { subprojects: [...job.subprojects, freshSubproject()] })}>Добавить подпроект</button>
        <button type="button" className={control} onClick={() => setField("employment", input.employment.filter((item) => item.id !== job.id))}>Удалить работу</button></div>
    </div>)}
    <button type="button" className={`${control} mt-2`} onClick={() => setField("employment", [...input.employment, freshJob()])}>Добавить работу</button>
    <h4 className="mt-4 font-semibold">Числа и вклад</h4>
    {input.metrics.map((metric) => <div key={metric.id} className="mt-2 grid gap-2 rounded border border-outline p-3 sm:grid-cols-2">
      <label>Работа<select className={field} value={metric.jobId ?? ""} onChange={(event) => setMetric(metric.id, { jobId: event.target.value || null })}><option value="">Без привязки</option>{input.employment.map((job) => <option key={job.id} value={job.id}>{job.employer || "Новая работа"}</option>)}</select></label>
      <label>Число<input type="number" className={field} value={metric.number} onChange={(event) => setMetric(metric.id, { number: Number(event.target.value) })} /></label>
      <label>Сравнение<select className={field} value={metric.comparator} onChange={(event) => setMetric(metric.id, { comparator: event.target.value as ManualMetric["comparator"], upperNumber: event.target.value === "range" ? metric.upperNumber ?? metric.number : null })}><option value="exact">Ровно</option><option value="at_least">Не менее</option><option value="at_most">Не более</option><option value="approximately">Примерно</option><option value="range">Диапазон</option></select></label>
      {metric.comparator === "range" && <label>Верхняя граница<input type="number" className={field} value={metric.upperNumber ?? ""} onChange={(event) => setMetric(metric.id, { upperNumber: Number(event.target.value) })} /></label>}
      <label>Единица<input className={field} value={metric.unit} onChange={(event) => setMetric(metric.id, { unit: event.target.value })} /></label>
      <label>Чей результат<select className={field} value={metric.attribution} onChange={(event) => setMetric(metric.id, { attribution: event.target.value as ManualMetric["attribution"] })}><option value="unknown">Неизвестно</option><option value="personal">Личный</option><option value="team">Команда</option><option value="organization">Организация</option></select></label>
      <label>Период<input className={field} value={metric.period ?? ""} onChange={(event) => setMetric(metric.id, { period: event.target.value || null })} /></label>
      <label>До изменения<input className={field} value={metric.baseline ?? ""} onChange={(event) => setMetric(metric.id, { baseline: event.target.value || null })} /></label>
      <label>Результат<input className={field} value={metric.result ?? ""} onChange={(event) => setMetric(metric.id, { result: event.target.value || null })} /></label>
      <label>Контекст<input className={field} value={metric.scope ?? ""} onChange={(event) => setMetric(metric.id, { scope: event.target.value || null })} /></label>
      <label>Условия, через запятую<input className={field} value={metric.qualifiers.join(", ")} onChange={(event) => setMetric(metric.id, { qualifiers: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} /></label>
      <button type="button" className={control} onClick={() => setField("metrics", input.metrics.filter((item) => item.id !== metric.id))}>Удалить число</button>
    </div>)}
    <button type="button" className={`${control} mt-2`} onClick={() => setField("metrics", [...input.metrics, freshMetric()])}>Добавить число</button>
    <h4 className="mt-4 font-semibold">Руководство и вклад</h4>
    {input.leadership.map((item) => <div key={item.id} className="mt-2 grid gap-2 rounded border border-outline p-3 sm:grid-cols-2">
      <label>Работа руководства<select className={field} value={item.jobId} onChange={(event) => setLeadership(item.id, { jobId: event.target.value })}><option value="">Выберите работу</option>{input.employment.map((job) => <option key={job.id} value={job.id}>{job.employer || "Новая работа"}</option>)}</select></label>
      <label>Действие<input className={field} value={item.action} onChange={(event) => setLeadership(item.id, { action: event.target.value })} /></label>
      <label>Чей вклад<select className={field} value={item.attribution} onChange={(event) => setLeadership(item.id, { attribution: event.target.value as ManualLeadership["attribution"] })}><option value="unknown">Неизвестно</option><option value="personal">Личный</option><option value="team">Команда</option><option value="organization">Организация</option></select></label>
      <label>Размер команды<input type="number" className={field} value={item.teamSize ?? ""} onChange={(event) => setLeadership(item.id, { teamSize: event.target.value ? Number(event.target.value) : null })} /></label>
      <label>Единица команды<input className={field} value={item.teamUnit} onChange={(event) => setLeadership(item.id, { teamUnit: event.target.value })} /></label>
      <label>Было до изменения<input className={field} value={item.teamBaseline ?? ""} onChange={(event) => setLeadership(item.id, { teamBaseline: event.target.value || null })} /></label>
      <button type="button" className={control} onClick={() => setField("leadership", input.leadership.filter((entry) => entry.id !== item.id))}>Удалить руководство</button>
    </div>)}
    <button type="button" className={`${control} mt-2`} onClick={() => setField("leadership", [...input.leadership, freshLeadership()])}>Добавить руководство</button>
    <div className="mt-4 flex flex-wrap gap-2"><button type="button" className={control} onClick={() => onOpen(input)}>Открыть дословный черновик</button>
      {onDraft && <button type="button" className={control} disabled={draftView?.pending} onClick={() => {
        const revision = manualRevision.current;
        onDraft(structuredClone(input), () => revision === manualRevision.current);
      }}>Составить черновик</button>}
      {draftView?.pending && <button type="button" className={control} onClick={onCancelDraft}>Отменить составление</button>}</div>
    {draftView?.pending && <p role="status" className="mt-2 text-sm">{draftView.stage === "normalize" ? "Проверяем смысл фактов…" : "Составляем текст…"}</p>}
    {draftView?.error && <p role="alert" className="mt-2 text-sm text-danger">{draftView.error}</p>}
  </section>;
}
