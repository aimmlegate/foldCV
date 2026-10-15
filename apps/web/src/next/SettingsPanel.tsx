import { useEffect, useRef, useState, type ReactNode } from "react";
import { ConnectionWorkflow, type ConnectionState, type ConnectionView } from "../connection/workflow";
import type { Preferences } from "../contracts/generated/preferences";
import { preferencesRequest } from "./api";
import { RulesPanel } from "./RulesPanel";

const messages: Record<ConnectionState, string> = {
  unchecked: "Подключение ещё не проверено.", detached: "Модель отключена от FoldCV. Вход в CLI остаётся в силе.",
  cli_missing: "Codex CLI не найден. Установите его и перезапустите приложение.",
  launcher_unsupported: "Для запуска этого CLI нужен Node. Установите Node и перезапустите приложение.",
  unsupported_version: "Эта версия CLI не поддерживается в выбранном режиме.",
  login_required: "Нужен вход с подпиской ChatGPT в выделенном профиле CLI.",
  api_key_mode: "Обнаружен вход по API-ключу. Для этого приложения нужна подписка ChatGPT.",
  metadata_failed: "Не удалось получить сведения об аккаунте и моделях. Повторите проверку.",
  quota_exhausted: "Лимит подписки исчерпан. Дождитесь его сброса.",
  unknown_limits: "Модели доступны в списке, но сведения о лимите не получены.",
  connected: "Вход с подпиской и список моделей доступны.", login_pending: "Завершите вход в окне, открытом CLI.",
  login_failed: "Вход не завершён. Повторите, когда будете готовы.",
  cleanup_blocked: "Не удалось подтвердить остановку процесса. Проверьте CLI и перезапустите приложение.",
};

