import { isReasoningEffort, longReasoning, type ModelReasoning, type ReasoningEffort } from "../../connection/reasoning";
import { defaultReasoningLabel, reasoningLabels } from "../settings/ReasoningSelect";

/** The level an import is sent with: the chosen one while its model reports it. */
export function chosenEffort(effort: ReasoningEffort | null, reasoning: ModelReasoning | undefined): ReasoningEffort | null {
  return effort && reasoning?.supported.includes(effort) ? effort : null;
}

export function EffortField({ effort, reasoning, disabled, change }: {
  effort: ReasoningEffort | null; reasoning: ModelReasoning | undefined; disabled: boolean; change: (value: ReasoningEffort | null) => void;
}) {
  const chosen = chosenEffort(effort, reasoning);
  // The level the import runs at: the chosen one, else the model's default (D114: it applies to every block).
  const effective = chosen ?? reasoning?.default ?? null;
  const slow = effective !== null && longReasoning(effective);
  return <div className="import-option"><label htmlFor="import-effort">Рассуждения</label>
    <select className="model-select" id="import-effort" aria-label="Уровень рассуждений импорта" value={chosen ?? ""}
      aria-describedby={slow ? "import-effort-help" : undefined}
      disabled={disabled || !reasoning?.supported.length} onChange={event => {
        const next = event.currentTarget.value;
        change(isReasoningEffort(next) ? next : null);
      }}>
      <option value="">{defaultReasoningLabel(reasoning?.default)}</option>
      {(reasoning?.supported ?? []).map(value => <option key={value} value={value}>{reasoningLabels[value]}</option>)}
    </select>
    {slow && <small id="import-effort-help">Импорт на высоком уровне рассуждений может занять больше времени.</small>}</div>;
}

export function RewriteField({ rewrite, disabled, change }: { rewrite: boolean; disabled: boolean; change: (value: boolean) => void }) {
  return <label className="import-rewrite" htmlFor="import-rewrite"><input className="switch" id="import-rewrite" type="checkbox" role="switch"
    checked={rewrite} disabled={disabled} aria-describedby="import-rewrite-help" onChange={event => change(event.currentTarget.checked)} />
    <span>Переписывать текст<small id="import-rewrite-help">{rewrite ? "Модель улучшит формулировки." : "Только оформление."}</small></span></label>;
}
