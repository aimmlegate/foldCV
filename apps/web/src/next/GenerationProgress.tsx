import type { Workspace } from "./api";

const labels = { extract: "Читаем исходник", normalize_semantics: "Разбираем факты", draft_prose: "Готовим резюме", assemble: "Проверяем документ", render: "Оформляем DOCX" };
const statuses = { queued: "Ожидает", running: "Выполняется", completed: "Готово", failed: "Ошибка", cancelled: "Отменено", interrupted: "Прервано" };

export function GenerationProgress({ generation, busy, control }: { generation: Workspace["generations"][number]; busy: boolean; control: (action: "cancel" | "retry") => void }) {
  const running = generation.status === "queued" || generation.status === "running";
  const failed = generation.status === "failed" || generation.status === "cancelled" || generation.status === "interrupted";
  return <section className="next-progress" aria-label="Создание резюме">
    <p role="status">{running ? labels[generation.stages.find(stage => stage.status === "queued" || stage.status === "running")?.kind ?? "render"]
      : generation.status === "completed" ? "Резюме готово" : generation.status === "cancelled" ? "Создание отменено" : "Создание не завершено"}</p>
    <details open={running || failed}><summary>Этапы создания</summary><ol aria-label="Этапы создания">{generation.stages.map(stage => <li key={stage.kind} data-stage={stage.kind} data-status={stage.status}>
      <span>{labels[stage.kind]}</span><span>{statuses[stage.status]}</span>
    </li>)}</ol></details>
    {running && <button disabled={busy} onClick={() => control("cancel")}>Отменить создание</button>}
    {failed && <button disabled={busy} onClick={() => control("retry")}>Повторить создание</button>}
    {generation.stages.some(stage => stage.docxError) && <p role="alert">Документ готов. DOCX пока не удалось оформить; текст доступен для правок.</p>}
  </section>;
}
