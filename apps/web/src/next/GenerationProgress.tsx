import { ApiFailure, errorLabel, type Workspace } from "./api";

const labels = { extract: "Читаем исходник", normalize_semantics: "Разбираем факты", draft_prose: "Готовим резюме", assemble: "Проверяем и оформляем", render: "Проверяем и оформляем" };
const statuses = { queued: "Ожидает", running: "Выполняется", completed: "Готово", failed: "Ошибка", cancelled: "Отменено", interrupted: "Прервано" };

export function GenerationProgress({ generation, busy, control }: { generation: Workspace["generations"][number]; busy: boolean; control: (action: "cancel" | "retry") => void }) {
  const running = generation.status === "queued" || generation.status === "running";
  const failed = generation.status === "failed" || generation.status === "cancelled" || generation.status === "interrupted";
  const error = generation.stages.find(stage => stage.errorCode !== null && stage.docxError === null)?.errorCode;
  const importedWithWarning = generation.status === "completed" && generation.stages.some(stage => stage.docxError);
  const stages = generation.stages.filter(stage => stage.kind !== "render" || !generation.stages.some(item => item.kind === "assemble"))
    .map(stage => stage.kind === "assemble"
      ? { ...stage, status: generation.stages.find(item => (item.kind === "assemble" || item.kind === "render") && item.status !== "completed")?.status ?? stage.status }
      : stage);
  return <section className="next-progress" aria-label="Создание резюме">
    <p role="status">{running ? labels[generation.stages.find(stage => stage.status === "queued" || stage.status === "running")?.kind ?? "render"]
      : generation.status === "completed" ? "Резюме готово" : generation.status === "cancelled" ? "Создание отменено" : "Создание не завершено"}</p>
    <details open={running || failed}><summary>Этапы создания</summary><ol aria-label="Этапы создания">{stages.map(stage => <li key={stage.kind} data-stage={stage.kind} data-status={stage.status}>
      <span>{labels[stage.kind]}</span><span>{importedWithWarning && stage.kind === "assemble" ? "Предупреждение" : statuses[stage.status]}</span>
    </li>)}</ol></details>
    {running && <button disabled={busy} onClick={() => control("cancel")}>Отменить создание</button>}
    {failed && <button disabled={busy} onClick={() => control("retry")}>Повторить создание</button>}
    {error && generation.status !== "cancelled" && <p role="alert">{errorLabel(new ApiFailure(error))}</p>}
    {generation.stages.some(stage => stage.docxError) && <p role="alert">Документ готов. DOCX пока не удалось оформить; текст доступен для правок.</p>}
  </section>;
}
