import { useEffect, useState } from "react";
import { ConnectionWorkflow, type ConnectionView } from "../../connection/workflow";
import { AgentBrowserApi } from "../../assistant/api";
import { preferencesRequest, rulesRequest, saveRulesRequest } from "../../next/api";
import { SettingsDrafts, type SettingsPart, type SettingsState } from "./drafts";
import { Connection } from "./Connection";
import { Button } from "../ui/Button";

const partNames: Record<SettingsPart, string> = { model: "модель обработки", analysis: "проверка изменений", assistant: "помощник", rules: "правила" };
export function Settings({ close, connectionChanged }: { close: () => void; connectionChanged: (view: ConnectionView) => void }) {
  const [section, setSection] = useState<"model" | "rules" | "analysis">("model");
  const [view, setView] = useState<ConnectionView>(() => new ConnectionWorkflow(() => {}).view);
  const [workflow] = useState(() => new ConnectionWorkflow(value => { setView(value); connectionChanged(value); }));
  const [state, setState] = useState<SettingsState | null>(null);
  const [controller] = useState(() => {
    const api = new AgentBrowserApi("");
    return new SettingsDrafts({ preferences: () => preferencesRequest(), rules: rulesRequest, assistant: () => api.settings(),
      analysis: enabled => preferencesRequest(enabled), saveRules: saveRulesRequest, saveAssistant: value => api.saveSettings(value),
      select: async model => {
        if (!model || !workflow.view.snapshot.metadataReady || !workflow.view.snapshot.models.includes(model)) throw new Error("MODEL_UNAVAILABLE");
        await workflow.select(model);
        if (workflow.view.error || workflow.view.snapshot.selectedModel !== model) throw new Error("MODEL_SAVE_FAILED");
        return model;
      } }, setState);
  });
  useEffect(() => { void controller.load(); void workflow.peek(); return () => { controller.close(); workflow.close(); }; }, [controller, workflow]);
  const current = state ?? controller.state, dirty = controller.dirty.length > 0, busy = current.loading || current.saving;
  const agentChoices = current.draft.agentModel && !view.snapshot.models.includes(current.draft.agentModel)
    ? [current.draft.agentModel, ...view.snapshot.models] : view.snapshot.models;
  return <section className="settings-screen" aria-label="Настройки">
    <div className="settings-title"><button className="text-button" disabled={current.saving} onClick={close}>← Вернуться к резюме</button></div>
    <div className="settings-layout"><nav className="settings-nav" aria-label="Разделы настроек">
      {(["model", "rules", "analysis"] as const).map(value => <button key={value} data-settings={value} className={section === value ? "active" : ""}
        aria-current={section === value ? "page" : undefined} onClick={() => setSection(value)}>
        {value === "model" ? "Модель и подключение" : value === "rules" ? "Общие правила и команды" : "Проверка изменений"}
      </button>)}
    </nav><div className="settings-content">
      {section === "model" && <><Connection view={view} workflow={workflow} model={current.draft.model} change={value => controller.change("model", value)} disabled={current.saving} selectionDisabled={!current.preferences} />
        <div className="uir-assistant-options"><h3>Помощник</h3><div className="switch-line"><label htmlFor="assistant-enabled">Включить помощника<small>Использует это же подключение. Открытие панели не включает помощника.</small></label>
          <input className="switch" id="assistant-enabled" aria-label="Включить помощника" role="switch" type="checkbox" checked={current.draft.agentEnabled} disabled={!current.assistant}
            onChange={event => controller.change("agentEnabled", event.currentTarget.checked)} /></div>
          <label htmlFor="assistant-model-select">Модель помощника</label><select className="model-select" id="assistant-model-select" aria-label="Модель помощника"
            value={current.draft.agentModel ?? ""} disabled={!current.assistant || !view.snapshot.metadataReady} onChange={event => controller.change("agentModel", event.currentTarget.value || null)}>
            <option value="">Выберите модель помощника</option>{agentChoices.map(model => <option key={model} value={model} disabled={!view.snapshot.models.includes(model)}>{model}{!view.snapshot.models.includes(model) ? " · недоступна" : ""}</option>)}
          </select><p className="settings-disclosure">Модель обработки и модель помощника сохраняются отдельно.</p>
          {current.errors.assistant && current.assistant && <button className="text-button" disabled={busy} onClick={() => void controller.reloadAssistant()}>Загрузить настройки помощника</button>}
        </div></>}
      {section === "rules" && <><h3>Общие правила и команды</h3><p>Эти правила действуют для всех резюме и применяются при следующей обработке текста.</p>
        <label htmlFor="rules-text">Правила в Markdown</label><textarea className="rules-text" id="rules-text" aria-label="Markdown правил" spellCheck={false}
          disabled={!current.rules} value={current.draft.markdown} onChange={event => controller.change("markdown", event.currentTarget.value)} />
        <p className="small muted">Сохраните оба заголовка: <code>## Preset: shorten</code> и <code>## Preset: clarify</code> с инструкциями под ними.</p>
        {current.rules && <><p className="small muted">Версия правил: {current.rules.revision}</p><button className="text-button" disabled={busy} onClick={() => void controller.reloadRules()}>Загрузить актуальную версию правил</button></>}
        {current.comparison && current.rules && <><label htmlFor="rules-comparison">Сохранённая версия для сравнения</label>
          <textarea className="rules-text" id="rules-comparison" aria-label="Сохранённая версия правил" readOnly value={current.rules.markdown} /></>}
      </>}
      {section === "analysis" && <><h3>Проверка изменений</h3><p>Проверять факты и даты после редактирования.</p>
        <div className="switch-line"><label htmlFor="analysis-toggle">Автоматически проверять изменения<small>Другие упоминания меняются только с вашего согласия.</small></label>
          <input className="switch" id="analysis-toggle" aria-label="Автоматически проверять изменения" type="checkbox" role="switch" disabled={!current.preferences} checked={current.draft.automatic}
            onChange={event => controller.change("automatic", event.currentTarget.checked)} /></div>
        <p className="settings-disclosure">Параллельные периоды работы допустимы. Подсказки не блокируют редактирование, сохранение или экспорт.</p>
      </>}
      {current.loading && <p className="notice" role="status">Загружаем настройки…</p>}
      {!controller.ready && !current.loading && <Button className="small" onClick={() => void controller.load()}>Повторить загрузку настроек</Button>}
      {current.saved.length > 0 && <p className="notice" role="status">Сохранено: {current.saved.map(part => partNames[part]).join(", ")}.{dirty && " Остальные черновики остаются в форме."}</p>}
      {current.message && <p className="notice" role="status">{current.message}</p>}
      {Object.entries(current.errors).map(([part, error]) => <p className="notice error" role="alert" key={part}>{partNames[part as SettingsPart]}: {error}</p>)}
      <div className="settings-actions"><Button variant="primary" disabled={!dirty || busy || view.pending} onClick={() => void controller.save()}>Сохранить изменения</Button>
        <Button variant="quiet" disabled={!dirty || busy} onClick={() => controller.cancel()}>Отмена</Button>
        <span className="settings-saved" role="status">{current.saving ? "Сохраняем по разделам…" : dirty ? "Есть несохранённые изменения" : current.staleRules ? "Нужно обновить правила" : controller.ready ? "Изменения сохранены" : "Не все настройки доступны"}</span>
      </div>
    </div></div>
  </section>;
}
