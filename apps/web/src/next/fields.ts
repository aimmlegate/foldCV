import type { Document, AuthoredField } from "../contracts/generated/document";
import type { FieldProjection } from "./adapter";

export function documentFields(document: Document): FieldProjection[] {
  const fields: FieldProjection[] = [];
  const add = (slotId: string, label: string, field: AuthoredField) => fields.push({ slotId, label, fieldId: field.fieldId, text: field.text });
  add("candidate", "Имя", document.candidate.name);
  add("candidate", "Должность", document.candidate.title);
  add("candidate", "Местоположение", document.candidate.location);
  add("profile", "О специалисте", document.profile.text);
  for (const job of document.jobs) {
    const slot = `job:${job.id}`;
    add(slot, "Компания", job.employer); add(slot, "Роль", job.role);
    for (const period of job.periods) {
      add(slot, "Начало работы", period.startText); add(slot, "Окончание работы", period.endText);
    }
    add(slot, "Контекст", job.context); add(slot, "Задачи", job.tasks);
    add(slot, "Результаты", job.results); add(slot, "Стек", job.stack);
  }
  for (const row of document.education) {
    const slot = `education:${row.id}`;
    if (row.legacyText) add(slot, "Импортированный текст", row.legacyText);
    else { add(slot, "Учебное заведение", row.institution); add(slot, "Квалификация", row.qualification); add(slot, "Специальность", row.specialty); add(slot, "Дата", row.dateText); }
  }
  for (const row of document.certifications) {
    const slot = `certification:${row.id}`;
    if (row.legacyText) add(slot, "Импортированный текст", row.legacyText);
    else { add(slot, "Сертификат", row.name); add(slot, "Организация", row.issuer); add(slot, "Дата", row.dateText); }
  }
  for (const row of document.languages) {
    const slot = `language:${row.id}`;
    if (row.legacyText) add(slot, "Импортированный текст", row.legacyText);
    else { add(slot, "Язык", row.name); add(slot, "Уровень", row.proficiency); }
  }
  add("skills-focus", "Навыки", document.skillsFocus.skillsText);
  for (const focus of document.skillsFocus.focus) add("skills-focus", "Технология в фокусе", focus.display);
  add("early-career", "Ранний опыт", document.earlyCareer.text);
  return fields;
}
