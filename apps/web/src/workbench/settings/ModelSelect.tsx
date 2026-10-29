import type { ModelGroup } from "../../connection/workflow";

/** Model options grouped by provider (D119); one provider shows a plain list. A saved model no provider offers stays
 * visible and disabled. */
export function ModelOptions({ groups, value }: { groups: readonly ModelGroup[]; value: string | null }) {
  const offered = groups.flatMap(group => group.models);
  const options = (models: readonly string[]) => models.map(model => <option key={model} value={model}>{model}</option>);
  return <>
    {value && !offered.includes(value) && <option value={value} disabled>{value} · недоступна</option>}
    {groups.length === 1 ? options(groups[0]?.models ?? [])
      : groups.map(group => <optgroup key={group.label} label={group.label}>{options(group.models)}</optgroup>)}
  </>;
}

export function ModelSelect({ id, label, value, groups, change, disabled, defaultLabel }: {
  id: string; label: string; value: string | null; groups: readonly ModelGroup[];
  change: (value: string | null) => void; disabled: boolean; defaultLabel?: string;
}) {
  return <><label htmlFor={id}>{label}</label>
    <select className="model-select" id={id} aria-label={label} value={value ?? ""} disabled={disabled}
      onChange={event => change(event.currentTarget.value || null)}>
      <option value="" disabled={!defaultLabel}>{defaultLabel ?? "Выберите модель"}</option>
      <ModelOptions groups={groups} value={value} />
    </select></>;
}
