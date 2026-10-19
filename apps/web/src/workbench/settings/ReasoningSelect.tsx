import { isReasoningEffort, type ModelReasoning, type ReasoningEffort } from "../../connection/reasoning";

const labels: Record<ReasoningEffort, string> = {
  none: "None · без рассуждений", minimal: "Minimal · минимум", low: "Low · быстрее",
  medium: "Medium · баланс", high: "High · подробнее", xhigh: "XHigh · глубже", max: "Max · максимум", ultra: "Ultra",
};

export function ReasoningSelect({ value, metadata, disabled, change }: {
  value: ReasoningEffort | null; metadata: ModelReasoning | undefined; disabled: boolean;
  change: (value: ReasoningEffort | null) => void;
}) {
  const supported = metadata?.supported ?? [];
  const choices = value && !supported.includes(value) ? [value, ...supported] : supported;
  return <><label htmlFor="rewrite-reasoning">Reasoning при правке текста</label>
    <select className="model-select" id="rewrite-reasoning" aria-label="Reasoning при правке текста" value={value ?? ""}
      disabled={disabled} onChange={event => {
        const next = event.currentTarget.value;
        if (next === "" || isReasoningEffort(next)) change(next === "" ? null : next);
      }}>
      <option value="">По умолчанию{metadata?.default ? ` · ${metadata.default}` : ""}</option>
      {choices.map(effort => <option key={effort} value={effort} disabled={!supported.includes(effort)}>
        {labels[effort]}{!supported.includes(effort) ? " · недоступен" : ""}
      </option>)}
    </select>
    <p className="small muted">Глубина рассуждений для правки выделения. Low обычно быстрее. Применится к следующему запросу.</p>
  </>;
}
