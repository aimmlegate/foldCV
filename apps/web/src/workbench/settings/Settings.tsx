import { errorMessage } from "../../errors/messages";
import { useEffect, useState } from "react";
import { ConnectionWorkflow, modelGroups, type ConnectionView } from "../../connection/workflow";
import { assistantSettings, saveAssistantSettings } from "../../assistant/api";
import { preferencesRequest, rulesRequest, saveRulesRequest, saveImportModelRequest, saveFallbackModelRequest, saveLimitsRequest, saveRewriteModelRequest, saveRewriteReasoningRequest } from "../../api/client";
import { SettingsDrafts, limitRanges, type SettingsPart, type SettingsState, type SettingsValues } from "./drafts";
import { Connections } from "./Connection";
import { ModelSelect } from "./ModelSelect";
import { ReasoningSelect } from "./ReasoningSelect";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";
import { type Appearance, type PaneOrder } from "./interface";
import { AppearanceSettings } from "./Appearance";
import { CommandsSettings } from "./Commands";
import { RowState, SettingsGroup, SettingsRow } from "./Rows";
import { settingsSections, type SettingsSection } from "./sections";

const partNames: Record<SettingsPart, string> = { reasoning: "рассуждения при правке", model: "модель обработки", rewrite: "модель правки", import: "модель импорта", fallback: "резервная модель", limits: "лимиты", assistant: "помощник", rules: "команды" };
// The parts that save at once from a row; their state shows on the row of the value that sent them.
const rowBound: readonly SettingsPart[] = ["model", "rewrite", "reasoning", "import", "fallback", "assistant"];
const firstKeys: Partial<Record<SettingsPart, keyof SettingsValues>> = { model: "model", rewrite: "rewriteModel", reasoning: "reasoning",
  import: "importModel", fallback: "fallbackModel", assistant: "agentEnabled" };
