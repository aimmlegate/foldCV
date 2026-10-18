import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";

type Generation = NonNullable<RichProjectResponse["generation"]>;
type Source = NonNullable<RichProjectResponse["workspace"]["preDraft"]>["sources"][number];

const messages: Readonly<Record<string, string>> = {
  source_not_resume: "Содержимое может не быть резюме. Проверьте исходник; обработка продолжена.",
  source_resume_uncertain: "Тип содержимого определён неуверенно. Проверьте исходник; обработка продолжена.",
  source_details_unresolved: "Некоторые сведения не извлечены. Сверьте факты с исходником и исправьте их или повторите обработку.",
  IMAGE: "Изображения не распознаются как текст. Проверьте, нет ли в них важных сведений; добавьте их текстом.",
  NO_TEXT: "Текст не найден. Для скана добавьте распознанный текст или выберите текстовый PDF/DOCX.",
  NO_USABLE_TEXT: "Нет доступного текста для обработки. Выберите текстовый файл или вставьте текст.",
  EXTRACT_MALFORMED: "Файл повреждён или не соответствует формату. Пересохраните его и загрузите снова.",
  EXTRACT_ENCRYPTED: "Файл защищён паролем. Загрузите копию без пароля.",
  EXTRACT_UNSUPPORTED: "Содержимое файла не поддерживается. Используйте PDF, DOCX, TXT или Markdown.",
  INPUT_TOO_LARGE: "Полный запрос превышает 256 КиБ. Уберите ненужные вложения или повторите обработку меньшего исходника; текст не обрезан.",
  INVALID_RESULT: "Модель вернула непригодный ответ. Исходник сохранён; повторите обработку.",
  FACT_EXTRACTION_EMPTY: "Модель не извлекла ни одного подтверждённого факта. Исходник сохранён; повторите обработку.",
  TIMEOUT: "Модель не ответила за 180 секунд. Повторите обработку явно.",
  DEADLINE: "Истекло время этапа. Исходник сохранён; повторите обработку.",
  PROCESS_TIMEOUT: "Модель не ответила за 180 секунд. Повторите обработку явно.",
  OPERATION_TIMEOUT: "Истекло время этапа. Исходник сохранён; повторите обработку.",
  CANCELLED: "Обработка отменена. Исходник сохранён; можно запустить её снова.",
  OPERATION_INTERRUPTED: "Обработка прервана. Исходник сохранён; повторите обработку.",
};

export function warningLabel(code: string): string {
  return messages[code] ?? `Код ${code}. Проверьте соответствующий исходник; при необходимости исправьте его и повторите обработку.`;
}

export function groupedWarnings(codes: readonly string[], sources: readonly Source[] = []): string[] {
  const counts = new Map<string, number>();
  for (const code of codes) counts.set(code, (counts.get(code) ?? 0) + 1);
  return [...counts].map(([code, count]) => {
    const pages = sources.flatMap(source => (source.warningDetails ?? []).filter(item => item.code === code)
      .map(item => `${source.originalName}${item.page ? `, стр. ${item.page}` : ""}`));
    return `${warningLabel(code)}${count > 1 ? ` Повторов: ${count}.` : ""}${pages.length ? ` ${[...new Set(pages)].join("; ")}.` : ""}`;
  });
}

export function processingFailure(generation: Generation | null | undefined): string | null {
  if (!generation || !["failed", "cancelled", "interrupted"].includes(generation.status)) return null;
  const stages: Readonly<Record<string, string>> = { assess_resume: "Проверка исходника", normalize_semantics: "Извлечение фактов", assemble: "Оформление", render: "Подготовка DOCX" };
  const code = generation.errorCode ?? (generation.status === "cancelled" ? "CANCELLED" : "OPERATION_INTERRUPTED");
  return `${stages[generation.stage] ?? generation.stage}: ${warningLabel(code)} (${code})`;
}
