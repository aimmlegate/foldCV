import { assistantCommands, templateCommands, type AssistantCommand } from "../../assistant/commands";

/** What differs between the resume drawer and the templates one: element ids (both can be mounted at once), texts,
 * commands and whether the edits switch shows. */
export type ChatScope = {
  host: string; content: string; threads: string; input: string; commands: string; option: string; model: string;
  access: (allowEdits: boolean) => string; empty: string; suggestions: readonly string[]; placeholder: string;
  commandList: readonly AssistantCommand[]; edits: boolean;
};
export const resumeScope: ChatScope = { host: "agent-chat-host", content: "assistant-content", threads: "chat-threads", input: "chat-input",
  commands: "assistant-commands", option: "assistant-command", model: "chat-model", access: allowEdits => allowEdits ? "Правки разрешены" : "Только чтение",
  empty: "Чат по резюме", suggestions: ["Проверь резюме", "Сократи текст", "Сравни с вакансией"],
  placeholder: "Что проверить или изменить? / — команды", commandList: assistantCommands, edits: true };
export const templateScope: ChatScope = { host: "template-chat-host", content: "template-assistant-content", threads: "template-chat-threads",
  input: "template-chat-input", commands: "template-assistant-commands", option: "template-assistant-command", model: "template-chat-model", access: () => "Без доступа к резюме",
  empty: "Чат по шаблону", suggestions: ["Сделай имя крупнее", "Сделай шаблон по образцу", "Найди ошибки в шаблоне"],
  placeholder: "Что изменить в шаблоне? / — команды", commandList: templateCommands, edits: false };
