import { assistantCommands, type AssistantCommand } from "../../assistant/commands";

/** The drawer's element ids, texts, commands and whether the edits switch shows. */
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
