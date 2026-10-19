export const assistantCommands = [
  { command: "/skills", description: "Показать доступные скилы" },
  { command: "/import-resume", description: "Использовать правила импорта и обработки резюме" },
  { command: "/format-resume", description: "Оформить по текущему шаблону без изменения текста" },
] as const;

export function commandSuggestions(value: string) {
  return /^\/[a-z-]*$/u.test(value) ? assistantCommands.filter(item => item.command.startsWith(value)) : [];
}

export function commandCompletion(value: string, selected: number, key: string, shift: boolean, composing: boolean): string | null {
  if (shift || composing || (key !== "Enter" && key !== "Tab")) return null;
  const choice = commandSuggestions(value)[selected];
  return choice && (key === "Tab" || choice.command !== value) ? choice.command + " " : null;
}
