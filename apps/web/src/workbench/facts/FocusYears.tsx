import { useEffect, useRef, useState } from "react";
import type { PanelCommand } from "../../rich/v7-panel";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/OperationStatus";
import { Button } from "../ui/Button";
import { useTechnologyDrag } from "./useTechnologyDrag";

export type FocusEntry = { recordId: string; display: string; years: number | null };
type Entry = FocusEntry;

function YearsRow({ entry, paused, submit, drag }: { entry: Entry; paused: boolean; submit: (command: PanelCommand) => Promise<void>;
  drag: ReturnType<typeof useTechnologyDrag> }) {
  const saved = entry.years === null ? "" : String(entry.years);
  const [value, setValue] = useState(saved), [busy, setBusy] = useState(false);
  const running = useRef(false);
  useEffect(() => { setValue(saved); }, [saved]);
  async function save() {
    if (paused || running.current || value === saved || value !== "" && (!Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 100)) return;
    running.current = true; setBusy(true);
    try { await submit({ operation: "edit", recordId: entry.recordId, values: { experience: value } }); }
    catch { /* The facts panel shows the save error and keeps this draft. */ }
    finally { running.current = false; setBusy(false); }
  }
  async function remove() {
    if (paused || running.current) return;
    running.current = true; setBusy(true);
    try { await submit({ operation: "remove_from_focus", recordId: entry.recordId }); }
    catch { /* The facts panel shows the error. */ }
    finally { running.current = false; setBusy(false); }
  }
  return <form className="focus-years-row" {...drag.target(entry.recordId)} onSubmit={event => { event.preventDefault(); void save(); }}>
    <button type="button" className="technology-drag" aria-label={`Порядок в фокусе: ${entry.display}`} title="Перетащите или нажмите Alt+↑ / Alt+↓"
      disabled={paused || busy} {...drag.handle(entry.recordId)}><span aria-hidden="true">⠿</span></button>
    <label htmlFor={`focus-years-${entry.recordId}`}>{entry.display}</label>
    <input id={`focus-years-${entry.recordId}`} aria-label={`Лет опыта: ${entry.display}`} type="number" min={0} max={100} step={1}
      inputMode="numeric" placeholder="Лет" value={value} disabled={paused || busy}
      onChange={event => setValue(event.target.value)} onBlur={() => { void save(); }} />
    <button type="submit" className="text-button" aria-label={`Сохранить срок: ${entry.display}`} aria-busy={busy} disabled={paused || busy || value === saved}>{busy ? <Spinner /> : "✓"}</button>
    <button type="button" className="icon" aria-label={`Убрать из фокуса: ${entry.display}`} disabled={paused || busy}
      onMouseDown={event => event.preventDefault()} onClick={() => { void remove(); }}><Icon name="close" /></button>
  </form>;
}

export function FocusYears({ entries, options, paused, submit }: { entries: readonly Entry[]; options: readonly Entry[]; paused: boolean; submit: (command: PanelCommand) => Promise<void> }) {
  const [selected, setSelected] = useState(""), [busy, setBusy] = useState(false);
  const running = useRef(false);
  const choice = options.some(option => option.recordId === selected) ? selected : options[0]?.recordId ?? "";
  const drag = useTechnologyDrag(entries.map(entry => entry.recordId), "move_focus", paused || busy, submit);
  async function add() {
    if (paused || running.current || !choice) return;
    running.current = true; setBusy(true);
    try { await submit({ operation: "add_to_focus", recordId: choice }); }
    catch { /* The facts panel shows the error. */ }
    finally { running.current = false; setBusy(false); }
  }
  return <div className="focus-years" aria-label="Фокус в резюме">
    <p className="technology-label">Фокус в резюме · лет опыта</p>
    {entries.map(entry => <YearsRow key={entry.recordId} entry={entry} paused={paused} submit={submit} drag={drag} />)}
    {drag.dragging && <div className="technology-drop-end" {...drag.target(null)}>В конец списка</div>}
    {options.length > 0 && <form className="focus-add" onSubmit={event => { event.preventDefault(); void add(); }}>
      <select aria-label="Технология для фокуса" value={choice} disabled={paused || busy} onChange={event => setSelected(event.target.value)}>
        {options.map(option => <option key={option.recordId} value={option.recordId}>{option.display}</option>)}
      </select>
      <Button type="submit" variant="quiet" busy={busy} busyLabel="Добавляем…" disabled={paused}>Добавить в фокус</Button>
    </form>}
  </div>;
}
