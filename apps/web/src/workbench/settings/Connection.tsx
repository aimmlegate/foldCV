import type { ConnectionView, ConnectionWorkflow } from "../../connection/workflow";
import { connectionMessages } from "../../connection/messages";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { ModelSelect } from "./ModelSelect";
import { Spinner } from "../ui/OperationStatus";

export function Connection({ view, workflow, model, change, disabled, selectionDisabled }: { view: ConnectionView; workflow: ConnectionWorkflow;
  model: string | null; change: (value: string) => void; disabled: boolean; selectionDisabled: boolean }) {
  const snapshot = view.snapshot;
  return <><h3>Модель и подключение</h3><p>Подключение через Codex по подписке ChatGPT.</p>
    <div className="connection-status"><span className="connection-check">{view.pending || view.detaching || snapshot.state === "login_pending" ? <Spinner /> : <Icon name={snapshot.state === "connected" ? "check" : "info"} />}</span>
      <div><strong role="status">{view.detaching ? "Останавливаем подключение…" : view.pending ? "Проверяем CLI, вход и доступные модели…" : connectionMessages[snapshot.state]}</strong>
        <small>{[snapshot.plan, snapshot.version].filter(Boolean).join(" · ") || "Сведения о подписке ещё не получены"}</small></div></div>
    <ModelSelect id="model-select" label="Модель обработки" value={model} models={snapshot.models}
      disabled={disabled || selectionDisabled || view.pending || !snapshot.metadataReady}
      change={value => { if (value) change(value); }} />
    <p className="small muted">Список получен от подключения. Наличие модели в списке не подтверждает доступ.</p>
    <div className="quota-line">{snapshot.quota.usedPercent !== null && <span className="quota-bar"><span style={{ width: `${snapshot.quota.usedPercent}%` }} /></span>}
      {snapshot.quota.usedPercent !== null ? `Использовано ${snapshot.quota.usedPercent}%` : "Использование неизвестно"}
      {` · Лимит ${snapshot.quota.state === "available" ? "доступен" : snapshot.quota.state === "exhausted" ? "исчерпан" : "неизвестен"}`}
      {snapshot.quota.resetsAt !== null && ` · Сброс ${new Date(snapshot.quota.resetsAt * 1000).toLocaleString()}`}
    </div>
    <div className="settings-actions"><Button className="small" busy={view.pending} busyLabel="Проверяем…" disabled={disabled} onClick={() => void workflow.refresh()}>Проверить подключение</Button>
      {snapshot.experimentalMode && snapshot.state === "login_required" && <button className="text-button" disabled={disabled || view.pending} onClick={() => void workflow.login()}>Войти в Codex</button>}
      {snapshot.state === "login_pending" && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelLogin()}>Отменить вход</button>}
      <Button variant="quiet" busy={view.detaching} busyLabel="Отключаем…" disabled={disabled} onClick={() => void workflow.detach()}>Отключить модель</Button>
    </div>
    {view.error && <p className="notice error" role="alert">Не удалось завершить действие подключения. Повторите проверку.</p>}
    <p className="settings-disclosure">Проверка, вход и отключение выполняются сразу. Отмена черновика настроек их не отменяет.</p>
    {snapshot.experimentalMode ? <p className="settings-disclosure">Текст передаётся через Codex CLI по вашей подписке ChatGPT; действуют правила хранения провайдера.
      CLI может предоставлять встроенные инструменты и сохранять запросы и ответы. Вход остаётся после отключения.</p>
      : <p className="settings-disclosure">Обработка недоступна в текущем режиме подключения.</p>}
  </>;
}
