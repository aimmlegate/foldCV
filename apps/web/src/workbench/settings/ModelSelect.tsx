export function ModelSelect({ id, label, value, models, change, disabled, defaultLabel }: {
  id: string; label: string; value: string | null; models: readonly string[];
  change: (value: string | null) => void; disabled: boolean; defaultLabel?: string;
}) {
  const choices = value && !models.includes(value) ? [value, ...models] : models;
  return <><label htmlFor={id}>{label}</label>
    <select className="model-select" id={id} aria-label={label} value={value ?? ""} disabled={disabled}
      onChange={event => change(event.currentTarget.value || null)}>
      <option value="" disabled={!defaultLabel}>{defaultLabel ?? "Выберите модель"}</option>
      {choices.map(model => <option key={model} value={model} disabled={!models.includes(model)}>
        {model}{!models.includes(model) ? " · недоступна" : ""}
      </option>)}
    </select></>;
}
