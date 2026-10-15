import { useRef } from "react";
import type { AssistantView } from "./controller";
import { canSend, errorText, submitKey } from "./presentation";
import { ModelChoice } from "./ModelChoice";
export function Composer({ view, captured, active, applying, draft, flags, model, send, stop, clear, settings }: {
  view: AssistantView; captured: string | null; active: boolean; applying: boolean;
  draft: (value: string) => void; flags: (edits: boolean, web: boolean) => void; model: (model: string | null) => void;
  send: () => void; stop: () => void; clear: () => void; settings: () => void;
}) {
  const composing = useRef(false), enabled = canSend(view, applying);
  return <form className="assistant-composer" onSubmit={event => { event.preventDefault(); if (enabled) send(); }}>
    <div className="assistant-scope" aria-label="Область следующей задачи">{captured ? <><span>Выделенный фрагмент · {captured}</span><button type="button" onClick={clear} aria-label="Убрать выделение из задачи">×</button></> : <span>Всё резюме</span>}</div>
    <textarea aria-label="Сообщение помощнику" value={view.draft} placeholder="Что проверить или изменить в резюме?" rows={2}
      disabled={view.submitting || view.pendingSend} onChange={event => draft(event.target.value)}
      onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={event => { if (submitKey(event.key, event.shiftKey, composing.current, event.nativeEvent.isComposing, event.keyCode)) {
        event.preventDefault(); if (enabled) send();
      } }} />
    <div className="assistant-composer-controls"><ModelChoice selected={view.settings?.selectedAgentModel ?? null}
      models={view.capabilities?.models.map(item => item.model) ?? []} capabilities={view.capabilities} disabled={!view.settings || view.submitting}
      change={model} /><label><input type="checkbox" checked={!view.flags.allowEdits} disabled={view.submitting || view.pendingSend}
        onChange={event => flags(!event.target.checked, view.flags.allowWeb)} /> Только проверка</label>
      <label><input type="checkbox" checked={view.flags.allowWeb} disabled={view.submitting || view.pendingSend}
        onChange={event => flags(view.flags.allowEdits, event.target.checked)} /> Интернет</label>
      <span className="assistant-send-space" />{active && <button type="button" onClick={stop} disabled={view.submitting}>Остановить</button>}
      <button type="submit" disabled={!enabled}>{view.pendingSend ? "Повторить отправку" : "Отправить"}</button></div>
    {active && <small>Модель, режим и область задачи уже зафиксированы. Выбор выше относится к следующей отправке.</small>}
    {[...view.draft].length > 8000 && <small className="text-danger">Сообщение длиннее 8000 символов.</small>}
    {view.capabilities?.unavailable && <p className="assistant-unavailable">{errorText(view.capabilities.unavailable.code)} <button type="button" onClick={settings}>Настройки</button></p>}
  </form>;
}
