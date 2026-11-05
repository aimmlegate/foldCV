import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { WorkingFacts } from "../../contracts/generated/contracts";
import { technologyKey, technologyName } from "../../rich/panel-intents";
import type { OrderDocument } from "../../rich/technology-order";
import { Icon } from "../ui/Icon";
import { technologySuggestions } from "./technology-catalog";

/** The field that adds a technology to one list: catalog names for the list's scope, or the typed name as a new one. The
 * names the list shows already are not offered. */
export function TechnologyAdd({ facts, document: resumeDocument, jobId, label, listed, paused, choose, footer, focus = false }: {
  facts: WorkingFacts; document: OrderDocument; jobId: string | null;
  /** The list's name in the field's accessible labels. */
  label: string;
  /** Keys of the names the list shows or is adding. */
  listed: ReadonlySet<string>; paused: boolean; choose: (name: string) => void;
  /** Shown under the open suggestions. */
  footer?: ReactNode;
  /** The field takes focus when it appears, as a new group's does. */
  focus?: boolean;
}) {
  const id = useId(), root = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false), [query, setQuery] = useState(""), [active, setActive] = useState(0);
  const [refocus, setRefocus] = useState(false);
  const catalog = useMemo(() => technologySuggestions(facts, jobId, query, resumeDocument), [facts, jobId, query, resumeDocument]);
  const available = catalog.filter(name => !listed.has(technologyKey(name)));
  const choices = available.slice(0, 60).map(name => ({ name, custom: false }));
  const custom = technologyName(query);
  if (custom && !listed.has(technologyKey(custom)) && !catalog.some(name => technologyKey(name) === technologyKey(custom))) choices.push({ name: custom, custom: true });
  const activeIndex = Math.min(active, Math.max(0, choices.length - 1));
  useEffect(() => {
    if (open) root.current?.querySelectorAll<HTMLElement>('[role="option"]')[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex, query, choices.length]);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside); return () => document.removeEventListener("pointerdown", outside);
  }, []);
  useEffect(() => { if (focus) input.current?.focus(); }, [focus]);
  // The field is disabled while a command saves; the next technology is typed into it again afterwards.
  useEffect(() => { if (refocus && !paused) { setRefocus(false); input.current?.focus(); } }, [refocus, paused]);
  function pick(name: string) {
    if (paused) return;
    choose(name);
    setQuery(""); setActive(0); setOpen(true); setRefocus(true);
  }
  return <div className="technology-add" ref={root}>
    <div className="technology-field" onClick={() => input.current?.focus()}>
      <input ref={input} id={id} className="technology-search" role="combobox" aria-label={`Технологии: ${label}`} aria-autocomplete="list"
        aria-expanded={open} aria-controls={`${id}-options`} aria-activedescendant={open && choices.length ? `${id}-option-${activeIndex}` : undefined}
        autoComplete="off" maxLength={80} placeholder="Добавить технологию…" value={query} disabled={paused}
        onFocus={() => setOpen(true)} onChange={event => { setQuery(event.target.value); setActive(0); setOpen(true); }}
        onKeyDown={event => {
          if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
          else if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true);
            setActive((activeIndex + (event.key === "ArrowDown" ? 1 : -1) + choices.length) % Math.max(1, choices.length)); }
          else if (event.key === "Enter" && open) { event.preventDefault(); const choice = choices[activeIndex]; if (choice) pick(choice.name); }
        }} />
      <div className="technology-field-actions">
        <button type="button" data-technology-toggle aria-label={`Показать список технологий: ${label}`} aria-expanded={open} aria-controls={`${id}-options`}
          disabled={paused} onClick={event => { event.stopPropagation(); setOpen(value => !value); }}><Icon name="chevron" /></button>
      </div>
    </div>
    <div className="technology-menu" id={`${id}-options`} role="listbox" aria-label={`Список технологий: ${label}`} aria-multiselectable="true" hidden={!open}>
      {choices.length ? choices.map((choice, index) => <button type="button" key={technologyKey(choice.name)} role="option" tabIndex={-1} aria-selected="false"
        id={`${id}-option-${index}`} className={`technology-option${index === activeIndex ? " active" : ""}`} disabled={paused}
        onMouseDown={event => event.preventDefault()} onClick={() => pick(choice.name)}>{choice.custom ? `Добавить «${choice.name}»` : choice.name}</button>)
        : <span className="technology-no-results">Ничего не найдено</span>}
      {available.length > 60 && <span className="technology-no-results">Показаны не все. Уточните запрос.</span>}
    </div>
    {open && footer}
  </div>;
}