type SettingsSection = "model" | "rules" | "analysis" | "appearance";
export function SettingsPanel({ close, analysisChanged, appearance, assistant }: { close: () => void; analysisChanged: (enabled: boolean) => void; appearance?: ReactNode;
  assistant?: (models: readonly string[]) => ReactNode }) {
  const [section, setSection] = useState<SettingsSection>("model");
  const [view, setView] = useState<ConnectionView>(() => new ConnectionWorkflow(() => {}).view);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [preferenceError, setPreferenceError] = useState(false);
  const [savingAnalysis, setSavingAnalysis] = useState(false);
  const workflowRef = useRef<ConnectionWorkflow | null>(null);
  if (!workflowRef.current) workflowRef.current = new ConnectionWorkflow(setView);
  const workflow = workflowRef.current, snapshot = view.snapshot;
  async function readPreferences() {
    try { setPreferences(await preferencesRequest());setPreferenceError(false); }
    catch { setPreferenceError(true); }
  }
  async function changeAnalysis(enabled: boolean) {
    setSavingAnalysis(true);
    try {
      const saved = await preferencesRequest(enabled);
      setPreferences(saved);setPreferenceError(false);analysisChanged(saved.automaticAnalysis);
    } catch { setPreferenceError(true); }
    finally { setSavingAnalysis(false); }
  }
  useEffect(() => {
    void workflow.peek();void readPreferences();
    return () => workflow.close();
  }, [workflow]);
  return <section className="next-settings" aria-label="Настройки">
    <button onClick={close}>Вернуться</button><h1>Настройки</h1>
    <div className="next-settings-layout">
    <nav className="next-settings-nav" aria-label="Разделы настроек">
      <button aria-current={section === "model" ? "page" : undefined} onClick={() => setSection("model")}>Модель и подключение</button>
      <button aria-current={section === "rules" ? "page" : undefined} onClick={() => setSection("rules")}>Общие правила и пресеты</button>
      <button aria-current={section === "analysis" ? "page" : undefined} onClick={() => setSection("analysis")}>Проверка изменений</button>
      {appearance && <button aria-current={section === "appearance" ? "page" : undefined} onClick={() => setSection("appearance")}>Внешний вид</button>}
    </nav>
    <div className="next-settings-content">
    <section aria-label="Подключение модели" hidden={section !== "model"}>
      <h2>Модель и подключение</h2>
      <p role="status">{view.detaching ? "Останавливаем операцию FoldCV…" : messages[snapshot.state]}</p>
      {snapshot.version && <p>Версия CLI: {snapshot.version}</p>}
      {snapshot.plan && <p>Подписка: {snapshot.plan}</p>}
      <div className="next-settings-controls">
        <button disabled={view.pending} onClick={() => { void workflow.refresh(); }}>Проверить подключение</button>
        {snapshot.experimentalMode && snapshot.state === "login_required" && <button disabled={view.pending}
          onClick={() => { void workflow.login(); }}>Войти в выделенный CLI</button>}
        {snapshot.state === "login_pending" && <button onClick={() => { void workflow.cancelLogin(); }}>Отменить вход</button>}
        <button disabled={view.detaching} onClick={() => { void workflow.detach(); }}>Отключить модель</button>
      </div>
      {view.pending && <p role="status">{view.detaching ? "Останавливаем…" : "Проверяем…"}</p>}
      {view.error && <p role="alert" className="text-danger">Не удалось завершить действие подключения. Повторите проверку.</p>}
      {snapshot.metadataReady && <label className="next-settings-model">{assistant ? "Модель обработки" : "Модель"}
        <select aria-label={assistant ? "Модель обработки" : "Модель"} disabled={view.pending} value={snapshot.selectedModel ?? ""}
          onChange={event => { void workflow.select(event.target.value).then(readPreferences); }}>
          <option value="">Выберите модель</option>{snapshot.models.map(model => <option key={model} value={model}>{model}</option>)}
        </select>
      </label>}
      {snapshot.metadataReady && <p>Наличие в списке не подтверждает доступ. Лимит: {snapshot.quota.state === "available" ? "доступен"
        : snapshot.quota.state === "exhausted" ? "исчерпан" : "неизвестен"}
        {snapshot.quota.usedPercent !== null ? ` · использовано ${snapshot.quota.usedPercent}%` : ""}
        {snapshot.quota.resetsAt !== null ? ` · сброс ${new Date(snapshot.quota.resetsAt * 1000).toLocaleString()}` : ""}</p>}
      {snapshot.experimentalMode ? <p className="next-settings-disclosure">Персональный режим CLI. Текст передаётся через Codex CLI по вашей
        подписке ChatGPT; действуют правила хранения провайдера. CLI может предоставлять модели встроенные инструменты и сохранять
        следы запросов и ответов. Выделенный вход и состояние остаются после отключения.</p>
        : <p className="next-settings-disclosure">Генерация недоступна: строгий профиль не прошёл проверку безопасности.
          Для персонального режима запустите приложение с выделенным профилем CLI.</p>}
      {!snapshot.generationReady && snapshot.experimentalMode && <p>Генерация пока недоступна. Проверьте вход, модель и лимит.</p>}
      {preferences?.selectedModel && <p>Сохранённый выбор: {preferences.selectedModel}. Доступ подтверждается проверкой подключения.</p>}
      {preferenceError && <p role="alert" className="text-danger">Не удалось прочитать или сохранить настройки. Повторите действие.</p>}
      {assistant?.(snapshot.models)}
    </section>
    <section aria-label="Проверка изменений" hidden={section !== "analysis"}><h2>Проверка изменений</h2>
      <label><input type="checkbox" checked={preferences?.automaticAnalysis ?? true} disabled={!preferences || savingAnalysis}
        onChange={event => { void changeAnalysis(event.target.checked); }} /> Автоматически проверять изменения</label>
      <p>Проверяем завершённые правки. Остальные упоминания меняются только по вашему действию.</p>
    </section>
    <div hidden={section !== "rules"}><RulesPanel /></div>
    {appearance && <section aria-label="Внешний вид" hidden={section !== "appearance"}><h2>Внешний вид</h2>{appearance}</section>}
    </div></div>
  </section>;
}
