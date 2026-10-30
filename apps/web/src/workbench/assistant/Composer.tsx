import { useRef, useState } from "react";
import type { AssistantView } from "../../assistant/controller";
import { canSend, errorText, submitKey } from "../../assistant/presentation";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/OperationStatus";
import { commandCompletion, commandSuggestions } from "../../assistant/commands";
import { CommandMenu } from "./CommandMenu";
import { choiceGroups, modelChoices, type ModelChoice } from "./model-choices";

const modelOption = (item: ModelChoice) => <option key={item.model} value={item.model}>{item.model}{item.state === "unavailable" ? " · недоступна" : item.state === "incompatible" ? " · не подходит" : ""}</option>;

export type ComposerProps = {
  view: AssistantView; captured: string | null; active: boolean; applying: boolean; title: string;
  draft: (value: string) => void; flags: (edits: boolean, web: boolean) => void; model: (model: string | null) => void;
  send: () => void; stop: () => void; clear: () => void; settings: () => void;
};
export function Composer({ view, captured, active, applying, title, draft, flags, model, send, stop, clear, settings }: ComposerProps) {
  const composing = useRef(false), enabled = canSend(view, applying);
  const input = useRef<HTMLTextAreaElement>(null);
  const [commandIndex, setCommandIndex] = useState(0), [dismissed, setDismissed] = useState<string | null>(null);
  const suggestions = commandSuggestions(view.draft), commandOpen = suggestions.length > 0 && dismissed !== view.draft && !view.submitting && !view.pendingSend;
  const selectedCommand = commandIndex < suggestions.length ? commandIndex : 0;
  const chooseCommand = (value: string) => { draft(value); setCommandIndex(0); input.current?.focus(); };
  const selected = view.settings?.selectedAgentModel ?? "", models = view.capabilities?.models ?? [];
  const choices = modelChoices(selected, models, view.capabilities?.ready === true && view.loading == null);
  return <form className="chat-composer" onSubmit={event => { event.preventDefault(); if (enabled) send(); }}>
    <div className="chat-context" aria-label="Контекст"><span className="chat-context-resume" title={title}><Icon name="file" />{title}</span>
      <button className={`chat-scope${captured ? " has-selection" : ""}`} type="button" disabled={!captured} onClick={clear}
        aria-label={captured ? `Убрать выделение: ${captured}` : "Весь проект"}>{captured ? <><Icon name="check" />Выделение · {captured}<Icon name="close" /></> : "Весь проект"}</button></div>
    <div className="chat-input-box">{commandOpen && <CommandMenu choices={suggestions} selected={selectedCommand} choose={chooseCommand} />}
      <textarea ref={input} id="chat-input" aria-label="Сообщение помощнику" value={view.draft} placeholder="Что проверить или изменить? / — команды" rows={2}
      role="combobox" aria-autocomplete="list" aria-expanded={commandOpen} aria-controls={commandOpen ? "assistant-commands" : undefined}
      aria-activedescendant={commandOpen ? `assistant-command-${String(selectedCommand)}` : undefined}
      disabled={view.submitting || view.pendingSend} onChange={event => { draft(event.target.value); setCommandIndex(0); setDismissed(null); }}
      onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={event => {
        const inComposition = composing.current || event.nativeEvent.isComposing || event.keyCode === 229;
        if (commandOpen && !inComposition && !event.shiftKey) {
          if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setDismissed(view.draft); return; }
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault(); setCommandIndex((selectedCommand + (event.key === "ArrowDown" ? 1 : suggestions.length - 1)) % suggestions.length); return;
          }
          const completion = commandCompletion(view.draft, selectedCommand, event.key, event.shiftKey, inComposition);
          if (completion) { event.preventDefault(); chooseCommand(completion); return; }
        }
        if (submitKey(event.key, event.shiftKey, composing.current, event.nativeEvent.isComposing, event.keyCode)) {
        event.preventDefault(); if (enabled) send();
      } }} />
      <div className="chat-composer-controls"><div className="chat-controls-left"><label className="chat-model-label"><span className="visually-hidden">Модель помощника</span>
        <select id="chat-model" aria-label="Модель помощника" value={selected} disabled={!view.settings || view.submitting} onChange={event => model(event.target.value || null)}>
          <option value="">Выберите модель</option>{choiceGroups(choices).map(group => group.label
            ? <optgroup key={group.label} label={group.label}>{group.choices.map(modelOption)}</optgroup> : group.choices.map(modelOption))}
        </select></label>
        <label className="chat-mode"><input type="checkbox" checked={view.flags.allowEdits} disabled={view.submitting || view.pendingSend}
          onChange={event => flags(event.target.checked, view.flags.allowWeb)} />Разрешить правки</label>
        <label className="chat-mode chat-internet"><input type="checkbox" checked={view.flags.allowWeb} disabled={view.submitting || view.pendingSend}
          onChange={event => flags(view.flags.allowEdits, event.target.checked)} /><Icon name="globe" /><span>Интернет</span></label></div>
        {active && <button className="chat-send is-stop" type="button" title="Остановить" aria-label="Остановить" onClick={stop} disabled={view.submitting || view.run?.state === "cancelling" || view.loading === "Останавливаем"}>{view.submitting || view.run?.state === "cancelling" || view.loading === "Останавливаем" ? <Spinner /> : <Icon name="stop" />}</button>}
        {(!active || view.pendingSend) && <button className="chat-send" type="submit" disabled={!enabled} title={view.pendingSend ? "Повторить отправку" : "Отправить"}
          aria-label={view.pendingSend ? "Повторить отправку" : "Отправить"}><Icon name="arrow" /></button>}</div></div>
    {[...view.draft].length > 8000 && <p className="chat-error" role="alert">Сообщение длиннее 8000 символов.</p>}
    {view.capabilities?.unavailable && <p className="chat-error">{errorText(view.capabilities.unavailable.code)} <button className="text-button" type="button" onClick={settings}>Настройки</button></p>}
  </form>;
}