const leads: Record<SettingsSection, string> = { connection: "Модели включённых провайдеров доступны во всех списках моделей.",
  models: "Каждый выбор сохраняется сразу.", assistant: "Чат по резюме и по шаблонам. Каждый выбор сохраняется сразу.",
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
  // Choices stay open during a save: a change then waits for it and goes next.
  const modelsOff = current.loading || !current.preferences || view.pending || !view.snapshot.metadataReady;
  const assistantOff = current.loading || !current.assistant || view.pending || !view.snapshot.metadataReady;
  // A part without its base failed to load: that goes to the top; a refused save goes under the row that sent it.
  const loadFailed = (part: SettingsPart) => part === "assistant" ? !current.assistant : part === "rules" ? !current.rules : !current.preferences;
  const at = (part: SettingsPart) => current.focus[part] ?? firstKeys[part];
  const rowParts = (key: keyof SettingsValues) => rowBound.filter(part => at(part) === key);
  const rowState = (key: keyof SettingsValues) => <RowState pending={rowParts(key).some(part => current.pending.includes(part))} at={current.marks[key]} />;
  const rowNote = (key: keyof SettingsValues) => {
    const failed = rowParts(key).filter(part => current.errors[part] && !loadFailed(part));
    return failed.length > 0 && failed.map(part => <p className="settings-row-error" role="alert" key={part}>{errorMessage(current.errors[part])}
      <button type="button" className="text-button" disabled={current.pending.includes(part)} onClick={() => void controller.retry(part)}>Повторить</button></p>);
  };
  const inline = (part: SettingsPart) => (rowBound.includes(part) || part === "rules") && !loadFailed(part);
  const topErrors = Object.entries(current.errors).filter(([part]) => !inline(part as SettingsPart));
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
        {current.saved.some(part => !inline(part)) && <OperationStatus state="success"
          label={`Сохранено: ${current.saved.filter(part => !inline(part)).map(part => partNames[part]).join(", ")}.`} />}
        {current.message && <p className="notice" role="status">{current.message}</p>}
        {topErrors.map(([part, error]) => <p className="notice error" role="alert" key={part}>{partNames[part as SettingsPart]}: {errorMessage(error)}</p>)}
        {!controller.ready && !current.loading && topErrors.length > 0 && <Button className="small" onClick={() => void controller.load()}>Загрузить снова</Button>}
      </div>
      <h2 className="settings-section-title">{shownLabel}</h2>
      {section !== "limits" && <p className="settings-lead">{leads[section]}</p>}
      {section === "connection" && <Connections view={view} workflow={workflow} disabled={current.saving} />}
      {section === "models" && <><SettingsGroup title="Обработка и правка">
        <SettingsRow label="Модель обработки" hint="Импорт и правки, если ниже не выбрано другое." htmlFor="model-select" note={rowNote("model")}>
          {rowState("model")}<ModelSelect id="model-select" label="Модель обработки" labelled={false} value={current.draft.model} groups={groups} disabled={modelsOff}
            change={value => { if (value) void controller.commit("model", value); }} /></SettingsRow>
        <SettingsRow label="Модель правки текста" htmlFor="rewrite-model-select" note={rowNote("rewriteModel")}>
          {rowState("rewriteModel")}<ModelSelect id="rewrite-model-select" label="Модель правки текста" labelled={false} value={current.draft.rewriteModel} groups={groups}
            defaultLabel="Как модель обработки" disabled={modelsOff} change={value => void controller.commit("rewriteModel", value)} /></SettingsRow>
        <SettingsRow label="Рассуждения при правке" htmlFor="rewrite-reasoning" note={rowNote("reasoning")}>
          {rowState("reasoning")}<ReasoningSelect labelled={false} value={current.draft.reasoning} metadata={view.snapshot.modelReasoning?.[current.draft.rewriteModel ?? current.draft.model ?? ""]}
            disabled={modelsOff || !(current.draft.rewriteModel ?? current.draft.model)} change={value => void controller.commit("reasoning", value)} /></SettingsRow>
      </SettingsGroup>
      <SettingsGroup title="Импорт резюме">
        <SettingsRow label="Модель импорта" htmlFor="import-model-select" note={rowNote("importModel")}>
          {rowState("importModel")}<ModelSelect id="import-model-select" label="Модель импорта" labelled={false} value={current.draft.importModel} groups={groups}
            defaultLabel="Как модель обработки" disabled={modelsOff} change={value => void controller.commit("importModel", value)} /></SettingsRow>
        <SettingsRow label="Резервная модель" hint="Повторит блок, если основная модель не справится." htmlFor="fallback-model-select" note={rowNote("fallbackModel")}>
          {rowState("fallbackModel")}<ModelSelect id="fallback-model-select" label="Резервная модель" labelled={false} value={current.draft.fallbackModel} groups={groups}
            defaultLabel="Нет" disabled={modelsOff} change={value => void controller.commit("fallbackModel", value)} /></SettingsRow>
      </SettingsGroup></>}
      {section === "assistant" && <SettingsGroup>
        <SettingsRow label="Включить помощника" htmlFor="assistant-enabled" note={rowNote("agentEnabled")}>
          {rowState("agentEnabled")}<input className="switch" id="assistant-enabled" role="switch" type="checkbox" checked={current.draft.agentEnabled} disabled={!current.assistant || current.loading}
            onChange={event => void controller.commit("agentEnabled", event.currentTarget.checked)} /></SettingsRow>
        <SettingsRow label="Модель помощника" htmlFor="assistant-model-select" note={rowNote("agentModel")}>
          {rowState("agentModel")}<ModelSelect id="assistant-model-select" label="Модель помощника" labelled={false} value={current.draft.agentModel} groups={groups}
            defaultLabel="Выберите модель" disabled={assistantOff} change={value => void controller.commit("agentModel", value)} /></SettingsRow>
        <SettingsRow label="Рассуждения помощника" htmlFor="assistant-reasoning" note={rowNote("agentEffort")}>
          {rowState("agentEffort")}<ReasoningSelect id="assistant-reasoning" label="Рассуждения помощника" labelled={false} value={current.draft.agentEffort}
            metadata={view.snapshot.modelReasoning?.[current.draft.agentModel ?? ""]} disabled={assistantOff || !current.draft.agentModel}
            change={value => void controller.commit("agentEffort", value)} /></SettingsRow>
      </SettingsGroup>}
      {section === "rules" && <CommandsSettings state={current} controller={controller} />}
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
