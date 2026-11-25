import { errorMessage } from "../../errors/messages";
import { useEffect, useRef, useState } from "react";
import { names, labels, offeredFields, type RecordValue, type Kind } from "../../rich/fact-fields";
import type { PanelCommand } from "../../rich/v7-panel";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { factError } from "./error";
import { DateInput } from "./DateInput";
import { OffPage } from "./OffPage";
import { JobWarnings, overlapLine } from "./JobWarnings";
import { dateChecker, dateWarningLines } from "./dateCheck";
import type { DateWarning } from "../../projects/api";

const present = "по настоящее время";

export type FactTarget = { kind: Kind; record: RecordValue | null; remove?: boolean };
export function FactDialog({ target, close, submit, unshown, offPage = [], addPeriod = false, checkDates = null, jobName = () => "Без названия" }: {
  target: FactTarget; close: () => void; submit: (command: PanelCommand) => Promise<void>;
  /** Python's warnings for the form's dates before Save (D182); they never block Save. */
  checkDates?: ((recordId: string | null, values: Record<string, string>) => Promise<DateWarning[]>) | null;
  /** The Facts row name of another job, for its overlap line. */
  jobName?: (recordId: string) => string;
  /** The record's field lines the page lost (D179): each shows «Не на странице» and its way back. */
  offPage?: readonly string[] | undefined;
  /** The record's fields the document has no place for; the dialog leaves them out. */
  unshown?: readonly string[] | undefined;
  /** The document has a place for another period of this job. */
  addPeriod?: boolean;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const record = target.record;
  const inputs = record ? offeredFields(record, unshown) : names[target.kind].map(([key, label]) => ({ key, label, text: "", checked: undefined }));
  const addingPeriod = !record && target.kind === "employment" ? [{ key: "start", label: "Начало", text: "", checked: undefined },
    { key: "end", label: "Окончание", text: "", checked: undefined }, { key: "present", label: "Работаю сейчас", text: "", checked: false }] : [];
  // D182: the form's period values, as the panel sends them, for the warnings before Save.
  const dated = [...inputs, ...addingPeriod].filter(input => target.kind === "employment" && !target.remove
    && /^(?:period:.+:)?(?:start|end|present)$/u.test(input.key));
  const [warnings, setWarnings] = useState<readonly DateWarning[]>([]);
  const checker = useRef<ReturnType<typeof dateChecker> | null>(null);
  if (checkDates && !checker.current) checker.current = dateChecker({ check: values => checkDates(record?.id ?? null, values), show: setWarnings });
  useEffect(() => () => checker.current?.dispose(), []);
  function dateValues(element: HTMLFormElement): Record<string, string> {
    const data = new FormData(element);
    return Object.fromEntries(dated.map(input => [input.key, input.checked === undefined ? String(data.get(input.key) ?? "") : data.has(input.key) ? present : ""]));
  }
  function scheduleCheck() {
    if (!dated.length) return;
    checker.current?.schedule(() => {
      if (!form.current) return null;
      const values = dateValues(form.current);
      return { values, changed: dated.some(input => values[input.key] !== (input.checked === undefined ? input.text : input.checked ? present : "")) };
    });
  }
  function changes(element: HTMLFormElement): Record<string, string> {
    const data = new FormData(element), values: Record<string, string> = {};
    for (const input of [...inputs, ...addingPeriod]) {
      const value = input.checked === undefined ? String(data.get(input.key) ?? "") : data.has(input.key) ? "по настоящее время" : "";
      // A new job's unchecked «по настоящее время» sends nothing, as before the box was there.
      if (!record && input.checked !== undefined && !value) continue;
      if (!record || (input.checked === undefined ? value !== input.text : data.has(input.key) !== input.checked)) values[input.key] = value;
    }
    return values;
  }
  // A period is one line: its way back stands at its first field the page lost.
  const backAt = new Set(offPage.filter((key, index) => !key.startsWith("period:")
    || !offPage.slice(0, index).some(other => other.replace(/:(start|end)$/u, "") === key.replace(/:(start|end)$/u, ""))));
  const back = (key: string) => record && backAt.has(key) ? <OffPage name={inputs.find(input => input.key === key)?.label ?? key} busy={busy}
    restore={() => void apply({ operation: "restore", recordId: record.id, values: { field: key } })} /> : null;
  async function apply(command: PanelCommand) {
    setBusy(true); setError("");
    try { await submit(command); close(); }
    catch (error) { setError(factError(error)); }
    finally { setBusy(false); }
  }
  return <Dialog open close={() => { if (!busy) close(); }} title={target.remove ? "Удалить факт?" : labels[target.kind]}>
    <form ref={form} onChange={scheduleCheck} onClick={event => { if (event.target instanceof HTMLButtonElement && event.target.type === "button") scheduleCheck(); }} onSubmit={event => {
      event.preventDefault();
      if (target.remove && record) { void apply({ operation: "remove", recordId: record.id }); return; }
      const values = changes(event.currentTarget);
      if (record && !Object.keys(values).length) { close(); return; }
      void apply(record ? { operation: "edit", recordId: record.id, values } : { operation: "add", recordKind: target.kind, values });
    }}>
      {target.remove ? <p className="dialog-copy">{target.kind === "claim" ? "Текст резюме не изменится." : "Поля этого факта будут удалены из документа."}</p> : <>
        {!inputs.length && <p className="dialog-copy">Этого факта нет в документе, поэтому здесь его не изменить.</p>}
        <div className="fact-form-grid">{[...inputs, ...addingPeriod].map((field, index) => "date" in field || field.key === "start" || field.key === "end" || field.key === "completion"
          ? back(field.key) ? <div key={field.key}><DateInput name={field.key} label={field.label} field={"date" in field ? field.date : undefined} disabled={busy} />{back(field.key)}</div>
            : <DateInput key={field.key} name={field.key} label={field.label} field={"date" in field ? field.date : undefined} disabled={busy} />
          : target.kind === "claim" ? <div key={field.key} className="full">
            <label htmlFor={`fact-${field.key}`}>{field.label}</label><textarea id={`fact-${field.key}`} name={field.key}
              aria-label={field.label} defaultValue={field.text} autoFocus disabled={busy} maxLength={16000} rows={6} />
          </div> : <div key={field.key} className={index === 0 || field.key === "role" ? "full" : ""}>
          <label htmlFor={`fact-${field.key}`}>{field.label}</label><input id={`fact-${field.key}`} name={field.key} aria-label={field.label}
            type={field.checked === undefined ? "text" : "checkbox"} defaultValue={field.checked === undefined ? field.text : "present"}
            defaultChecked={field.checked} autoFocus={index === 0} disabled={busy} maxLength={16000} required={!record && index === 0} />
          {back(field.key)}
        </div>)}</div>
        {dated.length > 0 && checkDates && <JobWarnings lines={dateWarningLines(warnings, jobName, overlapLine)} live />}
        {record?.kind === "employment" && <div className="uir-period-actions">
          {record.periods.map((period, index) => <button className="text-button" type="button" key={period.id} disabled={busy}
            onClick={() => { if (form.current) void apply({ operation: "remove_period", recordId: record.id, periodId: period.id,
              values: Object.fromEntries(Object.entries(changes(form.current)).filter(([key]) => !key.startsWith(`period:${period.id}:`))) }); }}>Удалить период {index + 1}</button>)}
          {addPeriod && <button className="text-button" type="button" disabled={busy} onClick={() => { if (form.current) void apply({ operation: "add_period", recordId: record.id, values: changes(form.current) }); }}>Добавить период</button>}
        </div>}
      </>}
      {error && <p className="notice warning" role="alert">{errorMessage(error)}</p>}
      <div className="dialog-actions"><Button disabled={busy} onClick={close}>Отмена</Button>
        <Button type="submit" variant={target.remove ? "danger" : "primary"} busy={busy} busyLabel={target.remove ? "Удаляем…" : "Сохраняем…"}>{target.remove ? "Удалить" : "Сохранить"}{!target.remove && <Icon name="check" />}</Button></div>
    </form>
  </Dialog>;
}
