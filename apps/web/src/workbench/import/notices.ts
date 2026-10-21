import { errorMessage } from "../../errors/messages";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";

type Generation = NonNullable<RichProjectResponse["generation"]>;
type Source = NonNullable<RichProjectResponse["workspace"]["preDraft"]>["sources"][number];

export function warningLabel(code: string): string {
  return errorMessage(code, "В исходнике есть сведения, которые требуют проверки. Проверьте текст и факты.");
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
  return `${stages[generation.stage] ?? "Обработка"}: ${warningLabel(code)}`;
}
