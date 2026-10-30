import { useState } from "react";
import type { WorkingFieldPartialDate } from "../../contracts/generated/working_facts";
import { changePrecision, datePrecision, dateText, type DatePrecision } from "./dates";

export function DateInput({ name, label, field, disabled }: {
  name: string; label: string; field: WorkingFieldPartialDate | undefined; disabled: boolean;
}) {
  const initial = field ? dateText(field) : "";
  const [precision, setPrecision] = useState<DatePrecision>(() => initial ? datePrecision(initial) : "month");
  const [value, setValue] = useState(initial), [raw, setRaw] = useState(field?.rawText ?? "");
  const [needsChoice, setNeedsChoice] = useState(false);
  const id = `fact-${name}`;
  return <div className="date-field">
    <label htmlFor={id}>{label}</label>
    <div className="date-input-row">
      <select aria-label={`Точность: ${label}`} value={precision} disabled={disabled} onChange={event => {
        const next = event.currentTarget.value;
        if (next !== "year" && next !== "month" && next !== "day" && next !== "text") return;
        const updated = changePrecision(value, next, field?.rawText);
        setPrecision(next); setValue(updated); setNeedsChoice(!updated && !!raw);
        if (updated) setRaw(updated);
      }}><option value="year">Год</option><option value="month">Месяц</option><option value="day">Дата</option><option value="text">Как в исходнике</option></select>
      <input id={id} aria-label={label} type={precision === "year" ? "number" : precision === "text" ? "text" : precision === "month" ? "month" : "date"}
        min={precision === "year" ? "1" : precision === "month" ? "0001-01" : "0001-01-01"}
        max={precision === "year" ? "9999" : precision === "month" ? "9999-12" : "9999-12-31"}
        maxLength={16000} required={needsChoice} disabled={disabled} value={value} placeholder={precision === "year" ? "ГГГГ" : "Дата из исходника"}
        onChange={event => { const text = event.currentTarget.value; setValue(text); setNeedsChoice(false);
          setRaw(precision === "year" && text ? text.padStart(4, "0") : text); }} />
    </div>
    <input type="hidden" name={name} value={raw} disabled={disabled} />
    {(raw || needsChoice) && <button type="button" className="text-button date-clear" disabled={disabled} onClick={() => { setValue(""); setRaw(""); setNeedsChoice(false); }}>Очистить</button>}
  </div>;
}
