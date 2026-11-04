import { errorMessage } from "../../errors/messages";
import { useEffect, useState } from "react";
import { ConnectionWorkflow, modelGroups, type ConnectionView } from "../../connection/workflow";
import { assistantSettings, saveAssistantSettings } from "../../assistant/api";
import { preferencesRequest, rulesRequest, saveRulesRequest, saveImportModelRequest, saveFallbackModelRequest, saveLimitsRequest, saveRewriteModelRequest, saveRewriteReasoningRequest } from "../../api/client";
import { SettingsDrafts, limitRanges, type SettingsPart, type SettingsState } from "./drafts";
import { Connections } from "./Connection";
import { ModelSelect } from "./ModelSelect";
import { ReasoningSelect } from "./ReasoningSelect";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";
import { type Appearance, type PaneOrder } from "./interface";
import { AppearanceSettings } from "./Appearance";
import { SettingsGroup, SettingsRow, settingsSections, type SettingsSection } from "./Rows";

const partNames: Record<SettingsPart, string> = { reasoning: "рассуждения при правке", model: "модель обработки", rewrite: "модель правки", import: "модель импорта", fallback: "резервная модель", limits: "лимиты", assistant: "помощник", rules: "команды" };
const leads: Record<SettingsSection, string> = { connection: "Модели включённых провайдеров доступны во всех списках моделей.",
  models: "Какая модель импортирует резюме и правит текст.", assistant: "Чат по резюме и по шаблонам.",
  rules: "Тексты команд «Сократить» и «Сделать яснее» в правке текста.", appearance: "Сохраняется сразу. Страница резюме остаётся светлой при любой теме." };

/** Settings (D147): five sections in a column of at most 720 px; each section is groups of rows. `request` opens a
 * section from elsewhere, for example the assistant's link to its model. */
