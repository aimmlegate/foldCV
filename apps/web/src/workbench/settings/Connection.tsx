import { useState } from "react";
import { errorMessage } from "../../errors/messages";
import { loginCodePattern, type ConnectionView, type ConnectionWorkflow, type ProviderActivity, type ProviderEntry } from "../../connection/workflow";
import { connectionMessage } from "../../connection/messages";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/OperationStatus";
import { Installation } from "./Installation";

/** Every listed provider with its own switch and connection (D119); the model choices below take any of their models. */
export function Connections({ view, workflow, disabled }: { view: ConnectionView; workflow: ConnectionWorkflow; disabled: boolean }) {
  const { snapshot } = view;
  return <><h3>Провайдеры</h3>
    <p>Включите провайдеров, через которых работает FoldCV. Модели всех включённых провайдеров можно выбрать ниже.</p>
    {snapshot.provider === null && !view.readFailed && <p className="small muted" role="status">Проверяем подключение…</p>}
    {view.readFailed && <div className="settings-actions"><p className="notice error" role="alert">Не удалось прочитать состояние подключения.</p>
      <Button className="small" onClick={() => void workflow.peek()}>Повторить</Button></div>}
    {snapshot.providers.map(entry => <ProviderCard key={entry.kind} entry={entry} activity={view.activity[entry.kind]}
      experimental={snapshot.experimentalMode} workflow={workflow} disabled={disabled} />)}
  </>;
}

function ProviderCard({ entry, activity, experimental, workflow, disabled }: { entry: ProviderEntry; activity: ProviderActivity | undefined;
  experimental: boolean; workflow: ConnectionWorkflow; disabled: boolean }) {
  const { kind, display, subscription, publisher, loginCode } = entry;
  const pending = activity?.pending ?? false, detaching = activity?.detaching ?? false;
  const [code, setCode] = useState(""), [codeSent, setCodeSent] = useState(false);
  const installation = entry.installation;
  const installing = installation && ["downloading", "verifying", "extracting"].includes(installation.state);
  const canInstall = installation?.available && ["cli_missing", "launcher_unsupported", "unsupported_version"].includes(entry.state);
  const quota = entry.quota.state === "not_provided" ? "Использование не предоставляется провайдером"
    : `${entry.quota.usedPercent !== null ? `Использовано ${entry.quota.usedPercent}%` : "Использование неизвестно"}`
      + ` · Лимит ${entry.quota.state === "available" ? "доступен" : entry.quota.state === "exhausted" ? "исчерпан" : "неизвестен"}`
      + (entry.quota.resetsAt !== null ? ` · Сброс ${new Date(entry.quota.resetsAt * 1000).toLocaleString()}` : "");
  const id = `provider-${kind}`;
  return <div className="provider-card" data-provider={kind}>
    <div className="switch-line"><label htmlFor={id}><strong>{display}</strong> <small>по подписке {subscription}</small></label>
      <input className="switch" id={id} aria-label={`Включить ${display}`} role="switch" type="checkbox" checked={entry.enabled}
        disabled={disabled || pending || detaching || Boolean(installing)} onChange={event => void workflow.enable(kind, event.currentTarget.checked)} /></div>
    {!entry.enabled ? <p className="small muted">{entry.installed ? "Выключен." : "Выключен, не установлен."} Включите, чтобы подключить {display}.</p> : <>
      <div className="connection-status"><span className="connection-check">{pending || detaching || entry.state === "login_pending" ? <Spinner /> : <Icon name={entry.state === "connected" ? "check" : "info"} />}</span>
        <div><strong role="status">{detaching ? "Останавливаем подключение…" : installing ? `Устанавливаем ${display}…` : entry.state === "login_pending" ? connectionMessage("login_pending", { display, subscription }) : pending ? "Проверяем подключение…" : connectionMessage(entry.state, { display, subscription })}</strong>
          <small>{[entry.plan, entry.version].filter(Boolean).join(" · ") || "Нет сведений о подписке"}</small></div></div>
      {entry.versionStatus === "graceful" && <p className="small muted">Версия новее проверенной в FoldCV; её возможности проверены при подключении.</p>}
      <div className="quota-line">{entry.quota.usedPercent !== null && <span className="quota-bar"><span style={{ width: `${entry.quota.usedPercent}%` }} /></span>}
        {quota}
      </div>
      {installation && <Installation value={installation} display={display} />}
      {canInstall && <p className="small muted">{display} будет установлен с сайта {publisher}.</p>}
      <div className="settings-actions"><Button className="small" busy={pending && !installing && entry.state !== "login_pending"} busyLabel="Проверяем…" disabled={disabled || pending || Boolean(installing)} onClick={() => void workflow.refresh(kind)}>Проверить подключение</Button>
        {canInstall && <Button variant="primary" className="small" busy={Boolean(installing)} busyLabel="Устанавливаем…" disabled={disabled || pending} onClick={() => void workflow.install(kind)}>Установить {display}</Button>}
        {installing && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelInstall(kind)}>Отменить установку</button>}
        {experimental && entry.state === "login_required" && <button className="text-button" disabled={disabled || pending} onClick={() => void workflow.login(kind)}>Войти через {subscription}</button>}
        {entry.state === "login_pending" && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelLogin(kind)}>Отменить вход</button>}
        <Button variant="quiet" busy={detaching} busyLabel="Отключаем…" disabled={disabled} onClick={() => void workflow.detach(kind)}>Отключить</Button>
      </div>
      {entry.state === "login_pending" && loginCode && <form className="login-code" onSubmit={event => {
        event.preventDefault();
        void workflow.sendLoginCode(kind, code).then(sent => { if (sent) { setCode(""); setCodeSent(true); } });
      }}>
        <label htmlFor={`login-code-${kind}`}>Код со страницы входа</label>
        <p className="small muted">Если после входа в браузере {display} показал код, вставьте его сюда.</p>
        <input id={`login-code-${kind}`} autoComplete="off" spellCheck={false} value={code} disabled={disabled}
          onChange={event => { setCode(event.currentTarget.value); setCodeSent(false); }} />
        <Button type="submit" className="small" disabled={disabled || !loginCodePattern.test(code.trim())}>Отправить код</Button>
        {codeSent && <p className="small muted" role="status">Код передан. Дождитесь завершения входа.</p>}
      </form>}
      <p className="small muted">Вход, установка и отключение останавливают работу моделей: идущий импорт, правка или ответ помощника прервутся.</p>
      {experimental ? <p className="settings-disclosure">Текст уходит в {publisher}, действуют её правила хранения. {display} может сохранять
        запросы и ответы. Вход остаётся после отключения.</p>
        : <p className="settings-disclosure">Обработка недоступна в текущем режиме подключения.</p>}
    </>}
    {activity?.error && <p className="notice error" role="alert">{errorMessage(activity.error)}</p>}
  </div>;
}
