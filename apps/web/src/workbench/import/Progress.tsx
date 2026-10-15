import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import { Icon } from "../ui/Icon";

const stages = ["assess_resume", "normalize_semantics", "assemble", "render"] as const;
const labels = ["Проверяем исходник", "Извлекаем факты", "Открываем исходный текст", "Готовим DOCX"];
export function Progress({ generation, sourceName, cancel, busy }: {
  generation: NonNullable<RichProjectResponse["generation"]>; sourceName: string; cancel: () => void; busy: boolean;
}) {
  const step = stages.findIndex(stage => stage === generation.stage);
  return <section className="progress-screen" aria-label="Обработка резюме"><div className="progress-content">
    <div className="progress-icon"><Icon name="fold" /></div><h2>Обработка резюме</h2><p className="muted">{sourceName}</p>
    <ol className="progress-list" aria-live="polite">{labels.map((label, index) => <li key={label} className={index < step ? "done" : index === step ? "current" : ""}>
      <span className="step-indicator">{index < step ? "✓" : index + 1}</span>{label}
    </li>)}</ol><button className="text-button" disabled={busy} onClick={cancel}>Отменить обработку</button>
  </div></section>;
}
