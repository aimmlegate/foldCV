import { useEffect, useRef, useState } from "react";
import type { PanelCommand } from "../../rich/v7-panel";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/OperationStatus";
import { Button } from "../ui/Button";
import { useTechnologyDrag } from "./useTechnologyDrag";
import { yearsValue } from "../../rich/v7-focus";

/** One Focus row: the whole years its technology states, else that statement or the shown line for the placeholder. */
export type FocusEntry = { recordId: string; display: string; years: number | null; detail: string };
type Entry = FocusEntry;

function YearsRow({ entry, paused, submit, edit, drag }: { entry: Entry; paused: boolean; submit: (command: PanelCommand) => Promise<void>;
  edit: (recordId: string) => void; drag: ReturnType<typeof useTechnologyDrag> }) {
  const saved = entry.years === null ? "" : String(entry.years);
  const [value, setValue] = useState(saved), [bad, setBad] = useState(false), [busy, setBusy] = useState(false);
  const running = useRef(false);
  useEffect(() => { setValue(saved); setBad(false); }, [saved]);
  const next = yearsValue(value, bad);
  async function save() {
    if (paused || running.current || next === null) return;
    if (next !== value) setValue(next);
    if (next === saved) return;
    running.current = true; setBusy(true);
    try { await submit({ operation: "edit", recordId: entry.recordId, values: { experience: next } }); }
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
  return <form className="focus-years-row" data-fact-id={entry.recordId} {...drag.target(entry.recordId)} onSubmit={event => { event.preventDefault(); void save(); }}>
    <button type="button" className="technology-drag" aria-label={`Порядок в фокусе: ${entry.display}`} title="Перетащите или Alt+↑/↓"
      disabled={paused || busy} {...drag.handle(entry.recordId)}><span aria-hidden="true">⠿</span></button>
    <button type="button" className="focus-name" aria-label={`Изменить: ${entry.display}`} disabled={paused || busy}
      onClick={() => edit(entry.recordId)}>{entry.display}</button>
    <input aria-label={`Лет опыта: ${entry.display}`} type="number" min={0} max={100} step={1} inputMode="numeric"
      placeholder={entry.years === null && entry.detail ? entry.detail : "Лет"} value={value} aria-invalid={next === null || undefined}
      disabled={paused || busy} onChange={event => { setValue(event.target.value); setBad(event.target.validity.badInput); }}
      onBlur={() => { void save(); }} />
    <button type="submit" className="text-button" aria-label={`Сохранить срок: ${entry.display}`} aria-busy={busy}
      disabled={paused || busy || next === null || next === saved}>{busy ? <Spinner /> : "✓"}</button>
    <button type="button" className="icon" aria-label={`Убрать из фокуса: ${entry.display}`} disabled={paused || busy}
      onMouseDown={event => event.preventDefault()} onClick={() => { void remove(); }}><Icon name="close" /></button>
  </form>;
}

export function FocusYears({ entries, options, paused, submit, edit }: { entries: readonly Entry[]; options: readonly Entry[]; paused: boolean;
  submit: (command: PanelCommand) => Promise<void>;
  /** Opens the technology's own dialog: its name and any stated experience, such as 10 месяцев. */
  edit: (recordId: string) => void }) {
  const [selected, setSelected] = useState(""), [busy, setBusy] = useState(false);
  const running = useRef(false);
  const choice = options.some(option => option.recordId === selected) ? selected : options[0]?.recordId ?? "";
  const drag = useTechnologyDrag(entries.map(entry => entry.recordId), "move_focus", paused || busy, submit);
  // Nothing to list or add, as for a template without a Focus block: no Focus heading either.
  if (!entries.length && !options.length) return null;
  async function add() {
    if (paused || running.current || !choice) return;
    running.current = true; setBusy(true);
    try { await submit({ operation: "add_to_focus", recordId: choice }); }
    catch { /* The facts panel shows the error. */ }
    finally { running.current = false; setBusy(false); }
  }
  return <div className="focus-years" aria-label="Фокус">
    <p className="technology-label">Фокус · лет опыта</p>
    {entries.map(entry => <YearsRow key={entry.recordId} entry={entry} paused={paused} submit={submit} edit={edit} drag={drag} />)}
    {drag.dragging && entries.length > 1 && <div className="technology-drop-end" {...drag.target(null)}>В конец списка</div>}
    {options.length > 0 && <form className="focus-add" onSubmit={event => { event.preventDefault(); void add(); }}>
      <select aria-label="Технология для фокуса" value={choice} disabled={paused || busy} onChange={event => setSelected(event.target.value)}>
        {options.map(option => <option key={option.recordId} value={option.recordId}>{option.display}</option>)}
      </select>
      <Button type="submit" variant="quiet" busy={busy} busyLabel="Добавляем…" disabled={paused}>Добавить в фокус</Button>
    </form>}
  </div>;
}