export function Settings({ open, request = null, connectionChanged, paneOrder, changePaneOrder, appearance, changeAppearance }: { open: boolean;
  request?: { section: SettingsSection; at: number } | null;
  connectionChanged: (view: ConnectionView) => void; paneOrder: PaneOrder; changePaneOrder: (order: PaneOrder) => void;
  appearance: Appearance; changeAppearance: (value: Appearance) => void }) {
  // Limits keep their code and values without a nav item (backlog item 10).
  const [section, setSection] = useState<SettingsSection | "limits">("connection");
  useEffect(() => { if (request) setSection(request.section); }, [request]);
  const [view, setView] = useState<ConnectionView>(() => new ConnectionWorkflow(() => {}).view);
  const [workflow] = useState(() => new ConnectionWorkflow(value => { setView(value); connectionChanged(value); }));
  const [state, setState] = useState<SettingsState | null>(null);
  const [controller] = useState(() => {
    return new SettingsDrafts({ preferences: preferencesRequest, rules: rulesRequest, assistant: () => assistantSettings(),
      saveRules: saveRulesRequest, saveAssistant: value => saveAssistantSettings(value),
      selectRewrite: saveRewriteModelRequest, selectImport: saveImportModelRequest, selectFallback: saveFallbackModelRequest, saveReasoning: saveRewriteReasoningRequest, saveLimits: saveLimitsRequest,
      select: async model => {
        if (!model || !workflow.view.snapshot.metadataReady || !workflow.view.snapshot.models.includes(model)) throw new Error("MODEL_UNAVAILABLE");
        if (!await workflow.select(model)) throw new Error("MODEL_SAVE_FAILED");
        return model;
      } }, setState);
  });
  useEffect(() => { void controller.load(); return () => { controller.close(); workflow.close(); }; }, [controller, workflow]);
  // Settings stays mounted behind the editor, whose rewrite popover and assistant panel save the same choices, and a
  // connection check can end while it is away.
  useEffect(() => { if (open) { void controller.refreshPreferences(); void controller.refreshAssistant(); void workflow.peek().then(() => workflow.checkReleases()); } }, [open, controller, workflow]);
  const current = state ?? controller.state, dirty = controller.dirty.length > 0, busy = current.loading || current.saving;
  const groups = modelGroups(view.snapshot);
  const modelsOff = busy || !current.preferences || view.pending || !view.snapshot.metadataReady;
  const assistantOff = busy || !current.assistant || view.pending || !view.snapshot.metadataReady;
  const draftActions = <>{!controller.ready && !current.loading && <Button className="small" onClick={() => void controller.load()}>Загрузить снова</Button>}
    <div className="settings-actions"><Button variant="primary" busy={current.saving} busyLabel="Сохраняем…" disabled={!dirty || current.loading || view.pending} onClick={() => void controller.save()}>Сохранить</Button>
      <Button variant="quiet" disabled={!dirty || busy} onClick={() => controller.cancel()}>Отмена</Button>
      <span className="settings-saved" role="status">{current.saving ? "" : dirty ? "Не сохранено" : current.staleRules ? "Команды изменились, загрузите их заново" : controller.ready ? "" : "Часть настроек не загрузилась"}</span>
    </div></>;
  const shownLabel = section === "limits" ? "Лимиты" : settingsSections.find(item => item.id === section)?.label ?? "";
  return <section className="settings-screen" aria-label="Настройки">
    <div className="settings-layout"><nav className="settings-nav" aria-label="Разделы настроек">
      {settingsSections.map(item => <button key={item.id} data-settings={item.id} className={section === item.id ? "active" : ""}
        aria-current={section === item.id ? "page" : undefined} onClick={() => setSection(item.id)}>{item.label}</button>)}
    </nav><div className="settings-content">
      <div className="settings-feedback">
        {current.loading && <OperationStatus label="Загружаем настройки" timed />}
        {current.saved.length > 0 && <OperationStatus state="success" label={`Сохранено: ${current.saved.map(part => partNames[part]).join(", ")}.`} />}
        {current.message && <p className="notice" role="status">{current.message}</p>}
        {Object.entries(current.errors).map(([part, error]) => <p className="notice error" role="alert" key={part}>{partNames[part as SettingsPart]}: {errorMessage(error)}</p>)}
      </div>
      <h2 className="settings-section-title">{shownLabel}</h2>
      {section !== "limits" && <p className="settings-lead">{leads[section]}</p>}
      {section === "connection" && <Connections view={view} workflow={workflow} disabled={current.saving} />}
      {section === "models" && <><SettingsGroup title="Обработка и правка">
        <SettingsRow label="Модель обработки" hint="Импорт и правки, если ниже не выбрано другое." htmlFor="model-select">
          <ModelSelect id="model-select" label="Модель обработки" labelled={false} value={current.draft.model} groups={groups} disabled={modelsOff}
            change={value => { if (value) controller.change("model", value); }} /></SettingsRow>
        <SettingsRow label="Модель правки текста" htmlFor="rewrite-model-select">
          <ModelSelect id="rewrite-model-select" label="Модель правки текста" labelled={false} value={current.draft.rewriteModel} groups={groups}
            defaultLabel="Как модель обработки" disabled={modelsOff} change={value => controller.change("rewriteModel", value)} /></SettingsRow>
        <SettingsRow label="Рассуждения при правке" htmlFor="rewrite-reasoning">
          <ReasoningSelect labelled={false} value={current.draft.reasoning} metadata={view.snapshot.modelReasoning?.[current.draft.rewriteModel ?? current.draft.model ?? ""]}
            disabled={modelsOff || !(current.draft.rewriteModel ?? current.draft.model)} change={value => controller.change("reasoning", value)} /></SettingsRow>
      </SettingsGroup>
      <SettingsGroup title="Импорт резюме">
        <SettingsRow label="Модель импорта" htmlFor="import-model-select">
          <ModelSelect id="import-model-select" label="Модель импорта" labelled={false} value={current.draft.importModel} groups={groups}
            defaultLabel="Как модель обработки" disabled={modelsOff} change={value => controller.change("importModel", value)} /></SettingsRow>
        <SettingsRow label="Резервная модель" hint="Повторит блок, если основная модель не справится." htmlFor="fallback-model-select">
          <ModelSelect id="fallback-model-select" label="Резервная модель" labelled={false} value={current.draft.fallbackModel} groups={groups}
            defaultLabel="Нет" disabled={modelsOff} change={value => controller.change("fallbackModel", value)} /></SettingsRow>
      </SettingsGroup>{draftActions}</>}
      {section === "assistant" && <><SettingsGroup>
        <SettingsRow label="Включить помощника" htmlFor="assistant-enabled">
          <input className="switch" id="assistant-enabled" role="switch" type="checkbox" checked={current.draft.agentEnabled} disabled={!current.assistant}
            onChange={event => controller.change("agentEnabled", event.currentTarget.checked)} /></SettingsRow>
        <SettingsRow label="Модель помощника" htmlFor="assistant-model-select">
          <ModelSelect id="assistant-model-select" label="Модель помощника" labelled={false} value={current.draft.agentModel} groups={groups}
            defaultLabel="Выберите модель" disabled={assistantOff} change={value => controller.change("agentModel", value)} /></SettingsRow>
        <SettingsRow label="Рассуждения помощника" htmlFor="assistant-reasoning">
          <ReasoningSelect id="assistant-reasoning" label="Рассуждения помощника" labelled={false} value={current.draft.agentEffort}
            metadata={view.snapshot.modelReasoning?.[current.draft.agentModel ?? ""]} disabled={assistantOff || !current.draft.agentModel}
            change={value => controller.change("agentEffort", value)} /></SettingsRow>
      </SettingsGroup>
        {current.errors.assistant && current.assistant && <button className="text-button" disabled={busy} onClick={() => void controller.reloadAssistant()}>Загрузить снова</button>}
        {draftActions}</>}
      {section === "rules" && <>
        <p className="small muted">Пишите инструкции под заголовками <code>## Preset: shorten</code> и <code>## Preset: clarify</code>; остальной текст не используется.</p>
        <label htmlFor="rules-text">Инструкции (Markdown)</label><textarea className="rules-text" id="rules-text" aria-label="Инструкции команд" spellCheck={false}
          disabled={!current.rules} value={current.draft.markdown} onChange={event => controller.change("markdown", event.currentTarget.value)} />
        {current.rules && <><p className="small muted">Версия {current.rules.revision}</p><button className="text-button" disabled={busy} onClick={() => void controller.reloadRules()}>Загрузить сохранённую версию</button></>}
        {current.comparison && current.rules && <><label htmlFor="rules-comparison">Сохранённая версия</label>
          <textarea className="rules-text" id="rules-comparison" aria-label="Сохранённая версия команд" readOnly value={current.rules.markdown} /></>}
        {draftActions}
      </>}
      {section === "limits" && <><p>Время действует со следующего импорта.</p>
        <label htmlFor="limit-import-minutes">Время на импорт резюме, минут</label>
        <input className="limit-input" id="limit-import-minutes" type="number" inputMode="numeric" step={1} min={limitRanges.importMinutes.minimum} max={limitRanges.importMinutes.maximum}
          disabled={!current.preferences || current.saving} value={current.draft.importMinutes} onChange={event => controller.change("importMinutes", event.currentTarget.value)} />
        <p className="small muted">От {limitRanges.importMinutes.minimum} до {limitRanges.importMinutes.maximum} минут.</p>
        <label htmlFor="limit-project-megabytes">Размер проекта, МБ</label>
        <input className="limit-input" id="limit-project-megabytes" type="number" inputMode="numeric" step={1} min={limitRanges.projectMegabytes.minimum} max={limitRanges.projectMegabytes.maximum}
          disabled={!current.preferences || current.saving} value={current.draft.projectMegabytes} onChange={event => controller.change("projectMegabytes", event.currentTarget.value)} />
        <p className="small muted">От {limitRanges.projectMegabytes.minimum} до {limitRanges.projectMegabytes.maximum} МБ.</p>
        {draftActions}
      </>}
      {section === "appearance" && <AppearanceSettings value={appearance} change={changeAppearance} paneOrder={paneOrder} changePaneOrder={changePaneOrder} />}
    </div></div>
  </section>;
}
