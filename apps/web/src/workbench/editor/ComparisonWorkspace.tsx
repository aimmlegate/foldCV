import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Icon } from "../ui/Icon";

export type WorkspaceView = "layout" | "compare" | "original";

export function WorkspaceViews({ view, change, hasSource, notices }: { view: WorkspaceView; change: (view: WorkspaceView) => void; hasSource: boolean; notices: ReactNode }) {
  return <div className="workspace-view-bar">
    <span className="workspace-view-label">Рабочая область</span>
    <div className="workspace-views" role="group" aria-label="Режим просмотра">
      <button aria-pressed={view === "layout"} onClick={() => change("layout")}><Icon name="file" />Макет</button>
      <button aria-pressed={view === "compare"} disabled={!hasSource} onClick={() => change("compare")}><Icon name="panel" />Макет + оригинал</button>
      <button aria-pressed={view === "original"} disabled={!hasSource} onClick={() => change("original")}><Icon name="file" />Оригинал</button>
    </div>
    <div className="workspace-notices">{notices}</div>
  </div>;
}

export function ComparisonWorkspace({ view, layout, original }: { view: WorkspaceView; layout: ReactNode; original: ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(0.5), [width, setWidth] = useState(0), [dragging, setDragging] = useState(false);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const minimum = width > 10 ? Math.min(0.5, Math.max(0.25, 320 / (width - 10))) : 0.25;
  const clamp = (value: number) => Math.min(1 - minimum, Math.max(minimum, value));
  const fraction = clamp(ratio);
  const style: CSSProperties = { gridTemplateColumns: view === "compare" ? `${fraction}fr 10px ${1 - fraction}fr` : "minmax(0, 1fr)" };
  return <div className="comparison-viewport">
    <div ref={host} className="comparison-workspace" data-view={view} data-resizing={dragging} style={style}>
      <section className="workspace-pane layout-pane" aria-label="Макет резюме" hidden={view === "original"}>{layout}</section>
      <div className="workspace-divider" role="separator" tabIndex={0} aria-label="Ширина макета" aria-orientation="vertical"
        aria-valuemin={Math.round(minimum * 100)} aria-valuemax={Math.round((1 - minimum) * 100)} aria-valuenow={Math.round(fraction * 100)}
        aria-valuetext={`${Math.round(fraction * 100)}% макет, ${Math.round((1 - fraction) * 100)}% оригинал`}
        hidden={view !== "compare"} title="Потяните для изменения ширины. Двойной щелчок — поровну."
        onDoubleClick={() => setRatio(0.5)} onKeyDown={event => {
          const value = event.key === "ArrowLeft" ? fraction - 0.05 : event.key === "ArrowRight" ? fraction + 0.05
            : event.key === "Home" ? minimum : event.key === "End" ? 1 - minimum : null;
          if (value !== null) { event.preventDefault(); setRatio(clamp(value)); }
        }} onPointerDown={event => {
          if (event.button !== 0) return;
          event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); setDragging(true);
        }} onPointerMove={event => {
          const rect = host.current?.getBoundingClientRect();
          if (dragging && rect) setRatio(clamp((event.clientX - rect.left - 5) / (rect.width - 10)));
        }} onPointerUp={event => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
          setDragging(false);
        }} onLostPointerCapture={() => setDragging(false)} onPointerCancel={() => setDragging(false)} />
      <section className="workspace-pane original-pane" aria-label="Оригинал резюме" hidden={view === "layout"}>{original}</section>
    </div>
  </div>;
}
