import { createContext, useMemo, useState, type ReactNode } from "react";
import type { Document } from "../contracts/generated/document";
import type { FieldProjection } from "./adapter";

type FieldStyle = { heading: string | null; hidden: boolean };
export const FieldLayout = createContext<ReadonlyMap<string, FieldStyle>>(new Map());
type Props = { document: Document; fields: readonly FieldProjection[]; activeSlot: string | null; tools: ReactNode;
  children: ReactNode; panels: ReactNode; panelOpen: boolean; focus: (fieldId?: string) => void; structure: () => void };

export function DocumentLayout({ document, fields, activeSlot, tools, children, panels, panelOpen, focus, structure }: Props) {
  const [collapsed, setCollapsed] = useState(false), [focused, setFocused] = useState(false);
  const navigation = [
    { section: "candidate", label: "Данные кандидата", slots: ["candidate"] },
    { section: "profile", label: "О специалисте", slots: ["profile"] },
    { section: "jobs", label: "Опыт работы", slots: document.jobs.map(job => `job:${job.id}`) },
    { section: "education", label: "Образование", slots: document.education.map(row => `education:${row.id}`) },
    { section: "certifications", label: "Сертификаты", slots: document.certifications.map(row => `certification:${row.id}`) },
    { section: "languages", label: "Языки", slots: document.languages.map(row => `language:${row.id}`) },
    { section: "skills-focus", label: "Навыки и фокус", slots: ["skills-focus"] },
    { section: "early-career", label: "Ранний опыт", slots: ["early-career"] },
  ];
  const styles = useMemo(() => {
    const hidden = new Set([
      ...(!document.profile.visible ? ["profile"] : []), ...(!document.skillsFocus.visible ? ["skills-focus"] : []),
      ...(!document.earlyCareer.visible ? ["early-career"] : []),
      ...document.jobs.filter(row => !row.visible).map(row => `job:${row.id}`),
      ...document.education.filter(row => !row.visible).map(row => `education:${row.id}`),
      ...document.certifications.filter(row => !row.visible).map(row => `certification:${row.id}`),
      ...document.languages.filter(row => !row.visible).map(row => `language:${row.id}`),
    ]);
    const labels: Record<string, string> = { candidate: "Данные кандидата", profile: "О специалисте", "skills-focus": "Навыки и фокус", "early-career": "Ранний опыт" };
    const rowLabels: Record<string, string> = { job: "Опыт работы", education: "Образование", certification: "Сертификат", language: "Язык" };
    const seen = new Set<string>(), values = new Map<string, FieldStyle>();
    for (const field of fields) {
      const kind = field.slotId.split(":")[0] ?? "";
      const heading = seen.has(field.slotId) ? null : labels[field.slotId] ?? rowLabels[kind] ?? "Раздел";
      values.set(field.fieldId, { heading, hidden: hidden.has(field.slotId) });seen.add(field.slotId);
    }
    return values;
  }, [document, fields]);
  return <section className="next-workspace" aria-label="Документ" data-focus-mode={focused} data-outline-collapsed={collapsed} data-panel-open={panelOpen}>
    <nav className="next-outline" aria-label="Разделы документа">
      <button aria-label={collapsed ? "Развернуть оглавление" : "Свернуть оглавление"} aria-expanded={!collapsed} onClick={() => setCollapsed(value => !value)}>{collapsed ? "→" : "В документе ←"}</button>
      <ol>{navigation.map(item => {
        const target = fields.find(field => item.slots.includes(field.slotId));
        return <li key={item.section}><button data-outline-section={item.section} aria-current={activeSlot && item.slots.includes(activeSlot) ? "location" : undefined}
          onClick={() => { if (target) focus(target.fieldId);else structure(); }}>{item.label}</button></li>;
      })}</ol>
    </nav>
    <div className="next-document-area">
      <div className="next-layout-controls" data-slot-owner={activeSlot ?? "profile"}>
        <span>Редактирование текста</span><button aria-pressed={focused} onPointerDown={event => event.preventDefault()}
          onClick={() => { setFocused(value => !value);focus(); }}>{focused ? "Выйти из режима фокуса" : "Режим фокуса"}</button>
      </div>
      <p className="next-editor-note">Правки сохраняются локально. «Сохранено» появляется после записи на диск.</p>
      {tools}
      <FieldLayout.Provider value={styles}><div className="next-document"><p className="next-paper-label">РЕЗЮМЕ СПЕЦИАЛИСТА</p>{children}</div></FieldLayout.Provider>
    </div>
    <div className="next-panel-dock">{panels}</div>
  </section>;
}
