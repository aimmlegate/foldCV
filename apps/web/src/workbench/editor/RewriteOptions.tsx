import { useEffect, useState } from "react";
import { preferencesRequest, saveRewriteModelRequest, saveRewriteReasoningRequest } from "../../api/client";
import { ConnectionWorkflow, type ConnectionSnapshot } from "../../connection/workflow";
import { isReasoningEffort } from "../../connection/reasoning";
import type { Preferences } from "../../contracts/generated/preferences";
import { errorMessage } from "../../errors/messages";
import { defaultReasoningLabel, reasoningLabels } from "../settings/ReasoningSelect";

type Saved = Pick<Preferences, "selectedRewriteModel" | "rewriteReasoningEffort">;
export type RewriteSettings = { catalog: ConnectionSnapshot | null; saved: Saved | null; saving: boolean; error: string;
  chooseModel: (model: string | null) => void; chooseEffort: (effort: string) => void };

/** The rewrite model and reasoning level are the saved choices Settings also shows: read on every opening, saved on change. */
export function useRewriteSettings(open: boolean): RewriteSettings {
  const [catalog, setCatalog] = useState<ConnectionSnapshot | null>(null), [saved, setSaved] = useState<Saved | null>(null);
  const [saving, setSaving] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let live = true;
    const workflow = new ConnectionWorkflow(view => { if (live) setCatalog(view.snapshot); });
    void workflow.peek();
    void preferencesRequest().then(value => { if (live) { setSaved(value); setError(""); } },
      (failure: unknown) => { if (live) setError(errorMessage(failure)); });
    return () => { live = false; workflow.close(); };
  }, [open]);
  const model = saved?.selectedRewriteModel ?? catalog?.selectedModel ?? null;
  async function save(work: () => Promise<Preferences>) {
    setSaving(true); setError("");
    try { setSaved(await work()); } catch (failure) { setError(errorMessage(failure)); } finally { setSaving(false); }
  }
  return { catalog, saved, saving, error,
    chooseModel: next => void save(() => saveRewriteModelRequest(next)),
    chooseEffort: next => { if (model) void save(() => saveRewriteReasoningRequest(model, isReasoningEffort(next) ? next : null)); } };
}

export function RewriteOptions({ settings, disabled }: { settings: RewriteSettings; disabled: boolean }) {
  const { catalog, saved } = settings, models = catalog?.models ?? [];
  const chosen = saved?.selectedRewriteModel ?? null, model = chosen ?? catalog?.selectedModel ?? null;
  const reasoning = model ? catalog?.modelReasoning?.[model] : undefined, supported = reasoning?.supported ?? [];
  // A saved level this model lacks runs at the model's default, so the default is what is shown.
  const level = saved?.rewriteReasoningEffort, effort = level && supported.includes(level) ? level : null;
  const off = disabled || settings.saving || !saved || !catalog?.metadataReady;
  return <div className="rewrite-options">
    <div><label htmlFor="rewrite-panel-model">Модель</label>
      <select className="model-select" id="rewrite-panel-model" value={chosen ?? ""} disabled={off}
        onChange={event => settings.chooseModel(event.currentTarget.value || null)}>
        <option value="">{catalog?.selectedModel ? `Модель обработки · ${catalog.selectedModel}` : "Модель обработки"}</option>
        {(chosen && !models.includes(chosen) ? [chosen, ...models] : models).map(name =>
          <option key={name} value={name} disabled={!models.includes(name)}>{name}{models.includes(name) ? "" : " · недоступна"}</option>)}
      </select></div>
    <div><label htmlFor="rewrite-panel-effort">Рассуждения</label>
      <select className="model-select" id="rewrite-panel-effort" value={effort ?? ""} disabled={off || !supported.length}
        onChange={event => settings.chooseEffort(event.currentTarget.value)}>
        <option value="">{defaultReasoningLabel(reasoning?.default)}</option>
        {supported.map(value => <option key={value} value={value}>{reasoningLabels[value]}</option>)}
      </select></div>
    {settings.error && <p className="notice error" role="alert">{settings.error}</p>}
  </div>;
}
