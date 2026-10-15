import { useEffect, useMemo, useState } from "react";
import type { AgentSettings } from "../contracts/generated/agent_settings";
import { AgentApiFailure, AgentBrowserApi } from "./api";
import { errorText } from "./presentation";
import { ModelChoice } from "./ModelChoice";

export function AssistantSettings({ models }: { models: readonly string[] }) {
  const api = useMemo(() => new AgentBrowserApi(""), []);
  const [settings, setSettings] = useState<AgentSettings | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  useEffect(() => { let live = true; void api.settings().then(value => { if (live) setSettings(value); }).catch(() => { if (live) setError("REQUEST_FAILED"); }); return () => { live = false; }; }, [api]);
  async function save(enabled: boolean, model: string | null) {
    if (!settings || busy) return;
    setBusy(true); setError(null);
    try { setSettings(await api.saveSettings({ expectedRevision: settings.revision, enabled, selectedAgentModel: model })); }
    catch (error) { setError(error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED"); setSettings(await api.settings().catch(() => null)); }
    finally { setBusy(false); }
  }
  return <div className="assistant-settings"><h3>Помощник</h3>
    <label><input type="checkbox" checked={settings?.enabled ?? false} disabled={!settings || busy}
      onChange={event => void save(event.target.checked, settings?.selectedAgentModel ?? null)} /> Включить помощника</label>
    <ModelChoice selected={settings?.selectedAgentModel ?? null} models={models} disabled={!settings || busy}
      change={model => void save(settings?.enabled ?? false, model)} />
    <p>Использует это же подключение. Выбор модели обработки и модели помощника сохраняется отдельно.</p>
    {error && <p role="alert" className="text-danger">{errorText(error)}</p>}
  </div>;
}
