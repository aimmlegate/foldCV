import type { ReactNode } from "react";

/** The sections of Settings in nav order (D147). Limits have no item: their saved or default values still apply. */
export type SettingsSection = "connection" | "models" | "assistant" | "rules" | "appearance";
export const settingsSections: readonly { id: SettingsSection; label: string }[] = [{ id: "connection", label: "Подключение" },
  { id: "models", label: "Модели" }, { id: "assistant", label: "Помощник" }, { id: "rules", label: "Команды" }, { id: "appearance", label: "Оформление" }];

/** A bordered group of setting rows; the title is an eyebrow inside the border. */
export function SettingsGroup({ title, children }: { title?: string; children: ReactNode }) {
  return <section className="settings-group" aria-label={title}>
    {title && <h4 className="settings-group-title eyebrow">{title}</h4>}
    {children}
  </section>;
}

/** One setting: the label and its hint at the left, the control at the right; `note` shows under the row. */
export function SettingsRow({ label, hint, htmlFor, children, note }: {
  label: ReactNode; hint?: ReactNode; htmlFor?: string; children: ReactNode; note?: ReactNode;
}) {
  return <div className="settings-row">
    <div className="settings-row-copy">{htmlFor ? <label htmlFor={htmlFor}>{label}</label> : <span className="settings-row-label">{label}</span>}
      {hint && <p>{hint}</p>}</div>
    <div className="settings-row-control">{children}</div>
    {note && <div className="settings-row-note">{note}</div>}
  </div>;
}
