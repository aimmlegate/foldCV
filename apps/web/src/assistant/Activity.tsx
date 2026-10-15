import type { AssistantView } from "./controller";
import { runText } from "./presentation";
const tools: Record<string, string> = { web_search: "Поиск в интернете", get_resume_context: "Чтение резюме", find_resume_content: "Поиск в резюме",
  get_working_facts: "Чтение фактов", get_original_source: "Чтение исходника", get_conversation_context: "Чтение диалога", check_resume: "Проверка резюме",
  read_public_page: "Открытие страницы", publish_findings: "Сохранение замечаний", prepare_edit_batch: "Подготовка правок", apply_edit_batch: "Сохраняем изменения" };
export function Activity({ view }: { view: AssistantView }) {
  const last = [...view.activity].reverse().find(event => event.type.startsWith("tool."));
  return <div className="assistant-activity"><span role="status">{runText(view)}</span>{view.run && <small>Модель задачи: {view.run.model}</small>}
    {last && (last.type === "tool.started" || last.type === "tool.completed" || last.type === "tool.failed") && <small>{tools[last.payload.name] ?? "Работа с резюме"}{last.type === "tool.failed" ? " · не удалось выполнить" : ""}</small>}
    {view.receipts.map(receipt => <p key={receipt.batchId}>{receipt.durable && receipt.disposition === "saved" ? "Изменения сохранены · одна отмена"
      : receipt.disposition === "outcome_unknown" ? "Проверяем результат сохранения" : "Правки не применены"}</p>)}</div>;
}
