export type AssistantCommand = { command: string; description: string };
export const assistantCommands: readonly AssistantCommand[] = [
  { command: "/skills", description: "Показать навыки помощника" },
  { command: "/import-resume", description: "Правила импорта резюме" },
  { command: "/format-resume", description: "Оформить по шаблону, не меняя текст" },
];

export function commandSuggestions(value: string, commands: readonly AssistantCommand[] = assistantCommands) {
  return /^\/[a-z-]*$/u.test(value) ? commands.filter(item => item.command.startsWith(value)) : [];
}

export function commandCompletion(value: string, selected: number, key: string, shift: boolean, composing: boolean,
  commands: readonly AssistantCommand[] = assistantCommands): string | null {
  if (shift || composing || (key !== "Enter" && key !== "Tab")) return null;
  const choice = commandSuggestions(value, commands)[selected];
  return choice && (key === "Tab" || choice.command !== value) ? choice.command + " " : null;
}
