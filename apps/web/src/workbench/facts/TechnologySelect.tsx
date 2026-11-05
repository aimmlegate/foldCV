import type { OrderDocument } from "../../rich/technology-order";
import { useEffect, useId, useState } from "react";
import type { WorkingFacts } from "../../contracts/generated/contracts";
import type { PanelCommand, TechnologyTarget } from "../../rich/v7-panel";
import { technologyKey, technologyName } from "../../rich/panel-intents";
import { Icon } from "../ui/Icon";
import { title } from "../../rich/fact-fields";
import { Spinner } from "../ui/OperationStatus";
import { documentTechnologies } from "../../rich/technology-order";
import { TechnologyAdd } from "./TechnologyAdd";
import { useTechnologyDrag } from "./useTechnologyDrag";

export function TechnologySelect({ facts, document: resumeDocument, jobId, label, pending, paused, submit, edit, focusRecordId, targets, lines = [], excluded }: {
  facts: WorkingFacts; document: OrderDocument; jobId: string | null; label: string; pending: readonly PanelCommand[]; paused: boolean;
  submit: (command: PanelCommand) => Promise<void>;
  /** The panel opens the chip's dialog outside itself: Escape in a dialog inside it would also close the panel. */
  edit: (recordId: string) => void;
  focusRecordId?: string | undefined;
  /** The lines Python can add to; with several, the user picks the group. */
  targets: readonly TechnologyTarget[];
  /** The technologies that share a line; a move stays inside its line. */
  lines?: readonly (readonly string[])[] | undefined;
  /** Records only Focus rows show; Focus manages them, so the list leaves them out. */
  excluded?: ReadonlySet<string> | undefined;
}) {
  const id = useId();
  const [expanded, setExpanded] = useState(false), [group, setGroup] = useState("");
  const line = targets.some(target => target.blockId === group) ? group : targets[0]?.blockId;
  const records = documentTechnologies(facts, resumeDocument, jobId).filter(record => !excluded?.has(record.id));
  const focused = records.some(record => record.id === focusRecordId);
  useEffect(() => { if (focused) setExpanded(true); }, [focused]);
  const scoped = pending.filter(command => command.operation === "clear_technologies" ? (command.jobId ?? null) === jobId
    : command.operation === "add" ? command.recordKind === "technology" && (command.jobId ?? null) === jobId
      : records.some(record => record.id === command.recordId));
  const drag = useTechnologyDrag(records.map(record => record.id), "move_technology", paused || pending.length > 0, submit, lines);
  const adding = scoped.filter(command => command.operation === "add").map(command => technologyName(command.values?.["display"] ?? ""));
  const selected = new Set([...records.map(record => technologyKey(record.display.rawText)), ...adding.map(technologyKey)]);
  const apply = (command: PanelCommand) => { void submit(command).catch(() => {}); };
  function choose(name: string) {
    if (!line) return;
    apply({ operation: "add", recordKind: "technology", jobId, values: { display: name }, lineBlockId: line });
    setExpanded(true);
  }
  const clear = (records.length > 0 || adding.length > 0) && <button type="button" className="text-button" aria-label={`Убрать все технологии: ${label}`}
    disabled={paused} onClick={() => { apply({ operation: "clear_technologies", recordKind: "technology", jobId, recordId: null, periodId: null, values: {} }); }}>
    Убрать все технологии</button>;
  return <div className="technology-select" data-technology-scope={jobId ?? ""}>
    <span className="technology-label">{jobId ? "Технологии" : "Все технологии"}</span>
    <ul className="technology-values" id={`${id}-values`} aria-label={`Выбранные технологии: ${label}`}>
        {(expanded || focused ? records : records.slice(0, 8)).map(record => <li key={record.id} className="technology-chip" data-fact-id={record.id} {...drag.target(record.id)}
          aria-busy={scoped.some(command => command.operation === "clear_technologies" || command.recordId === record.id ||
            command.operation === "add" && technologyKey(command.values?.["display"] ?? "") === technologyKey(record.display.rawText))}>
          <button type="button" className="technology-drag" aria-label={`Порядок: ${title(record)}`} title="Перетащите или Alt+↑/↓"
            disabled={paused || pending.length > 0 || !drag.movable(record.id)} {...drag.handle(record.id)}><span aria-hidden="true">⠿</span></button>
          <button type="button" className="technology-edit" aria-label={`Изменить: ${title(record)}`} disabled={paused}
            onClick={event => { event.stopPropagation(); edit(record.id); }}>
            <span>{title(record)}</span>{record.experience?.rawText && <small>{record.experience.rawText}</small>}
          </button>
          <button type="button" aria-label={`Убрать: ${title(record)}`} disabled={paused}
            onClick={event => { event.stopPropagation(); apply({ operation: "remove", recordId: record.id }); }}><Icon name="close" /></button>
        </li>)}
        {[...new Set(adding)].filter(name => !records.some(record => technologyKey(record.display.rawText) === technologyKey(name))).map(name =>
          <li key={technologyKey(name)} className="technology-chip" aria-busy="true"><span>{name}</span><Spinner /></li>)}
    </ul>
    {drag.dragging && <div className="technology-drop-end" {...drag.target(null)}>{jobId ? "В конец списка" : "В конец группы"}</div>}
    {records.length > 8 && <button type="button" className="technology-expand" aria-expanded={expanded} aria-controls={`${id}-values`}
      onClick={() => { setExpanded(value => !value); }}>{expanded ? "Свернуть" : `Ещё ${records.length - 8}`}</button>}
    {!targets.length && <small className="technology-note">Новую технологию здесь не добавить: в документе нет строки для этого списка.</small>}
    {targets.length > 1 && <label className="technology-group">Группа
      <select aria-label={`Группа для новой технологии: ${label}`} value={line} disabled={paused} onChange={event => setGroup(event.target.value)}>
        {targets.map(target => <option key={target.blockId} value={target.blockId}>{target.label || "Без названия"}</option>)}
      </select></label>}
    {targets.length > 0 ? <TechnologyAdd facts={facts} document={resumeDocument} jobId={jobId} label={label} listed={selected} paused={paused}
      choose={choose} footer={clear} /> : clear}
  </div>;
}
