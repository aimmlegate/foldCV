import { useState, type ReactNode } from "react";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { PanelCommand } from "./synchronization";

type RecordValue = WorkingFacts["records"][number];
type Kind = "candidate" | "employment" | "technology" | "education" | "language";
type Field = { key: string; label: string; text: string; checked?: boolean };
const labels = { candidate: "Кандидат", employment: "Опыт", technology: "Технологии", education: "Образование", language: "Языки" };
const names: Record<Kind, readonly (readonly [string, string])[]> = {
  candidate: [["name", "Имя"], ["title", "Должность"], ["location", "Город"]],
  employment: [["employer", "Компания"], ["role", "Роль"]], technology: [["display", "Технология"]],
  education: [["institution", "Учебное заведение"], ["qualification", "Квалификация"], ["specialty", "Специальность"], ["completion", "Дата окончания"]],
  language: [["language", "Язык"], ["level", "Уровень"]],
};
function fields(record: RecordValue): Field[] {
  if (!(record.kind in names)) return [];
  const values = Object.entries(record);
  const result = names[record.kind as Kind].map(([key, label]) => {
    const value: unknown = values.find(([name]) => name === key)?.[1];
    return { key, label, text: typeof value === "object" && value !== null && "rawText" in value && typeof value.rawText === "string" ? value.rawText : "" };
  });
  if (record.kind === "employment") record.periods.forEach((period, index) => {
    result.push({ key: `period:${period.id}:start`, label: `Начало ${index + 1}`, text: period.start.rawText },
      { key: `period:${period.id}:end`, label: `Окончание ${index + 1}`, text: period.end.rawText });
  });
  return [...result, ...(record.kind === "employment" ? record.periods.map((period, index) => ({ key: `period:${period.id}:present`,
    label: `Работаю сейчас ${index + 1}`, text: period.present.rawText, checked: period.present.value === true })) : [])];
}
function title(record: RecordValue): string {
  if (record.kind === "employment") return record.employer.rawText || "Без названия";
  if (record.kind === "technology") return record.display.rawText || "Без названия";
  if (record.kind === "education") return record.institution.rawText || "Без названия";
  if (record.kind === "language") return record.language.rawText || "Без названия";
  return "Кандидат";
}
function needsCheck(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(needsCheck);
  if (typeof value !== "object" || value === null) return false;
  if ("status" in value && "rawText" in value) return value.rawText !== "" && value.status !== "known";
  return Object.values(value).some(needsCheck);
}
function values(form: HTMLFormElement): Record<string, string> {
  return Object.fromEntries([...new FormData(form)].filter((entry): entry is [string, string] => typeof entry[1] === "string"));
}
function RecordForm({ record, submit, close }: { record: RecordValue; submit: (command: PanelCommand) => Promise<void>; close: () => void }) {
  const [busy, setBusy] = useState(false);
  const inputs = fields(record);
  return <form onSubmit={event => {
    event.preventDefault(); const data = values(event.currentTarget);
    const changed = Object.fromEntries(inputs.filter(field => field.checked === undefined ? data[field.key] !== field.text : !!data[field.key] !== field.checked)
      .map(field => [field.key, field.checked === undefined ? data[field.key] ?? "" : data[field.key] ? "по настоящее время" : ""]));
    setBusy(true); void submit({ operation: "edit", recordId: record.id, values: changed }).then(close).catch(() => {}).finally(() => setBusy(false));
  }}>
    {inputs.map(field => <label key={field.key}>{field.label}<input name={field.key} aria-label={field.label} type={field.checked === undefined ? "text" : "checkbox"}
      defaultValue={field.checked === undefined ? field.text : "present"} defaultChecked={field.checked} disabled={busy} /></label>)}
    {record.kind === "education" && <small>Сохраняйте точность даты: ГГГГ, ГГГГ-ММ или ГГГГ-ММ-ДД.</small>}
    {record.kind === "employment" && <><small>ГГГГ, ГГГГ-ММ или ГГГГ-ММ-ДД. Неясные даты сохранятся для проверки.</small>
      {record.periods.map((period, index) => <button type="button" key={period.id} disabled={busy} onClick={() => {
        void submit({ operation: "remove_period", recordId: record.id, periodId: period.id }).then(close).catch(() => {});
      }}>Удалить период {index + 1}</button>)}
      <button type="button" disabled={busy} onClick={() => void submit({ operation: "add_period", recordId: record.id }).then(close).catch(() => {})}>Добавить период</button></>}
    <div><button disabled={busy}>Сохранить</button><button type="button" disabled={busy} onClick={close}>Отмена</button></div>
  </form>;
}
function AddForm({ kind, job, submit }: { kind: Kind; job?: string; submit: (command: PanelCommand) => Promise<void> }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false);
  return open ? <form onSubmit={event => {
    event.preventDefault(); const data = values(event.currentTarget);
    setBusy(true); void submit({ operation: "add", recordKind: kind, jobId: job ?? null, values: data }).then(() => setOpen(false)).catch(() => {}).finally(() => setBusy(false));
  }}>{names[kind].map(([key, label]) => <label key={key}>{label}<input name={key} aria-label={label} disabled={busy} /></label>)}
    {kind === "employment" && <><label>Начало<input name="start" aria-label="Начало" disabled={busy} /></label><label>Окончание<input name="end" aria-label="Окончание" disabled={busy} /></label></>}
    <button disabled={busy}>Добавить</button><button type="button" disabled={busy} onClick={() => setOpen(false)}>Отмена</button>
  </form> : <button className="rich-facts-add" onClick={() => setOpen(true)}>+ {kind === "technology" ? "Технология" : labels[kind]}</button>;
}
function RecordRow({ record, submit }: { record: RecordValue; submit: (command: PanelCommand) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  return <div className="rich-fact-row" data-fact-id={record.id}>
    <button className="rich-fact-title" onClick={() => setEditing(value => !value)}>{title(record)}</button>
    {record.userCorrected && <small>Исправлено</small>}
    {needsCheck(record) && <small>Проверьте значение</small>}
    {editing && <RecordForm key={JSON.stringify(fields(record))} record={record} submit={submit} close={() => setEditing(false)} />}
    <button className="rich-facts-remove" aria-label={`Удалить: ${title(record)}`} onClick={() => void submit({ operation: "remove", recordId: record.id }).catch(() => {})}>Удалить</button>
  </div>;
}
export function FactsPanel({ facts, submit, timeline }: { facts: WorkingFacts; submit: (command: PanelCommand) => Promise<void>; timeline?: ReactNode }) {
  const [error, setError] = useState("");
  async function apply(command: PanelCommand) {
    setError("");
    try { await submit(command); } catch (error) { setError(error instanceof Error ? error.message : "Не удалось обновить факт"); throw error; }
  }
  return <aside className="rich-facts bg-surface text-content border-outline" aria-label="Факты резюме"><h2>Факты</h2>
    {error && <p role="alert">{error}</p>}
    {(["candidate", "employment", "technology", "education", "language"] as const).map(kind => <details key={kind} open>
      <summary>{labels[kind]}</summary>
      {kind === "technology" && <small>Общие навыки без привязки к работе</small>}
      {facts.records.filter(record => record.kind === kind && (record.kind !== "technology" || record.jobId === null)).map(record => <div key={record.id}>
        <RecordRow record={record} submit={apply} />
        {record.kind === "employment" && <div className="rich-job-technologies"><small>Технологии этой работы</small>
          {facts.records.filter(item => item.kind === "technology" && item.jobId === record.id).map(item => <RecordRow key={item.id} record={item} submit={apply} />)}
          <AddForm kind="technology" job={record.id} submit={apply} /></div>}
      </div>)}
      {kind === "employment" && timeline}
      {(kind !== "candidate" || !facts.records.some(record => record.kind === "candidate")) && <AddForm kind={kind} submit={apply} />}
    </details>)}
  </aside>;
}
