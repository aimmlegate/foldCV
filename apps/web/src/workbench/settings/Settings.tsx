import { errorMessage } from "../../errors/messages";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { ConnectionWorkflow, modelGroups, type ConnectionView } from "../../connection/workflow";
import { assistantSettings, saveAssistantSettings } from "../../assistant/api";
import { preferencesRequest, rulesRequest, saveRulesRequest, saveImportModelRequest, saveFallbackModelRequest, saveLimitsRequest, saveRewriteModelRequest, saveRewriteReasoningRequest } from "../../api/client";
import { SettingsDrafts, limitRanges, type SettingsPart, type SettingsState } from "./drafts";
import { Connections } from "./Connection";
import { ModelSelect } from "./ModelSelect";
import { ReasoningSelect } from "./ReasoningSelect";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";
import type { PaneOrder } from "./interface";
import { Dialog } from "../ui/Dialog";

// Loaded on first visit: the YAML parser and Monaco stay out of the startup bundle.
const TemplateSettings = lazy(() => import("./template/TemplateSettings"));
const partNames: Record<SettingsPart, string> = { reasoning: "рассуждения при правке", model: "модель обработки", rewrite: "модель правки", import: "модель импорта", fallback: "резервная модель", limits: "лимиты", assistant: "помощник", rules: "команды" };
export function Settings({ open, close, connectionChanged, paneOrder, changePaneOrder }: { open: boolean; close: () => void; connectionChanged: (view: ConnectionView) => void; paneOrder: PaneOrder; changePaneOrder: (order: PaneOrder) => void }) {
  const [section, setSection] = useState<"model" | "rules" | "limits" | "interface">("model");
  // The template editor stays mounted after its first visit so switching sections keeps unsaved YAML.
  const [templateOpened, setTemplateOpened] = useState(false), [templateDirty, setTemplateDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const templateDirtyChange = useCallback((dirty: boolean) => setTemplateDirty(dirty), []);
  const leave = () => { if (templateDirty) setConfirmClose(true); else close(); };
  const [view, setView] = useState<ConnectionView>(() => new ConnectionWorkflow(() => {}).view);
  const [workflow] = useState(() => new ConnectionWorkflow(value => { setView(value); connectionChanged(value); }));
  const [state, setState] = useState<SettingsState | null>(null);
  const [controller] = useState(() => {
    return new SettingsDrafts({ preferences: preferencesRequest, rules: rulesRequest, assistant: () => assistantSettings(),
      saveRules: saveRulesRequest, saveAssistant: value => saveAssistantSettings(value),
      selectRewrite: saveRewriteModelRequest, selectImport: saveImportModelRequest, selectFallback: saveFallbackModelRequest, saveReasoning: saveRewriteReasoningRequest, saveLimits: saveLimitsRequest,
      select: async model => {
        if (!model || !workflow.view.snapshot.metadataReady || !workflow.view.snapshot.models.includes(model)) throw new Error("MODEL_UNAVAILABLE");
        await workflow.select(model);
        if (workflow.view.error || workflow.view.snapshot.selectedModel !== model) throw new Error("MODEL_SAVE_FAILED");
        return model;
      } }, setState);
  });
  useEffect(() => { void controller.load(); void workflow.peek(); return () => { controller.close(); workflow.close(); }; }, [controller, workflow]);
  // Settings stays mounted behind the editor, whose rewrite popover saves the same rewrite choices.
  useEffect(() => { if (open) void controller.refreshPreferences(); }, [open, controller]);
  const current = state ?? controller.state, dirty = controller.dirty.length > 0, busy = current.loading || current.saving;
  const groups = modelGroups(view.snapshot);
  const draftActions = <>{!controller.ready && !current.loading && <Button className="small" onClick={() => void controller.load()}>Загрузить снова</Button>}
    <div className="settings-actions"><Button variant="primary" busy={current.saving} busyLabel="Сохраняем…" disabled={!dirty || current.loading || view.pending} onClick={() => void controller.save()}>Сохранить</Button>
      <Button variant="quiet" disabled={!dirty || busy} onClick={() => controller.cancel()}>Отмена</Button>
      <span className="settings-saved" role="status">{current.saving ? "" : dirty ? "Не сохранено" : current.staleRules ? "Команды изменились, загрузите их заново" : controller.ready ? "" : "Часть настроек не загрузилась"}</span>
    </div></>;
  return <section className="settings-screen" aria-label="Настройки">
    <div className="settings-title"><button className="text-button" disabled={current.saving} onClick={leave}>← К резюме</button></div>
    <div className="settings-layout"><nav className="settings-nav" aria-label="Разделы настроек">
      {/* Limits have no menu item; their saved or default values still apply. */}
      {(["model", "rules", "interface"] as const).map(value => <button key={value} data-settings={value} className={section === value ? "active" : ""}
        aria-current={section === value ? "page" : undefined} onClick={() => { setSection(value); if (value === "rules") setTemplateOpened(true); }}>
        {value === "model" ? "Модель и подключение" : value === "rules" ? "Правила и шаблон" : "Интерфейс"}
      </button>)}
    </nav><div className="settings-content">
      <div className="settings-feedback">
        {current.loading && <OperationStatus label="Загружаем настройки" timed />}
        {current.saved.length > 0 && <OperationStatus state="success" label={`Сохранено: ${current.saved.map(part => partNames[part]).join(", ")}.`} />}
        {current.message && <p className="notice" role="status">{current.message}</p>}
        {Object.entries(current.errors).map(([part, error]) => <p className="notice error" role="alert" key={part}>{partNames[part as SettingsPart]}: {errorMessage(error)}</p>)}
      </div>
      {section === "model" && <><Connections view={view} workflow={workflow} disabled={current.saving} />
        <div className="uir-assistant-options"><h3>Обработка и правка текста</h3>
        <ModelSelect id="model-select" label="Модель обработки" value={current.draft.model} groups={groups}
          disabled={busy || !current.preferences || view.pending || !view.snapshot.metadataReady}
          change={value => { if (value) controller.change("model", value); }} />
        <ModelSelect id="rewrite-model-select" label="Модель правки текста" value={current.draft.rewriteModel} groups={groups}
          defaultLabel="Как модель обработки" disabled={busy || !current.preferences || view.pending || !view.snapshot.metadataReady}
          change={value => controller.change("rewriteModel", value)} />
        <ReasoningSelect value={current.draft.reasoning} metadata={view.snapshot.modelReasoning?.[current.draft.rewriteModel ?? current.draft.model ?? ""]}
          disabled={busy || !current.preferences || view.pending || !view.snapshot.metadataReady || !(current.draft.rewriteModel ?? current.draft.model)}
          change={value => controller.change("reasoning", value)} /></div>
        <div className="uir-assistant-options"><h3>Импорт резюме</h3>
          <ModelSelect id="import-model-select" label="Модель импорта" value={current.draft.importModel} groups={groups}
            defaultLabel="Как модель обработки" disabled={busy || !current.preferences || view.pending || !view.snapshot.metadataReady}
            change={value => controller.change("importModel", value)} />
          <ModelSelect id="fallback-model-select" label="Резервная модель" value={current.draft.fallbackModel} groups={groups}
            defaultLabel="Нет" disabled={busy || !current.preferences || view.pending || !view.snapshot.metadataReady}
            change={value => controller.change("fallbackModel", value)} />
          <p className="small muted">Повторит блок, если основная модель не справится.</p>
        </div>
        <div className="uir-assistant-options"><h3>Помощник</h3><div className="switch-line"><label htmlFor="assistant-enabled">Включить помощника</label>
          <input className="switch" id="assistant-enabled" aria-label="Включить помощника" role="switch" type="checkbox" checked={current.draft.agentEnabled} disabled={!current.assistant}
            onChange={event => controller.change("agentEnabled", event.currentTarget.checked)} /></div>
          <ModelSelect id="assistant-model-select" label="Модель помощника" value={current.draft.agentModel} groups={groups}
            defaultLabel="Выберите модель" disabled={busy || !current.assistant || view.pending || !view.snapshot.metadataReady}
            change={value => controller.change("agentModel", value)} />
          <ReasoningSelect id="assistant-reasoning" label="Рассуждения помощника" value={current.draft.agentEffort}
            metadata={view.snapshot.modelReasoning?.[current.draft.agentModel ?? ""]}
            disabled={busy || !current.assistant || view.pending || !view.snapshot.metadataReady || !current.draft.agentModel}
            change={value => controller.change("agentEffort", value)} />
          {current.errors.assistant && current.assistant && <button className="text-button" disabled={busy} onClick={() => void controller.reloadAssistant()}>Загрузить снова</button>}
        </div></>}
      {section === "rules" && <><h3>Команды «Сократить» и «Сделать яснее»</h3>
        <p className="small muted">Пишите инструкции под заголовками <code>## Preset: shorten</code> и <code>## Preset: clarify</code>; остальной текст не используется.</p>
        <label htmlFor="rules-text">Инструкции (Markdown)</label><textarea className="rules-text" id="rules-text" aria-label="Инструкции команд" spellCheck={false}
          disabled={!current.rules} value={current.draft.markdown} onChange={event => controller.change("markdown", event.currentTarget.value)} />
        {current.rules && <><p className="small muted">Версия {current.rules.revision}</p><button className="text-button" disabled={busy} onClick={() => void controller.reloadRules()}>Загрузить сохранённую версию</button></>}
        {current.comparison && current.rules && <><label htmlFor="rules-comparison">Сохранённая версия</label>
          <textarea className="rules-text" id="rules-comparison" aria-label="Сохранённая версия команд" readOnly value={current.rules.markdown} /></>}
        {draftActions}
      </>}
      {section === "limits" && <><h3>Лимиты</h3>
        <p>Время действует со следующего импорта.</p>
        <label htmlFor="limit-import-minutes">Время на импорт резюме, минут</label>
        <input className="limit-input" id="limit-import-minutes" type="number" inputMode="numeric" step={1} min={limitRanges.importMinutes.minimum} max={limitRanges.importMinutes.maximum}
          disabled={!current.preferences || current.saving} value={current.draft.importMinutes} onChange={event => controller.change("importMinutes", event.currentTarget.value)} />
        <p className="small muted">От {limitRanges.importMinutes.minimum} до {limitRanges.importMinutes.maximum} минут.</p>
        <label htmlFor="limit-project-megabytes">Размер проекта, МБ</label>
        <input className="limit-input" id="limit-project-megabytes" type="number" inputMode="numeric" step={1} min={limitRanges.projectMegabytes.minimum} max={limitRanges.projectMegabytes.maximum}
          disabled={!current.preferences || current.saving} value={current.draft.projectMegabytes} onChange={event => controller.change("projectMegabytes", event.currentTarget.value)} />
        <p className="small muted">От {limitRanges.projectMegabytes.minimum} до {limitRanges.projectMegabytes.maximum} МБ.</p>
      </>}
      {section === "interface" && <><h3>Расположение резюме</h3>
        <label htmlFor="workspace-pane-order">Порядок панелей при сравнении</label>
        <select id="workspace-pane-order" value={paneOrder} onChange={event => changePaneOrder(event.currentTarget.value === "original-first" ? "original-first" : "layout-first")}>
          <option value="layout-first">Макет слева, оригинал справа</option>
          <option value="original-first">Оригинал слева, макет справа</option>
        </select><p>Сохраняется сразу.</p>
      </>}
      {(section === "model" || section === "limits") && draftActions}
      {templateOpened && <div className="uir-assistant-options" hidden={section !== "rules"}><Suspense fallback={<OperationStatus label="Загружаем шаблон" />}><TemplateSettings dirtyChange={templateDirtyChange} /></Suspense></div>}
    </div></div>
    <Dialog open={confirmClose} close={() => setConfirmClose(false)} title="Выйти без сохранения?">
      <p className="dialog-copy">Правки шаблона пропадут.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmClose(false)}>Остаться</Button>
        <Button variant="danger" onClick={() => { setConfirmClose(false); close(); }}>Выйти</Button></div>
    </Dialog>
  </section>;
}
