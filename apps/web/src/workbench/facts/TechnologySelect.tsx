import type { OrderDocument } from "../../rich/technology-order";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { WorkingFacts } from "../../contracts/generated/working_facts";
import type { PanelCommand } from "../../rich/synchronization";
import { technologyKey, technologyName } from "../../rich/panel-intents";
import { Icon } from "../ui/Icon";
import { technologySuggestions } from "./technology-catalog";
import { FactDialog } from "./FactDialog";
import { Spinner } from "../ui/OperationStatus";
import { documentTechnologies } from "../../rich/technology-order";
import { useTechnologyDrag } from "./useTechnologyDrag";

export function TechnologySelect({ facts, document: resumeDocument, jobId, label, pending, paused, submit, focusRecordId }: {
  facts: WorkingFacts; document: OrderDocument; jobId: string | null; label: string; pending: readonly PanelCommand[]; paused: boolean;
  submit: (command: PanelCommand) => Promise<void>;
  focusRecordId?: string | undefined;
}) {
  const id = useId(), root = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false), [query, setQuery] = useState(""), [active, setActive] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const records = documentTechnologies(facts, resumeDocument, jobId);
  const focused = records.some(record => record.id === focusRecordId);
  useEffect(() => { if (focused) setExpanded(true); }, [focused]);
  const editedRecord = records.find(record => record.id === editing);
  const scoped = pending.filter(command => command.operation === "clear_technologies" ? (command.jobId ?? null) === jobId
    : command.operation === "add" ? command.recordKind === "technology" && (command.jobId ?? null) === jobId
      : records.some(record => record.id === command.recordId));
  const drag = useTechnologyDrag(records.map(record => record.id), "move_technology", paused || pending.length > 0, submit);
  const adding = scoped.filter(command => command.operation === "add").map(command => technologyName(command.values?.["display"] ?? ""));
  const selected = new Set([...records.map(record => technologyKey(record.display.rawText)), ...adding.map(technologyKey)]);
  const catalog = useMemo(() => technologySuggestions(facts, jobId, query, resumeDocument), [facts, jobId, query, resumeDocument]);
  const available = catalog.filter(name => !selected.has(technologyKey(name)));
  const choices = available.slice(0, 60)
    .map(name => ({ name, custom: false }));
  const custom = technologyName(query);
  if (custom && !selected.has(technologyKey(custom)) && !catalog.some(name => technologyKey(name) === technologyKey(custom))) choices.push({ name: custom, custom: true });
  const activeIndex = Math.min(active, Math.max(0, choices.length - 1));
  useEffect(() => {
    if (open) root.current?.querySelectorAll<HTMLElement>('[role="option"]')[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex, query, choices.length]);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside); return () => document.removeEventListener("pointerdown", outside);
  }, []);
  const apply = (command: PanelCommand) => { void submit(command).catch(() => {}); };
  function choose(name: string) {
    if (paused) return;
    apply({ operation: "add", recordKind: "technology", jobId, values: { display: name } });
    setQuery(""); setActive(0); setExpanded(true); setOpen(true); input.current?.focus();
  }
  return <div className="technology-select" data-technology-scope={jobId ?? ""} ref={root}>
    <span className="technology-label">{jobId ? "Технологии" : "Все технологии"}</span>
    <ul className="technology-values" id={`${id}-values`} aria-label={`Выбранные технологии: ${label}`}>
        {(expanded || focused ? records : records.slice(0, 8)).map(record => <li key={record.id} className="technology-chip" data-fact-id={record.id} {...drag.target(record.id)}
          aria-busy={scoped.some(command => command.operation === "clear_technologies" || command.recordId === record.id ||
            command.operation === "add" && technologyKey(command.values?.["display"] ?? "") === technologyKey(record.display.rawText))}>
          <button type="button" className="technology-drag" aria-label={`Порядок: ${record.display.rawText}`} title="Перетащите или нажмите Alt+↑ / Alt+↓"
            disabled={paused || pending.length > 0} {...drag.handle(record.id)}><span aria-hidden="true">⠿</span></button>
          <button type="button" className="technology-edit" aria-label={`Изменить ${record.display.rawText} и срок опыта`} disabled={paused}
            onClick={event => { event.stopPropagation(); setOpen(false); setEditing(record.id); }}>
            <span>{record.display.rawText}</span>{record.experience?.rawText && <small>{record.experience.rawText}</small>}
          </button>
          <button type="button" aria-label={`Убрать ${record.display.rawText}`} disabled={paused}
            onClick={event => { event.stopPropagation(); apply({ operation: "remove", recordId: record.id }); }}><Icon name="close" /></button>
        </li>)}
        {[...new Set(adding)].filter(name => !records.some(record => technologyKey(record.display.rawText) === technologyKey(name))).map(name =>
          <li key={technologyKey(name)} className="technology-chip" aria-busy="true"><span>{name}</span><Spinner /></li>)}
    </ul>
    {drag.dragging && <div className="technology-drop-end" {...drag.target(null)}>В конец списка</div>}
    {records.length > 8 && <button type="button" className="technology-expand" aria-expanded={expanded} aria-controls={`${id}-values`}
      onClick={() => { setExpanded(value => !value); }}>{expanded ? "Свернуть список" : `Ещё ${records.length - 8}`}</button>}
    <div className="technology-field" onClick={() => input.current?.focus()}>
        <input ref={input} id={id} className="technology-search" role="combobox" aria-label={`Технологии: ${label}`} aria-autocomplete="list"
          aria-expanded={open} aria-controls={`${id}-options`} aria-activedescendant={open && choices.length ? `${id}-option-${activeIndex}` : undefined}
          autoComplete="off" maxLength={80} placeholder="Добавить технологию…" value={query} disabled={paused}
          onFocus={() => setOpen(true)} onChange={event => { setQuery(event.target.value); setActive(0); setOpen(true); }}
          onKeyDown={event => {
            if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
            else if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true);
              setActive((activeIndex + (event.key === "ArrowDown" ? 1 : -1) + choices.length) % Math.max(1, choices.length)); }
            else if (event.key === "Enter" && open) { event.preventDefault(); const choice = choices[activeIndex]; if (choice) choose(choice.name); }
          }} />
      <div className="technology-field-actions">
        <button type="button" data-technology-toggle aria-label={`Показать список технологий: ${label}`} aria-expanded={open} aria-controls={`${id}-options`}
          disabled={paused}
          onClick={event => { event.stopPropagation(); setOpen(value => !value); }}><Icon name="chevron" /></button>
      </div>
    </div>
    <div className="technology-menu" id={`${id}-options`} role="listbox" aria-label={`Список технологий: ${label}`} aria-multiselectable="true" hidden={!open}>
      {choices.length ? choices.map((choice, index) => <button type="button" key={technologyKey(choice.name)} role="option" tabIndex={-1} aria-selected="false"
        id={`${id}-option-${index}`} className={`technology-option${index === activeIndex ? " active" : ""}`} disabled={paused}
        onMouseDown={event => event.preventDefault()} onClick={() => choose(choice.name)}>{choice.custom ? `Добавить «${choice.name}»` : choice.name}</button>)
        : <span className="technology-no-results">Нет доступных вариантов</span>}
      {available.length > 60 && <span className="technology-no-results">Уточните название, чтобы увидеть остальные варианты.</span>}
    </div>
    {open && (records.length > 0 || adding.length > 0) && <button type="button" className="text-button" aria-label={`Убрать все технологии: ${label}`} disabled={paused}
      onClick={() => { apply({ operation: "clear_technologies", recordKind: "technology", jobId, recordId: null, periodId: null, values: {} }); }}>Убрать все технологии</button>}
    {editedRecord && <FactDialog target={{ kind: "technology", record: editedRecord }} close={() => { setEditing(null); }} submit={submit} />}
  </div>;
}
