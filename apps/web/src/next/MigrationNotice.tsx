const labels: Record<string, string> = {
  imported_locks_ignored: "Старые блокировки не действуют; перенесённый текст доступен для правок.",
  legacy_focus_to_text: "Свободный текст старого фокуса перенесён в навыки без подбора логотипов.",
  legacy_merged_blocks: "Видимые старые блоки объединены в сохранённом порядке. Скрытый текст оставлен для чтения.",
  legacy_ambiguous_job_prose: "Текст с неоднозначной привязкой к работе остался в исходном контексте; описание работы не заполнено автоматически.",
  legacy_language_unknown: "Язык источника не был указан. Для оформления выбран смешанный режим.",
  legacy_job_undo_history_only: "Старая предыдущая версия описания работы доступна для чтения. Она не восстанавливает весь новый блок опыта.",
  legacy_profile_undo_history_only: "Предыдущие версии нескольких старых профилей оставлены для чтения.",
  legacy_prior_fact_values_unavailable: "Предыдущий текст профиля сохранён, но старые значения некоторых фактов недоступны.",
  legacy_period_label: "Старые свободные подписи периодов оставлены для чтения. Поля дат перенесены из данных работы.",
  legacy_duration_not_reused: "Старые подписи длительности не используются. Новые значения доступны только при подтверждённых датах.",
  legacy_unmapped_sidebar: "Дополнительные боковые разделы остались в тексте переноса.",
  legacy_unmapped_achievement: "Отдельные достижения старого формата остались в тексте переноса.",
  legacy_unapplied_text: "Неприменённые правки доступны для чтения и не заменяют сохранённый текст.",
  legacy_formatting_date_unavailable: "Старая дата оформления недоступна. Сохранена дата открытия файла.",
};

export function MigrationNotice({ notices, showText }: { notices: string[]; showText: () => void }) {
  if (notices.length === 0) return null;
  const explanations = [...new Set(notices.map(code => labels[code]).filter((label): label is string => label !== undefined))];
  return <section className="next-message" aria-label="Перенос проекта">
    <p role="status">Проект открыт из файла. Исходники и перенесённый текст доступны для работы.</p>
    {explanations.length > 0 && <details><summary>Особенности переноса</summary><ul>{explanations.map(label => <li key={label}>{label}</li>)}</ul></details>}
    <button onClick={showText}>Показать текст переноса</button>
  </section>;
}
