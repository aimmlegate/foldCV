import { useState } from "react";
import { errorMessage } from "../../errors/messages";
import { loginCodePattern, providerNames, type ConnectionView, type ConnectionWorkflow, type ProviderKind } from "../../connection/workflow";
import { connectionMessage } from "../../connection/messages";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { ModelSelect } from "./ModelSelect";
import { Spinner } from "../ui/OperationStatus";
import { Installation } from "./Installation";

export function Connection({ view, workflow, model, change, disabled, selectionDisabled, switchDisabled, providerChanged }: { view: ConnectionView;
  workflow: ConnectionWorkflow; model: string | null; change: (value: string) => void; disabled: boolean; selectionDisabled: boolean;
  switchDisabled: boolean; providerChanged: () => void }) {
  const snapshot = view.snapshot;
  const { display, subscription, publisher, loginCode } = providerNames(snapshot);
  const [code, setCode] = useState(""), [codeSent, setCodeSent] = useState(false);
  const installation = snapshot.installation;
  const installing = installation && ["downloading", "verifying", "extracting"].includes(installation.state);
  const canInstall = installation?.available && ["cli_missing", "launcher_unsupported", "unsupported_version"].includes(snapshot.state);
  const quota = snapshot.quota.state === "not_provided" ? "Использование не предоставляется провайдером"
    : `${snapshot.quota.usedPercent !== null ? `Использовано ${snapshot.quota.usedPercent}%` : "Использование неизвестно"}`
      + ` · Лимит ${snapshot.quota.state === "available" ? "доступен" : snapshot.quota.state === "exhausted" ? "исчерпан" : "неизвестен"}`
      + (snapshot.quota.resetsAt !== null ? ` · Сброс ${new Date(snapshot.quota.resetsAt * 1000).toLocaleString()}` : "");
  return <><h3>Модель и подключение</h3><p>Подключение через {display} по подписке {subscription}.</p>
    {snapshot.providerNotice === "provider_unavailable" && <p className="notice" role="status">Выбранный ранее провайдер сейчас недоступен. Используется {display}.</p>}
    <label htmlFor="provider-select">Провайдер</label>
    {/* Switching detaches at once, like sign-in and detach; unsaved model drafts would belong to the old provider. */}
    <select className="model-select" id="provider-select" aria-label="Провайдер" value={snapshot.provider ?? ""}
      disabled={disabled || switchDisabled || view.pending || view.detaching || snapshot.providers.length < 2}
      onChange={event => void workflow.selectProvider(event.currentTarget.value as ProviderKind).then(done => { if (done) providerChanged(); })}>
      {snapshot.provider === null && <option value="">Проверяем…</option>}
      {snapshot.providers.map(item => <option key={item.kind} value={item.kind}>{item.display}{item.installed ? "" : " · не установлен"}</option>)}
    </select>
    <div className="connection-status"><span className="connection-check">{view.pending || view.detaching || snapshot.state === "login_pending" ? <Spinner /> : <Icon name={snapshot.state === "connected" ? "check" : "info"} />}</span>
      <div><strong role="status">{view.detaching ? "Останавливаем подключение…" : installing ? `Устанавливаем ${display}…` : snapshot.state === "login_pending" ? connectionMessage("login_pending", { display, subscription }) : view.pending ? "Проверяем подключение…" : connectionMessage(snapshot.state, { display, subscription })}</strong>
        <small>{[snapshot.plan, snapshot.version].filter(Boolean).join(" · ") || "Нет сведений о подписке"}</small></div></div>
    {snapshot.versionStatus === "graceful" && <p className="small muted">Версия новее проверенной в FoldCV; её возможности проверены при подключении.</p>}
    <ModelSelect id="model-select" label="Модель обработки" value={model} models={snapshot.models}
      disabled={disabled || selectionDisabled || view.pending || !snapshot.metadataReady}
      change={value => { if (value) change(value); }} />
    <div className="quota-line">{snapshot.quota.usedPercent !== null && <span className="quota-bar"><span style={{ width: `${snapshot.quota.usedPercent}%` }} /></span>}
      {quota}
    </div>
    {installation && <Installation value={installation} display={display} />}
    {canInstall && <p className="small muted">{display} будет установлен с сайта {publisher}.</p>}
    <div className="settings-actions"><Button className="small" busy={view.pending && !installing && snapshot.state !== "login_pending"} busyLabel="Проверяем…" disabled={disabled || view.pending || Boolean(installing)} onClick={() => void workflow.refresh()}>Проверить подключение</Button>
      {canInstall && <Button variant="primary" className="small" busy={Boolean(installing)} busyLabel="Устанавливаем…" disabled={disabled || view.pending} onClick={() => void workflow.install()}>Установить {display}</Button>}
      {installing && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelInstall()}>Отменить установку</button>}
      {snapshot.experimentalMode && snapshot.state === "login_required" && <button className="text-button" disabled={disabled || view.pending} onClick={() => void workflow.login()}>Войти через {subscription}</button>}
      {snapshot.state === "login_pending" && <button className="text-button" disabled={disabled} onClick={() => void workflow.cancelLogin()}>Отменить вход</button>}
      <Button variant="quiet" busy={view.detaching} busyLabel="Отключаем…" disabled={disabled} onClick={() => void workflow.detach()}>Отключить модель</Button>
    </div>
    {snapshot.state === "login_pending" && loginCode && <form className="login-code" onSubmit={event => {
      event.preventDefault();
      void workflow.sendLoginCode(code).then(sent => { if (sent) { setCode(""); setCodeSent(true); } });
    }}>
      <label htmlFor="login-code">Код со страницы входа</label>
      <p className="small muted">Если после входа в браузере {display} показал код, вставьте его сюда.</p>
      <input id="login-code" autoComplete="off" spellCheck={false} value={code} disabled={disabled}
        onChange={event => { setCode(event.currentTarget.value); setCodeSent(false); }} />
      <Button type="submit" className="small" disabled={disabled || !loginCodePattern.test(code.trim())}>Отправить код</Button>
      {codeSent && <p className="small muted" role="status">Код передан. Дождитесь завершения входа.</p>}
    </form>}
    {view.error && <p className="notice error" role="alert">{errorMessage(view.error)}</p>}
    {snapshot.experimentalMode ? <p className="settings-disclosure">Текст уходит в {publisher}, действуют её правила хранения. {display} может сохранять
      запросы и ответы. Вход остаётся после отключения.</p>
      : <p className="settings-disclosure">Обработка недоступна в текущем режиме подключения.</p>}
  </>;
}
