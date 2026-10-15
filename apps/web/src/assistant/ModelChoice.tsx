import type { AgentCapabilities } from "../contracts/generated/agent_capabilities";
export function ModelChoice({ selected, models, capabilities, disabled = false, change }: { selected: string | null; models: readonly string[];
  capabilities?: AgentCapabilities | null; disabled?: boolean; change: (model: string | null) => void }) {
  const choices = selected && !models.includes(selected) ? [selected, ...models] : models;
  return <label className="assistant-model">Модель помощника<select aria-label="Модель помощника" value={selected ?? ""} disabled={disabled}
    onChange={event => change(event.target.value || null)}><option value="">Выберите модель помощника</option>
    {choices.map(model => <option key={model} value={model}>{model}{!models.includes(model) ? " · недоступна"
      : capabilities?.models.find(item => item.model === model)?.state === "incompatible" ? " · инструменты недоступны" : ""}</option>)}
  </select></label>;
}
