import { useEffect, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";

export function NoticePanel({ count, label = "Замечания", attention = "", children }: {
  count: number; label?: string; attention?: string; children: ReactNode;
}) {
  const root = useRef<HTMLDetailsElement>(null);
  useEffect(() => { if (attention && root.current) root.current.open = true; }, [attention]);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target) && root.current) root.current.open = false; };
    document.addEventListener("pointerdown", outside); return () => document.removeEventListener("pointerdown", outside);
  }, []);
  if (!count) return null;
  return <details className="notice-control" ref={root} onToggle={event => {
    const current = event.currentTarget;
    if (current.open) current.parentElement?.querySelectorAll<HTMLDetailsElement>(".notice-control[open]").forEach(other => { if (other !== current) other.open = false; });
  }} onKeyDown={event => {
    if (event.key === "Escape" && root.current?.open) { event.preventDefault(); event.stopPropagation(); root.current.open = false; root.current.querySelector("summary")?.focus(); }
  }}><summary><Icon name="info" /><span>{label}</span><span className="notice-count">{count}</span></summary>
    <section className="notice-panel" aria-label={label}><div className="notice-panel-heading"><strong>{label}</strong><button type="button" className="icon" aria-label={`Скрыть: ${label}`} onClick={() => { if (root.current) { root.current.open = false; root.current.querySelector("summary")?.focus(); } }}><Icon name="close" /></button></div>{children}</section>
  </details>;
}
