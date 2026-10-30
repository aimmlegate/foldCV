import { useRef, useState } from "react";

const prefix = "foldcv.panel.";

/** A saved panel size in pixels, or null when the user has not chosen one. */
export function readPanelSize(name: string, minimum: number, maximum: number): number | null {
  try {
    const raw = localStorage.getItem(prefix + name), value = raw === null ? Number.NaN : Number(raw);
    return Number.isFinite(value) ? Math.min(maximum, Math.max(minimum, value)) : null;
  } catch { return null; }
}

export function savePanelSize(name: string, value: number | null): void {
  try {
    if (value === null) localStorage.removeItem(prefix + name);
    else localStorage.setItem(prefix + name, String(value));
  } catch { /* Resizing also works without browser storage. */ }
}

/** The draggable edge of a panel. `sign` is 1 when dragging right or down grows it; arrow keys step it, a double click resets it. */
export function PanelHandle({ label, axis, sign, value, minimum, maximum, change, reset, className = "" }: {
  label: string; axis: "x" | "y"; sign: 1 | -1; value: number; minimum: number; maximum: number;
  change: (value: number) => void; reset: () => void; className?: string;
}) {
  const origin = useRef<{ pointer: number; size: number } | null>(null), [dragging, setDragging] = useState(false);
  const clamp = (next: number) => Math.round(Math.min(maximum, Math.max(minimum, next)));
  const pointer = (event: { clientX: number; clientY: number }) => axis === "x" ? event.clientX : event.clientY;
  const grow = axis === "x" ? sign > 0 ? "ArrowRight" : "ArrowLeft" : sign > 0 ? "ArrowDown" : "ArrowUp";
  const shrink = axis === "x" ? sign > 0 ? "ArrowLeft" : "ArrowRight" : sign > 0 ? "ArrowUp" : "ArrowDown";
  return <div className={`panel-handle ${className}`} data-axis={axis} data-resizing={dragging} role="separator" tabIndex={0} aria-label={label}
    aria-orientation={axis === "x" ? "vertical" : "horizontal"} aria-valuemin={minimum} aria-valuemax={maximum} aria-valuenow={value}
    title="Потяните. Двойной щелчок вернёт размер." onDoubleClick={reset}
    onKeyDown={event => {
      const next = event.key === grow ? value + 16 : event.key === shrink ? value - 16 : event.key === "Home" ? minimum : event.key === "End" ? maximum : null;
      if (next !== null) { event.preventDefault(); change(clamp(next)); }
    }}
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId);
      origin.current = { pointer: pointer(event), size: value }; setDragging(true);
    }}
    onPointerMove={event => { if (origin.current) change(clamp(origin.current.size + sign * (pointer(event) - origin.current.pointer))); }}
    onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onLostPointerCapture={() => { origin.current = null; setDragging(false); }} />;
}
