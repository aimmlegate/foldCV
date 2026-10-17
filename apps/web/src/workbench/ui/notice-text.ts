export function noticeText(message: string): string {
  if (/^(?:DRAFT_|WRITER_|JOB_SCOPE_INVALID|AGENT_OUTCOME_UNKNOWN|OUTCOME_UNKNOWN)/u.test(message))
    return "Не удалось восстановить черновик. Повторите попытку или выберите сохранённую версию.";
  if (/^[A-Z][A-Z0-9_]+$/u.test(message) || /Failed to fetch|NetworkError|Load failed/u.test(message))
    return "Не удалось завершить действие. Проверьте подключение и повторите попытку.";
  return message;
}
