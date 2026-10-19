import { assistantCommands } from "../../assistant/commands";

type Command = typeof assistantCommands[number];
export function CommandMenu({ choices, selected, choose }: { choices: readonly Command[]; selected: number; choose: (value: string) => void }) {
  return <div id="assistant-commands" className="chat-command-menu" role="listbox" aria-label="Команды помощника">
    <span className="chat-command-caption">Команды · ↑↓ выбрать · Tab вставить</span>
    {choices.map((item, index) => <button id={`assistant-command-${String(index)}`} key={item.command} type="button" role="option"
      aria-selected={index === selected} tabIndex={-1} onMouseDown={event => event.preventDefault()} onClick={() => choose(item.command + " ")}>
      <strong>{item.command}</strong><span>{item.description}</span>
    </button>)}
  </div>;
}
