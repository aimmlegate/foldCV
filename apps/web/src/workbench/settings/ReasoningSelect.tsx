import { isReasoningEffort, type ModelReasoning, type ReasoningEffort } from "../../connection/reasoning";

/** Reasoning levels in Settings and the import form. */
export const reasoningLabels: Record<ReasoningEffort, string> = {
  none: "Без рассуждений", minimal: "Минимальный", low: "Низкий", medium: "Средний", high: "Высокий", xhigh: "Очень высокий",
  max: "Максимальный", ultra: "Ультра",
};

export function defaultReasoningLabel(value: ReasoningEffort | null | undefined): string {
  return value ? `По умолчанию (${reasoningLabels[value].toLowerCase()})` : "По умолчанию";
}

export function ReasoningSelect({ value, metadata, disabled, change, id = "rewrite-reasoning", label = "Рассуждения при правке текста" }: {
  value: ReasoningEffort | null; metadata: ModelReasoning | undefined; disabled: boolean;
  change: (value: ReasoningEffort | null) => void; id?: string; label?: string;
}) {
  const supported = metadata?.supported ?? [];
  const choices = value && !supported.includes(value) ? [value, ...supported] : supported;
  return <><label htmlFor={id}>{label}</label>
    <select className="model-select" id={id} aria-label={label} value={value ?? ""}
      disabled={disabled} onChange={event => {
        const next = event.currentTarget.value;
        if (next === "" || isReasoningEffort(next)) change(next === "" ? null : next);
      }}>
      <option value="">{defaultReasoningLabel(metadata?.default)}</option>
      {choices.map(effort => <option key={effort} value={effort} disabled={!supported.includes(effort)}>
        {reasoningLabels[effort]}{!supported.includes(effort) ? " · недоступен" : ""}
      </option>)}
    </select>
  </>;
}
