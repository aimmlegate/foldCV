import type { AuthoredField, Document, DocumentPeriod, EducationRecord, JobRecord, LanguageRecord } from "../contracts/generated/document";
import type { StructuralIntent } from "./useEdits";

function field(fieldId: string): AuthoredField { return { fieldId, text: "", factIds: [], evidence: [], origin: "user" }; }
function period(slot: string): DocumentPeriod {
  const id = crypto.randomUUID();
  return { id, startText: field(`${slot}/period:${id}/startText`), endText: field(`${slot}/period:${id}/endText`), present: false };
}
function job(): JobRecord {
  const id = crypto.randomUUID(), slot = `job:${id}`;
  return { kind: "job", id, revision: 1, visible: true, employer: field(`${slot}/employer`), role: field(`${slot}/role`),
    periodsFieldId: `${slot}/periods`, periods: [], context: field(`${slot}/context`), tasks: field(`${slot}/tasks`),
    results: field(`${slot}/results`), stack: field(`${slot}/stack`), subprojectIds: [] };
}
function education(): EducationRecord {
  const id = crypto.randomUUID(), slot = `education:${id}`;
  return { kind: "education", id, revision: 1, visible: true, institution: field(`${slot}/institution`), qualification: field(`${slot}/qualification`),
    specialty: field(`${slot}/specialty`), dateText: field(`${slot}/dateText`), legacyText: null };
}
function language(): LanguageRecord {
  const id = crypto.randomUUID(), slot = `language:${id}`;
  return { kind: "language", id, revision: 1, visible: true, name: field(`${slot}/name`), proficiency: field(`${slot}/proficiency`), legacyText: null };
}
type Row = { id: string; kind: string; visible: boolean; label: string };
function Rows({ rows, section, send, disabled }: { rows: Row[]; section: "jobs" | "education" | "languages";
  send: (intent: StructuralIntent) => void; disabled: boolean;
}) {
  return <ul>{rows.map((row, index) => <li key={row.id} data-record-id={row.id}>
    <span>{row.label}{!row.visible ? " · скрыт из DOCX" : ""}</span>
    <button disabled={disabled} aria-label={`${row.visible ? "Скрыть" : "Показать"} ${row.label}`} onClick={() => send({ kind: "hide", payload: { slotId: `${row.kind}:${row.id}`, visible: !row.visible } })}>{row.visible ? "Скрыть" : "Показать"}</button>
    <button disabled={disabled || index === 0} aria-label={`Выше ${row.label}`} onClick={() => {
      const orderedIds = rows.map(row => row.id), previous = orderedIds[index - 1];
      if (!previous) return; orderedIds[index - 1] = row.id; orderedIds[index] = previous;
      send({ kind: "reorder", payload: { sectionId: section, orderedIds } });
    }}>Выше</button>
    <button disabled={disabled || index === rows.length - 1} aria-label={`Ниже ${row.label}`} onClick={() => {
      const orderedIds = rows.map(row => row.id), next = orderedIds[index + 1];
      if (!next) return; orderedIds[index + 1] = row.id; orderedIds[index] = next;
      send({ kind: "reorder", payload: { sectionId: section, orderedIds } });
    }}>Ниже</button>
    <button disabled={disabled} aria-label={`Удалить ${row.label}`} onClick={() => send({ kind: "delete", payload: { sectionId: section, recordId: row.id } })}>Удалить</button>
  </li>)}</ul>;
}
export function StructureControls({ document, send, periods, disabled }: { document: Document; send: (intent: StructuralIntent) => void;
  periods: (fieldId: string, update: (periods: DocumentPeriod[]) => DocumentPeriod[], slot: string) => void; disabled: boolean;
}) {
  return <details className="next-structure"><summary>Разделы и строки</summary>
    <section><h3>Работа</h3><button disabled={disabled} onClick={() => send({ kind: "add", payload: { sectionId: "jobs", record: job(), afterRecordId: null } })}>Добавить работу</button>
      <Rows section="jobs" rows={document.jobs.map((row, index) => ({ ...row, label: row.employer.text || `Работа ${index + 1}` }))} send={send} disabled={disabled} />
      {document.jobs.map((row, index) => <details key={row.id} data-period-job={row.id} data-slot-owner={`job:${row.id}`}><summary>Периоды: {row.employer.text || `Работа ${index + 1}`}</summary>
        <button disabled={disabled} onClick={() => { const added = period(`job:${row.id}`); periods(row.periodsFieldId, current => [...current, added], `job:${row.id}`); }}>Добавить период</button>
        {row.periods.map((period, index) => <div key={period.id}>
          <label><input type="checkbox" disabled={disabled} checked={period.present} onChange={event => {
            const present = event.target.checked;
            periods(row.periodsFieldId, current => current.map(item => item.id === period.id ? { ...item, present } : item), `job:${row.id}`);
          }} />По настоящее время · период {index + 1}</label>
          <button disabled={disabled || index === 0} onClick={() => periods(row.periodsFieldId, current => {
            const at = current.findIndex(item => item.id === period.id), previous = current[at - 1], selected = current[at];
            if (previous && selected) { const next = [...current]; next[at - 1] = selected; next[at] = previous; return next; } return current;
          }, `job:${row.id}`)}>Период выше</button>
          <button disabled={disabled} onClick={() => periods(row.periodsFieldId, current => current.filter(item => item.id !== period.id), `job:${row.id}`)}>Удалить период</button>
        </div>)}
      </details>)}
    </section>
    <section><h3>Образование</h3><button disabled={disabled} onClick={() => send({ kind: "add", payload: { sectionId: "education", record: education(), afterRecordId: null } })}>Добавить образование</button>
      <Rows section="education" rows={document.education.map((row, index) => ({ ...row, label: row.legacyText?.text || row.institution.text || `Образование ${index + 1}` }))} send={send} disabled={disabled} />
    </section>
    <section><h3>Языки</h3><button disabled={disabled} onClick={() => send({ kind: "add", payload: { sectionId: "languages", record: language(), afterRecordId: null } })}>Добавить язык</button>
      <Rows section="languages" rows={document.languages.map((row, index) => ({ ...row, label: row.legacyText?.text || row.name.text || `Язык ${index + 1}` }))} send={send} disabled={disabled} />
    </section>
    <section><h3>Видимость разделов</h3>{[
      { slot: "profile", record: document.profile, label: "О специалисте" },
      { slot: "skills-focus", record: document.skillsFocus, label: "Навыки и фокус" },
      { slot: "early-career", record: document.earlyCareer, label: "Ранний опыт" },
      ...document.certifications.map(row => ({ slot: `certification:${row.id}`, record: row, label: row.name.text || "Сертификат" })),
    ].map(({ slot, record, label }) => <button key={slot} disabled={disabled} onClick={() => send({ kind: "hide", payload: { slotId: slot, visible: !record.visible } })}>{record.visible ? "Скрыть" : "Показать"} {label}</button>)}</section>
  </details>;
}
