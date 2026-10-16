import { useRef, useState } from "react";
import { fields, names, labels, type RecordValue, type Kind } from "../../rich/fact-fields";
import type { PanelCommand } from "../../rich/synchronization";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { factError } from "./error";
import { AppliedIntentFailure } from "../../rich/intent-queue";

export type FactTarget = { kind: Exclude<Kind, "technology">; record: RecordValue | null; remove?: boolean };
export function FactDialog({ target, close, submit }: { target: FactTarget; close: () => void; submit: (command: PanelCommand) => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const record = target.record;
  const inputs = record ? fields(record) : names[target.kind].map(([key, label]) => ({ key, label, text: "", checked: undefined }));
  const addingPeriod = !record && target.kind === "employment" ? [{ key: "start", label: "Начало", text: "", checked: undefined },
    { key: "end", label: "Окончание", text: "", checked: undefined }] : [];
  function changes(element: HTMLFormElement): Record<string, string> {
    const data = new FormData(element), values: Record<string, string> = {};
    for (const input of [...inputs, ...addingPeriod]) {
      const value = input.checked === undefined ? String(data.get(input.key) ?? "") : data.has(input.key) ? "по настоящее время" : "";
      if (!record || (input.checked === undefined ? value !== input.text : data.has(input.key) !== input.checked)) values[input.key] = value;
    }
    return values;
  }
  async function apply(command: PanelCommand) {
    setBusy(true); setError("");
    try { await submit(command); close(); }
    catch (error) { if (error instanceof AppliedIntentFailure) close(); else setError(factError(error)); }
    finally { setBusy(false); }
  }
  return <Dialog open close={() => { if (!busy) close(); }} title={target.remove ? "Удалить факт?" : labels[target.kind]}>
    <form ref={form} onSubmit={event => {
      event.preventDefault();
      if (target.remove && record) { void apply({ operation: "remove", recordId: record.id }); return; }
      const values = changes(event.currentTarget);
      if (record && !Object.keys(values).length) { close(); return; }
      void apply(record ? { operation: "edit", recordId: record.id, values } : { operation: "add", recordKind: target.kind, values });
    }}>
      {target.remove ? <p className="dialog-copy">Связанные поля будут удалены из документа. Остальной текст сохранится.</p> : <>
        <p className="dialog-subtitle">Изменения появятся в документе после сохранения.</p>
        <div className="fact-form-grid">{[...inputs, ...addingPeriod].map((field, index) => <div key={field.key} className={index === 0 ? "full" : ""}>
          <label htmlFor={`fact-${field.key}`}>{field.label}</label><input id={`fact-${field.key}`} name={field.key} aria-label={field.label}
            type={field.checked === undefined ? "text" : "checkbox"} defaultValue={field.checked === undefined ? field.text : "present"}
            defaultChecked={field.checked} autoFocus={index === 0} disabled={busy} maxLength={16000} />
        </div>)}</div>
        {(target.kind === "employment" || target.kind === "education") && <p className="dialog-subtitle">Укажите год, месяц или полную дату, как в исходнике. Неясные даты сохранятся для проверки.</p>}
        {record?.kind === "employment" && <div className="uir-period-actions">
          {record.periods.map((period, index) => <button className="text-button" type="button" key={period.id} disabled={busy}
            onClick={() => { if (form.current) void apply({ operation: "remove_period", recordId: record.id, periodId: period.id,
              values: Object.fromEntries(Object.entries(changes(form.current)).filter(([key]) => !key.startsWith(`period:${period.id}:`))) }); }}>Удалить период {index + 1}</button>)}
          <button className="text-button" type="button" disabled={busy} onClick={() => { if (form.current) void apply({ operation: "add_period", recordId: record.id, values: changes(form.current) }); }}>Добавить период</button>
        </div>}
      </>}
      {error && <p className="notice warning" role="alert">{error}</p>}
      <div className="dialog-actions"><Button disabled={busy} onClick={close}>Отмена</Button>
        <Button type="submit" variant={target.remove ? "danger" : "primary"} disabled={busy}>{target.remove ? "Удалить факт" : "Сохранить факт"}{!target.remove && <Icon name="check" />}</Button></div>
    </form>
  </Dialog>;
}
