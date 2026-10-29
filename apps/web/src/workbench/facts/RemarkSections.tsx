import { useId, useState } from "react";
import type { PlacedRemarks, Remark } from "../../rich/remarks";
import { Icon } from "../ui/Icon";
import { Button } from "../ui/Button";

/** A warning icon whose remarks show on hover and on keyboard focus; a click keeps them open, Escape closes them.
 * The remark text is the button's description, so a screen reader reads it with the button. */
export function RemarkMarker({ remarks, subject }: { remarks: readonly Remark[]; subject: string }) {
  const id = useId(), [hovered, setHovered] = useState(false), [focused, setFocused] = useState(false), [pinned, setPinned] = useState(false);
  const shown = hovered || focused || pinned;
  const [single] = remarks;
  if (!single) return null;
  return <span className="remark-marker" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    <button type="button" className="remark-marker-button" aria-label={`Замечаний: ${remarks.length}. ${subject}`}
      aria-describedby={id} aria-expanded={shown} onFocus={() => setFocused(true)} onBlur={() => { setFocused(false); setPinned(false); }}
      onClick={() => setPinned(value => !value)} onKeyDown={event => {
        if (event.key !== "Escape" || !shown) return;
        event.preventDefault(); event.stopPropagation(); setHovered(false); setFocused(false); setPinned(false);
      }}><Icon name="warning" /></button>
    <span role="tooltip" id={id} className="remark-tooltip" hidden={!shown}>
      {remarks.length === 1 ? single.message : remarks.map(remark => <span className="remark-line" key={remark.id}>{remark.message}</span>)}
    </span>
  </span>;
}

export type CheckState = { kind: "idle" } | { kind: "running" } | { kind: "failed"; message: string }
  | { kind: "done"; count: number; stale: boolean };

/** One section per resume section, named as in the document, after the five fact groups. */
export function RemarkSections({ remarks, show }: { remarks: PlacedRemarks; show: (blockId: string) => void }) {
  if (!remarks.sections.length && !remarks.unplaced.length) return null;
  return <section className="fact-group remark-sections" aria-labelledby="remark-sections-title">
    <h3 id="remark-sections-title" className="remark-sections-title">Разделы
      {remarks.count > 0 && <small>Замечаний: {remarks.count}</small>}</h3>
    <ul className="remark-section-list">
      {remarks.sections.map(section => <li key={section.id} className="remark-section" data-remark-section={section.id}>
        <div className="remark-row">
          <button type="button" className="remark-jump remark-section-name" title={section.title} disabled={section.focusId === null}
            onClick={() => { if (section.focusId) show(section.focusId); }}>{section.title}</button>
          <RemarkMarker remarks={section.remarks} subject={section.title} />
        </div>
        {section.items.length > 0 && <ul className="remark-items">{section.items.map(item => <li key={item.blockId} className="remark-row"
          data-remark-item={item.blockId}>
          <button type="button" className="remark-jump" title={item.label} onClick={() => show(item.focusId)}>{item.label || "Без текста"}</button>
          <RemarkMarker remarks={item.remarks} subject={item.label || "Без текста"} />
        </li>)}</ul>}
      </li>)}
      {remarks.unplaced.length > 0 && <li className="remark-section"><div className="remark-row">
        <span className="remark-section-name">Без раздела</span><RemarkMarker remarks={remarks.unplaced} subject="без раздела" />
      </div></li>}
    </ul>
  </section>;
}

/** The explicit check at the bottom of the panel; its findings join the section remarks above. */
export function CheckFooter({ state, run, disabled }: { state: CheckState; run: () => void; disabled: boolean }) {
  return <div className="facts-check">
    <Button disabled={disabled} busy={state.kind === "running"} busyLabel="Проверяем…" onClick={run}><Icon name="check" />Проверить резюме</Button>
    <p role="status" className={state.kind === "failed" ? "facts-check-status warning" : "facts-check-status"}>
      {state.kind === "failed" ? state.message
        : state.kind === "done" ? state.stale ? "Резюме изменилось. Проверьте снова."
          : state.count === 0 ? "Замечаний нет" : `Замечаний: ${state.count}` : ""}
    </p>
  </div>;
}
