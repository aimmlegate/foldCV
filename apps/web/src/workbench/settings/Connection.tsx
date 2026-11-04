import { useState } from "react";
import { errorMessage } from "../../errors/messages";
import { installable, loginCodePattern, type ConnectionView, type ConnectionWorkflow, type ProviderActivity, type ProviderEntry } from "../../connection/workflow";
import { connectionMessage } from "../../connection/messages";
import { APP_NAME } from "../app-name";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/OperationStatus";
import { Installation } from "./Installation";

/** Every listed provider with its own switch and connection (D119); the model choices take any of their models. */
export function Connections({ view, workflow, disabled }: { view: ConnectionView; workflow: ConnectionWorkflow; disabled: boolean }) {
  const { snapshot } = view;
  return <>
    {snapshot.provider === null && !view.readFailed && <p className="small muted" role="status">Проверяем подключение…</p>}
    {view.readFailed && <div className="settings-actions"><p className="notice error" role="alert">Не удалось прочитать состояние подключения.</p>
      <Button className="small" onClick={() => void workflow.peek()}>Повторить</Button></div>}
    {snapshot.providers.map(entry => <ProviderCard key={entry.kind} entry={entry} activity={view.activity[entry.kind]}
      experimental={snapshot.experimentalMode} workflow={workflow} disabled={disabled} />)}
    {snapshot.providers.some(entry => entry.enabled) && <p className="settings-lead provider-note">Вход, установка и отключение останавливают работу моделей:
      идущий импорт, правка или ответ помощника прервутся.</p>}
  </>;
}

/** The usage line: the share used and when it resets; null when the provider reports nothing. */
export function quotaText(quota: ProviderEntry["quota"]): string {
  if (quota.state === "not_provided") return "Расход не сообщается";
  const used = quota.usedPercent !== null ? `Использовано ${String(quota.usedPercent)} %` : "Расход неизвестен";
  const reset = quota.resetsAt !== null ? ` · сброс ${new Date(quota.resetsAt * 1000).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : "";
  return `${used}${quota.state === "exhausted" ? " · лимит исчерпан" : ""}${reset}`;
}

/** One provider in one block (D147): the switch, name and actions in the head row, then the status with the usage,
 * then only the rows that apply (update, install progress, sign-in code, error); the storage note folds away. */
function ProviderCard({ entry, activity, experimental, workflow, disabled }: { entry: ProviderEntry; activity: ProviderActivity | undefined;
  experimental: boolean; workflow: ConnectionWorkflow; disabled: boolean }) {
  const { kind, display, subscription, publisher, loginCode } = entry;
  const pending = activity?.pending ?? false, detaching = activity?.detaching ?? false;
  const [code, setCode] = useState(""), [codeSent, setCodeSent] = useState(false);
  const installation = entry.installation;
  const installing = installation && ["downloading", "verifying", "extracting"].includes(installation.state);
  const canInstall = installable(entry), update = Boolean(installation?.update) && !installing;
  // An update keeps the profile, so a sign-in stays.
  const signedIn = ["connected", "unknown_limits", "quota_exhausted"].includes(entry.state);
  const installNote = update ? `${display} ${installation?.latest ?? ""} будет скачан с сайта ${publisher}.${signedIn ? " Вход сохранится." : ""}`
    : `${display} будет установлен с сайта ${publisher}.`;
  const status = detaching ? "Останавливаем подключение…" : installing ? `${installation?.installed ? "Обновляем" : "Устанавливаем"} ${display}…`
    : entry.state === "login_pending" ? connectionMessage("login_pending", { display, subscription }) : pending ? "Проверяем подключение…"
    : connectionMessage(entry.state, { display, subscription });
  const id = `provider-${kind}`;
  return <div className="provider-card" data-provider={kind}>
    <div className="provider-head">
      <input className="switch" id={id} aria-label={`Включить ${display}`} role="switch" type="checkbox" checked={entry.enabled}
        disabled={disabled || pending || detaching || Boolean(installing)} onChange={event => { const on = event.currentTarget.checked; void workflow.enable(kind, on).then(() => { if (on) void workflow.checkReleases(); }); }} />
      <label className="provider-name" htmlFor={id}><strong>{display}</strong>
        <small>{[`по подписке ${subscription}`, entry.enabled ? entry.plan : null, entry.enabled ? entry.version : null].filter(Boolean).join(" · ")}</small></label>
      {entry.enabled && <div className="provider-actions">
        {(canInstall || installing) && <Button variant="primary" className="small" busy={Boolean(installing)} busyLabel={installation?.installed ? "Обновляем…" : "Устанавливаем…"}
          disabled={disabled || pending} onClick={() => void workflow.install(kind)}>{update ? `Обновить ${display}` : `Установить ${display}`}</Button>}
        {installing && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelInstall(kind)}>Отменить установку</button>}
        {experimental && entry.state === "login_required" && <button className="text-button" disabled={disabled || pending} onClick={() => void workflow.login(kind)}>Войти через {subscription}</button>}
        {entry.state === "login_pending" && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelLogin(kind)}>Отменить вход</button>}
        <Button className="small" busy={pending && !installing && entry.state !== "login_pending"} busyLabel="Проверяем…" disabled={disabled || pending || Boolean(installing)}
          title="Проверить подключение" onClick={() => void workflow.refresh(kind).then(() => workflow.checkReleases())}>Проверить</Button>
        <Button variant="quiet" className="small" busy={detaching} busyLabel="Отключаем…" disabled={disabled} onClick={() => void workflow.detach(kind)}>Отключить</Button>
      </div>}
    </div>
    {!entry.enabled ? <p className="provider-line">{entry.installed ? "Выключен." : "Выключен, не установлен."} Включите, чтобы подключить {display}.</p> : <>
      <div className="provider-status">
        <span className="provider-state" data-state={entry.state}>{pending || detaching || entry.state === "login_pending" ? <Spinner /> : <Icon name={entry.state === "connected" ? "check" : "info"} />}
          <strong role="status">{status}</strong></span>
        <span className="quota-line">{entry.quota.usedPercent !== null && <span className="quota-bar"><span style={{ width: `${String(entry.quota.usedPercent)}%` }} /></span>}
          {quotaText(entry.quota)}</span>
      </div>
      {entry.versionStatus === "graceful" && <p className="provider-line">Версия новее проверенной в {APP_NAME}; её возможности проверены при подключении.</p>}
      {update ? <p className="provider-line provider-update" role="status">Доступна новая версия {display}: {installation?.latest}. Установлена {installation?.installed}.</p>
        : installation?.latest && installation.latest === installation.installed && !installing
          && <p className="provider-line">Установлена последняя версия {display}.</p>}
      {installation && <Installation value={installation} display={display} />}
      {canInstall && <p className="provider-line">{installNote}</p>}
      {entry.state === "login_pending" && loginCode && <form className="login-code provider-line" onSubmit={event => {
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
      {experimental ? <details className="provider-line provider-legal"><summary>Текст уходит в {publisher}, действуют её правила хранения. <span>Подробнее</span></summary>
        {display} может сохранять запросы и ответы. Вход остаётся после отключения.</details>
        : <p className="provider-line provider-legal">Обработка недоступна в текущем режиме подключения.</p>}
    </>}
    {activity?.error && <p className="notice error provider-line" role="alert">{errorMessage(activity.error)}</p>}
  </div>;
}
