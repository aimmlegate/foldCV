import type { useExport } from "./useExport";
import type { Workspace } from "./api";
import { documentFields } from "./fields";

const errors: Record<string, string> = {
  DOCX_NAME_LINE_LIMIT: "Имя занимает слишком много места. Сократите его.",
  DOCX_TITLE_LINE_LIMIT: "Должность занимает слишком много места. Сократите её.",
  DOCX_UNBREAKABLE_TEXT: "В тексте есть слишком длинное слово или строка без пробелов.",
  DOCX_BLOCK_PAGE_BUDGET: "Блок не помещается в макет. Сократите его.",
  DOCX_BLOCK_PLANNED_PAGE: "Блок не помещается на странице. Сократите его.",
  DOCX_UNKNOWN_FOCUS_ICON: "Для выбранной технологии нет значка.",
  DOCX_TEXT_LIMIT: "Текст поля слишком длинный для этого макета.",
  DOCX_LIST_LIMIT: "В разделе слишком много строк для этого макета.",
  DOCX_TOTAL_TEXT_LIMIT: "В документе слишком много текста для этого макета.",
  DOCX_INVALID_CHARACTER: "В тексте есть символ, который нельзя записать в DOCX.",
};
export function ExportPanel({ exporter, workspace }: { exporter: ReturnType<typeof useExport>; workspace: Workspace | null }) {
  const operation = exporter.state?.operation;
  const running = exporter.busy || operation?.status === "queued" || operation?.status === "running";
  const ready = operation?.status === "completed" && exporter.current;
  const error = operation?.docxError;
  const fieldId = error?.anchor.kind === "field" ? error.anchor.fieldId : null;
  const sectionId = error?.anchor.kind === "section" ? error.anchor.sectionId.split(":")[0] : null;
  const sections: Record<string, string> = { candidate: "Данные кандидата", profile: "О специалисте", employment: "Опыт работы",
    education: "Образование", certifications: "Сертификаты", languages: "Языки", "skills-focus": "Навыки и фокус",
    "early-career": "Ранний опыт", "document-sidebar": "Дополнительные сведения" };
  const label = fieldId && workspace?.project
    ? documentFields(workspace.project.document).find(field => field.fieldId === fieldId)?.label
      ?? (workspace.project.document.jobs.some(job => job.periodsFieldId === fieldId) ? "Периоды работы" : null)
    : sectionId ? sections[sectionId] : null;
  return <section className="next-export" aria-label="Экспорт DOCX">
    <button onClick={exporter.close}>К тексту</button>
    <p className="next-eyebrow">ГОТОВЫЙ ДОКУМЕНТ</p>
    <h1>{running ? "Оформляем резюме." : ready ? "DOCX готов." : "Продолжите с текстом."}</h1>
    <p>{ready ? "Файл содержит последние сохранённые правки. Его можно редактировать в Word." : "Текст доступен в редакторе. Сформируйте DOCX, когда будете готовы."}</p>
    {running && <p role="status">Формируем DOCX… <button disabled={!operation} onClick={() => { void exporter.cancel(); }}>Отменить оформление</button></p>}
    {ready && <div className="next-export-file"><strong>resume.docx</strong>
      <span>DOCX · {Math.ceil((exporter.state?.snapshot?.docx?.size ?? 0) / 1024)} КБ</span>
      <button disabled={exporter.downloading} onClick={() => { void exporter.download(); }}>{exporter.downloading ? "Скачиваем…" : "Скачать DOCX"}</button>
    </div>}
    {operation?.status === "completed" && !exporter.current && <p role="alert">Документ изменился. Сформируйте DOCX ещё раз.</p>}
    {operation?.status === "failed" && <p role="alert">{operation.errorCode === "EXPORT_STALE" ? "Документ изменился во время оформления. Сформируйте DOCX ещё раз."
      : error ? errors[error.code] ?? "Не удалось оформить DOCX. Текст доступен для правок." : "Не удалось оформить DOCX. Текст доступен для правок."}
      {label && <span> {fieldId ? "Поле" : "Раздел"}: {label}.</span>}</p>}
    {operation?.status === "cancelled" && <p role="status">Оформление отменено. Текст доступен в редакторе.</p>}
    {operation?.status === "interrupted" && <p role="status">Оформление прервано. Повторите, когда будете готовы.</p>}
    {exporter.message && <p role="alert">{exporter.message}</p>}
    {!running && !ready && <button onClick={() => { void exporter.start(); }}>Повторить оформление</button>}
    {ready && exporter.message && <button onClick={() => { void exporter.start(); }}>Сформировать заново</button>}
  </section>;
}
