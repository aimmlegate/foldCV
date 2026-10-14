import { createContext, useContext } from "react";
import type { Annotation, RelatedUpdateSuggestion } from "../contracts/generated/workspace_v5";
import type { FieldProjection } from "./adapter";

type LocatedMark = { mark: Annotation; label: string };
export const AnnotationContext = createContext<ReadonlyMap<string, readonly LocatedMark[]>>(new Map());
type Actions = { suggestions: readonly RelatedUpdateSuggestion[]; fields: readonly FieldProjection[];
  projectRevision: number; documentRevision: number; disabled: boolean; apply: (suggestion: RelatedUpdateSuggestion) => void };
export const AnnotationActions = createContext<Actions | null>(null);
const labels: Readonly<Record<string, string>> = {
  missing_surname: "Фамилия не указана в исходнике",
  missing_education: "Образование не указано",
  missing_languages: "Языки не указаны",
  missing_job_dates: "Уточните даты работы",
  team_size_conflict: "В исходнике указаны разные размеры команды",
  focus_entry_removed: "Часть технологий исключена из фокуса",
  source_details_unresolved: "Часть данных не разобрана. Проверьте сохранённый исходник",
  editorial_plan_stale: "Редакторские рекомендации требуют обновления",
  name_assessment_stale: "Имя изменено. Оценку фамилии нужно обновить",
};
const sectionSlots: Readonly<Record<string, readonly string[]>> = {
  education: ["education:", "certification:", "language:", "skills-focus"],
  languages: ["language:", "skills-focus"],
  "skills-focus": ["skills-focus"],
};

export function locateAnnotations(fields: readonly FieldProjection[], annotations: readonly Annotation[]): ReadonlyMap<string, readonly LocatedMark[]> {
  const located = new Map<string, LocatedMark[]>();
  for (const mark of annotations) {
    if (mark.resolved) continue;
    const anchor = mark.anchor;
    let field: FieldProjection | undefined;
    if (anchor.kind === "field") {
      field = fields.find(field => field.fieldId === anchor.fieldId);
      if (!field && anchor.fieldId.endsWith("/periods")) {
        const slot = anchor.fieldId.slice(0, -"/periods".length);
        field = fields.find(field => field.slotId === slot && field.fieldId.includes("/period:"))
          ?? fields.find(field => field.slotId === slot);
      }
    } else if (anchor.kind === "section") {
      for (const prefix of sectionSlots[anchor.sectionId] ?? []) {
        field = fields.find(field => field.slotId.startsWith(prefix));
        if (field) break;
      }
    } else field = fields[0];
    if (!field) continue;
    const items = located.get(field.fieldId) ?? [];
    items.push({ mark, label: labels[mark.code] ?? "Проверьте этот фрагмент" });
    located.set(field.fieldId, items);
  }
  return located;
}

export function FieldAnnotations({ fieldId }: { fieldId: string }) {
  const marks = useContext(AnnotationContext).get(fieldId) ?? [];
  const actions = useContext(AnnotationActions);
  const owner = actions?.fields.find(field => field.fieldId === fieldId)?.slotId;
  return <>{marks.map(({ mark, label }) => {
    const suggestion = actions?.suggestions.find(item => item.id === mark.updateSuggestionId);
    const stale = !!suggestion && (suggestion.dependencies.projectRevision !== actions?.projectRevision
      || suggestion.dependencies.documentRevision !== actions.documentRevision);
    return <div key={mark.id} className="next-annotation" contentEditable={false} data-slot-owner={owner}
    role="note" data-annotation-id={mark.id} data-annotation-type={mark.type} data-annotation-code={mark.code}
    data-section-id={mark.anchor.kind === "section" ? mark.anchor.sectionId : undefined}
    data-anchor-field={mark.anchor.kind === "field" ? mark.anchor.fieldId : undefined}>
    <span>{label}</span>
    {mark.type === "conflicting" && <span className="next-annotation-detail">{mark.code.startsWith("reconcile_") || mark.code === "restore_shared_fact_conflict"
      ? "В этом фрагменте осталось другое упоминание. Рабочие факты уже обновлены."
      : "Обе версии сохранены в фактах; ни одна не добавлена в текст."}</span>}
    {mark.removedFocus.length > 0 && <span className="next-annotation-detail">Исключено: {mark.removedFocus.length}</span>}
    {suggestion && <details className="next-annotation-update"><summary>Связанные изменения</summary>
      <p>{suggestion.reason}</p>
      {suggestion.replacements.map(replacement => <div key={replacement.fieldId}>
        <strong>{actions?.fields.find(field => field.fieldId === replacement.fieldId)?.label ?? "Текст"}</strong>
        <p className="next-related-text">{replacement.text}</p>
      </div>)}
      {stale && <p>Предложение устарело. Завершите правку и дождитесь новой проверки.</p>}
      <button disabled={stale || actions?.disabled} onClick={() => actions?.apply(suggestion)}>Обновить связанный текст</button>
    </details>}
  </div>;
  })}</>;
}
