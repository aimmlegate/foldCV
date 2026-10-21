import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";

export function LayoutControls({ comparing, expand }: { comparing: boolean; expand: () => void }) {
  const controls = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState("1.25");
  useEffect(() => {
    const workspace = controls.current?.closest<HTMLElement>(".document-workspace");
    const scroll = workspace?.querySelector<HTMLElement>(".paper-scroll"), paper = scroll?.querySelector<HTMLElement>(".resume-paper");
    if (!workspace || !scroll || !paper) return;
    const fit = () => {
      if (!scroll.clientWidth || !paper.offsetWidth) return;
      const scale = zoom === "fit" ? Math.min(1, Math.max(0.1, (scroll.clientWidth - 48) / paper.offsetWidth)) : Number(zoom);
      workspace.style.setProperty("--document-zoom", String(scale));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(scroll); fit();
    return () => observer.disconnect();
  }, [zoom]);
  return <div ref={controls} className="tool-group layout-controls">
    <select className="toolbar-select" aria-label="Масштаб макета" value={zoom} onChange={event => setZoom(event.currentTarget.value)}>
      <option value="fit">По ширине</option><option value="0.75">75%</option><option value="1">100%</option><option value="1.25">125%</option>
    </select>
    {comparing && <button className="tool" aria-label="Развернуть макет" title="Развернуть макет" onClick={expand}><Icon name="expand" /></button>}
  </div>;
}
