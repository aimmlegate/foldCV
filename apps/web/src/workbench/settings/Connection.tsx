import type { ConnectionView, ConnectionWorkflow } from "../../connection/workflow";
import { connectionMessages } from "../../connection/messages";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

export function Connection({ view, workflow, model, change, disabled, selectionDisabled }: { view: ConnectionView; workflow: ConnectionWorkflow;
  model: string | null; change: (value: string) => void; disabled: boolean; selectionDisabled: boolean }) {
  const snapshot = view.snapshot;
  const choices = model && !snapshot.models.includes(model) ? [model, ...snapshot.models] : snapshot.models;
  return <><h3>Модель и подключение</h3><p>Подключение через Codex по подписке ChatGPT.</p>
    <div className="connection-status"><span className="connection-check"><Icon name={snapshot.state === "connected" ? "check" : "info"} /></span>
      <div><strong>{view.detaching ? "Останавливаем операцию…" : connectionMessages[snapshot.state]}</strong>
        <small>{[snapshot.plan, snapshot.version].filter(Boolean).join(" · ") || "Сведения о подписке ещё не получены"}</small></div></div>
    <label htmlFor="model-select">Модель обработки</label>
    <select className="model-select" id="model-select" aria-label="Модель обработки" value={model ?? ""} disabled={disabled || selectionDisabled || view.pending || !snapshot.metadataReady}
      onChange={event => change(event.currentTarget.value)}><option value="" disabled>Выберите модель</option>
      {choices.map(value => <option key={value} value={value} disabled={!snapshot.models.includes(value)}>{value}{!snapshot.models.includes(value) ? " · недоступна" : ""}</option>)}
    </select>
    <p className="small muted">Список получен от подключения. Наличие модели в списке не подтверждает доступ.</p>
    <div className="quota-line">{snapshot.quota.usedPercent !== null && <span className="quota-bar"><span style={{ width: `${snapshot.quota.usedPercent}%` }} /></span>}
      {snapshot.quota.usedPercent !== null ? `Использовано ${snapshot.quota.usedPercent}%` : "Использование неизвестно"}
      {` · Лимит ${snapshot.quota.state === "available" ? "доступен" : snapshot.quota.state === "exhausted" ? "исчерпан" : "неизвестен"}`}
      {snapshot.quota.resetsAt !== null && ` · Сброс ${new Date(snapshot.quota.resetsAt * 1000).toLocaleString()}`}
    </div>
    <div className="settings-actions"><Button className="small" disabled={disabled || view.pending} onClick={() => void workflow.refresh()}>{view.pending ? "Проверяем…" : "Проверить подключение"}</Button>
      {snapshot.experimentalMode && snapshot.state === "login_required" && <button className="text-button" disabled={disabled || view.pending} onClick={() => void workflow.login()}>Войти в Codex</button>}
      {snapshot.state === "login_pending" && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelLogin()}>Отменить вход</button>}
      <button className="text-button" disabled={disabled || view.detaching} onClick={() => void workflow.detach()}>Отключить модель</button>
    </div>
    {view.error && <p className="notice error" role="alert">Не удалось завершить действие подключения. Повторите проверку.</p>}
    <p className="settings-disclosure">Проверка, вход и отключение выполняются сразу. Отмена черновика настроек их не отменяет.</p>
    {snapshot.experimentalMode ? <p className="settings-disclosure">Текст передаётся через Codex CLI по вашей подписке ChatGPT; действуют правила хранения провайдера.
      CLI может предоставлять встроенные инструменты и сохранять запросы и ответы. Вход остаётся после отключения.</p>
      : <p className="settings-disclosure">Обработка недоступна в текущем режиме подключения.</p>}
  </>;
}
