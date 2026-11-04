import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/Spinner";

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

/** A row's save state at the left of its control: a spinner while it saves, then «Сохранено» for two seconds. */
export function RowState({ pending, at }: { pending: boolean; at: number | undefined }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const left = at === undefined ? 0 : at + 2000 - Date.now();
    setShown(left > 0);
    if (left <= 0) return;
    const timer = setTimeout(() => setShown(false), left);
    return () => clearTimeout(timer);
  }, [at]);
  return <span className="settings-row-state" role="status">{pending ? <Spinner /> : shown && <><Icon name="check" />Сохранено</>}</span>;
}
