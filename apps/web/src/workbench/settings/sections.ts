/** The sections of Settings in nav order (D147). Limits have no item: their saved or default values still apply. */
export type SettingsSection = "connection" | "models" | "assistant" | "rules" | "appearance";
export const settingsSections: readonly { id: SettingsSection; label: string }[] = [{ id: "connection", label: "Подключение" },
  { id: "models", label: "Модели" }, { id: "assistant", label: "Помощник" }, { id: "rules", label: "Команды" }, { id: "appearance", label: "Оформление" }];
