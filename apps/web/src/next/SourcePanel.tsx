import type { SourceContext } from "../contracts/generated/source_context";
import type { Workspace } from "./api";

const relations = { exact: "Совпадает с выделением", field: "Источник поля", block: "Контекст блока" };
const statuses = { "user-origin": "Этот текст добавлен пользователем. Источника для него нет.",
  "no-evidence": "Для этого фрагмента нет сохранённого источника.",
  stale: "Выделение устарело или текст изменён. Выделите фрагмент снова после сохранения." };
const legacyLabels: Record<string, string> = { unapplied_draft: "Неприменённая правка", unapplied_form: "Неприменённый текст",
  unapplied_presentation: "Неприменённые данные кандидата", unapplied_input: "Сохранённый ввод", unapplied_education: "Неприменённое образование",
  legacy_profile: "Старый профиль", legacy_previous_profile: "Предыдущий профиль", legacy_job_prose: "Старое описание работы",
  legacy_previous_job_prose: "Предыдущее описание работы", legacy_education: "Старое образование", legacy_focus: "Старый фокус",
  legacy_skills: "Старые навыки", contact: "Контактные данные из старого файла", unapplied_proposal: "Неприменённое предложение" };
export function SourcePanel({ context, workspace, loading, close }: {
  context: SourceContext | null; workspace: Workspace; loading: boolean; close: () => void;
}) {
  return <aside className="next-source-panel" aria-label="Исходный контекст" onKeyDown={event => { if (event.key === "Escape") { event.preventDefault();close(); } }}>
    <p className="next-panel-eyebrow">СОХРАНЁННЫЙ ИСХОДНИК</p>
    <header><h2>Исходный контекст</h2><button onClick={close} aria-label="Закрыть исходный контекст">Закрыть</button></header>
    {loading && <p role="status">Читаем сохранённые источники…</p>}
    {context && context.status !== "evidence" && <p role="status">{statuses[context.status]}</p>}
    {context?.excerpts.map((excerpt, index) => <section key={index} data-source-relation={excerpt.relation}>
      <p className="next-source-reference">{relations[excerpt.relation]} · {workspace.project?.sources.find(source => source.id === excerpt.evidence.sourceId)?.originalName ?? "Исходник"}
        {excerpt.page !== null ? ` · стр. ${excerpt.page + 1}` : ""}</p>
      <blockquote>{excerpt.evidence.text}</blockquote>
    </section>)}
    {context?.annotations.length ? <section><h3>Связанные отметки</h3>{context.annotations.map(mark => <p key={mark.id}
      data-source-annotation={mark.code}>{mark.type === "conflicting" ? "В исходнике есть противоречие. Обе версии сохранены." : "В этом блоке есть сведения для уточнения."}</p>)}</section> : null}
    {context?.legacyText.map(item => <section key={item.id} data-legacy-kind={item.originalKind}><h3>{legacyLabels[item.originalKind] ?? item.label}</h3><p className="next-related-text">{item.text}</p></section>)}
  </aside>;
}
