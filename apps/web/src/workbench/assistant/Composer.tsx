import { useRef } from "react";
import type { AssistantView } from "../../assistant/controller";
import { canSend, errorText, submitKey } from "../../assistant/presentation";
import { Icon } from "../ui/Icon";

export type ComposerProps = {
  view: AssistantView; captured: string | null; active: boolean; applying: boolean; title: string;
  draft: (value: string) => void; flags: (edits: boolean, web: boolean) => void; model: (model: string | null) => void;
  send: () => void; stop: () => void; clear: () => void; settings: () => void;
};
export function Composer({ view, captured, active, applying, title, draft, flags, model, send, stop, clear, settings }: ComposerProps) {
  const composing = useRef(false), enabled = canSend(view, applying);
  const selected = view.settings?.selectedAgentModel ?? "", models = view.capabilities?.models ?? [];
  const choices = selected && !models.some(item => item.model === selected) ? [{ model: selected, state: "unavailable" }, ...models] : models;
  return <form className="chat-composer" onSubmit={event => { event.preventDefault(); if (enabled) send(); }}>
    <div className="chat-context" aria-label="Область следующей задачи"><span className="chat-context-resume" title={title}><Icon name="file" />{title}</span>
      <button className={`chat-scope${captured ? " has-selection" : ""}`} type="button" disabled={!captured} onClick={clear}
        aria-label={captured ? "Убрать выделение из задачи" : "Всё резюме"}>{captured ? <><Icon name="check" />Выделенный фрагмент · {captured}<Icon name="close" /></> : "Всё резюме"}</button></div>
    <div className="chat-input-box"><textarea id="chat-input" aria-label="Сообщение помощнику" value={view.draft} placeholder="Что проверить или изменить в резюме?" rows={2}
      disabled={view.submitting || view.pendingSend} onChange={event => draft(event.target.value)}
      onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={event => { if (submitKey(event.key, event.shiftKey, composing.current, event.nativeEvent.isComposing, event.keyCode)) {
        event.preventDefault(); if (enabled) send();
      } }} />
      <div className="chat-composer-controls"><div className="chat-controls-left"><label className="chat-model-label"><span className="visually-hidden">Модель помощника</span>
        <select id="chat-model" aria-label="Модель помощника" value={selected} disabled={!view.settings || view.submitting} onChange={event => model(event.target.value || null)}>
          <option value="">Выберите модель помощника</option>{choices.map(item => <option key={item.model} value={item.model}>{item.model}{item.state === "unavailable" ? " · недоступна" : item.state === "incompatible" ? " · инструменты недоступны" : ""}</option>)}
        </select></label>
        <label className="chat-mode"><input type="checkbox" checked={!view.flags.allowEdits} disabled={view.submitting || view.pendingSend}
          onChange={event => flags(!event.target.checked, view.flags.allowWeb)} />Только проверка</label>
        <label className="chat-mode chat-internet"><input type="checkbox" checked={view.flags.allowWeb} disabled={view.submitting || view.pendingSend}
          onChange={event => flags(view.flags.allowEdits, event.target.checked)} /><Icon name="globe" /><span>Интернет</span></label></div>
        {active && <button className="chat-send is-stop" type="button" title="Остановить" aria-label="Остановить" onClick={stop} disabled={view.submitting}><Icon name="stop" /></button>}
        {(!active || view.pendingSend) && <button className="chat-send" type="submit" disabled={!enabled} title={view.pendingSend ? "Повторить отправку" : "Отправить"}
          aria-label={view.pendingSend ? "Повторить отправку" : "Отправить"}><Icon name="arrow" /></button>}</div></div>
    <div className="chat-composer-footer"><span>{active ? "Выбор относится к следующей задаче. Текущая область и режим уже зафиксированы." : "Правки сохраняются в общей истории редактора."}</span><span>Enter — отправить · Shift+Enter — новая строка</span></div>
    {[...view.draft].length > 8000 && <p className="chat-error" role="alert">Сообщение длиннее 8000 символов.</p>}
    {view.capabilities?.unavailable && <p className="chat-error">{errorText(view.capabilities.unavailable.code)} <button className="text-button" type="button" onClick={settings}>Настройки</button></p>}
  </form>;
}
