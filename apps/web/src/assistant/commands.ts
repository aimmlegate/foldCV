export const assistantCommands = [
  { command: "/skills", description: "Показать навыки помощника" },
  { command: "/import-resume", description: "Правила импорта резюме" },
  { command: "/format-resume", description: "Оформить по шаблону, не меняя текст" },
] as const;

export function commandSuggestions(value: string) {
  return /^\/[a-z-]*$/u.test(value) ? assistantCommands.filter(item => item.command.startsWith(value)) : [];
}

export function commandCompletion(value: string, selected: number, key: string, shift: boolean, composing: boolean): string | null {
  if (shift || composing || (key !== "Enter" && key !== "Tab")) return null;
  const choice = commandSuggestions(value)[selected];
  return choice && (key === "Tab" || choice.command !== value) ? choice.command + " " : null;
}
