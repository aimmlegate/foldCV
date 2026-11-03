import type { AssistantCommand } from "../../assistant/commands";

export function CommandMenu({ id, option, choices, selected, choose }: { id: string; option: string; choices: readonly AssistantCommand[]; selected: number; choose: (value: string) => void }) {
  return <div id={id} className="chat-command-menu" role="listbox" aria-label="Команды помощника">
    <span className="chat-command-caption">↑↓ выбрать · Tab вставить</span>
    {choices.map((item, index) => <button id={`${option}-${String(index)}`} key={item.command} type="button" role="option"
      aria-selected={index === selected} tabIndex={-1} onMouseDown={event => event.preventDefault()} onClick={() => choose(item.command + " ")}>
      <strong>{item.command}</strong><span>{item.description}</span>
    </button>)}
  </div>;
}
