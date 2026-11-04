import { assistantCommands, templateCommands, type AssistantCommand } from "../../assistant/commands";

/** What differs between the resume drawer and the templates one: element ids (both can be mounted at once), texts,
 * commands and whether the edits switch shows. */
export type ChatScope = {
  host: string; content: string; threads: string; input: string; commands: string; option: string; model: string;
  access: (allowEdits: boolean) => string; empty: string; question: string; placeholder: string;
  commandList: readonly AssistantCommand[]; edits: boolean;
};
// An empty chat asks a plain question instead of offering ready prompts (D139).
export const resumeScope: ChatScope = { host: "agent-chat-host", content: "assistant-content", threads: "chat-threads", input: "chat-input",
  commands: "assistant-commands", option: "assistant-command", model: "chat-model", access: allowEdits => allowEdits ? "Правки разрешены" : "Только чтение",
  empty: "Чат по резюме", question: "Что вы хотите изменить или проверить в резюме? Напишите вопрос ниже.",
  placeholder: "Что проверить или изменить? / — команды", commandList: assistantCommands, edits: true };
export const templateScope: ChatScope = { host: "template-chat-host", content: "template-assistant-content", threads: "template-chat-threads",
  input: "template-chat-input", commands: "template-assistant-commands", option: "template-assistant-command", model: "template-chat-model", access: () => "Без доступа к резюме",
  empty: "Что изменить в шаблоне?", question: "Например: «имя крупнее, без линии под шапкой». Помощник видит шаблоны и образцы, но не резюме; правка придёт предложением с разницей.",
  placeholder: "Что изменить в шаблоне? / — команды", commandList: templateCommands, edits: false };
