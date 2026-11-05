import { useId, useState, type DragEvent, type KeyboardEvent } from "react";
import type { WorkingFacts } from "../../contracts/generated/contracts";
import { title as recordTitle } from "../../rich/fact-fields";
import { technologyKey, technologyName } from "../../rich/panel-intents";
import { adjacentTechnology, type OrderDocument } from "../../rich/technology-order";
import type { PanelCommand, TechnologyTarget } from "../../rich/v7-panel";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/OperationStatus";
import { TechnologyAdd } from "./TechnologyAdd";

type Technology = Extract<WorkingFacts["records"][number], { kind: "technology" }>;
type Category = { id: string; title: string; records: Technology[]; draft: boolean };
const dragType = "application/x-foldcv-technology-group";

/** The skill groups of the resume, each with its technologies in the document's order (D136). A technology is added to a
 * group, moved within or between groups, or taken out of one; a group of one's own starts as a draft here and shows in the
 * resume with its first technology. General technologies the resume shows nowhere are listed last. */
export function TechnologyGroups({ facts, document: resumeDocument, targets, creatable, pending, paused, submit, edit, excluded }: {
  facts: WorkingFacts; document: OrderDocument;
  /** The plan's general targets: one per group, with its technologies. */
  targets: readonly TechnologyTarget[];
  /** A group of one's own can be started. */
  creatable: boolean;
  pending: readonly PanelCommand[]; paused: boolean; submit: (command: PanelCommand) => Promise<void>;
  /** The panel opens the chip's dialog outside itself: Escape in a dialog inside it would also close the panel. */
  edit: (recordId: string) => void;
  /** Records only Focus rows show; Focus manages them. */
  excluded?: ReadonlySet<string> | undefined;
}) {
  const scope = useId();
  const [drafts, setDrafts] = useState<string[]>([]), [naming, setNaming] = useState<string | null>(null);
  // The group a draft became: its field keeps the focus the draft's had.
  const [created, setCreated] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null), [over, setOver] = useState<string | null>(null);
  const busy = paused || pending.length > 0;
  const technologies = new Map(facts.records.filter((record): record is Technology => record.kind === "technology").map(record => [record.id, record]));
  const groups: Category[] = targets.map(target => ({ id: target.blockId, title: target.label, draft: false,
    records: (target.records ?? []).flatMap(id => { const record = technologies.get(id); return record ? [record] : []; }) }));
  const placed = new Set(groups.flatMap(group => group.records.map(record => record.id)));
  const unplaced = [...technologies.values()].filter(record => record.jobId === null && !placed.has(record.id) && !excluded?.has(record.id));
  const titles = new Set(groups.map(group => technologyKey(group.title)));
  const shownDrafts = drafts.filter(title => !titles.has(technologyKey(title)));
  const categories = [...groups, ...shownDrafts.map(title => ({ id: "draft:" + title, title, records: [], draft: true }))];
  const adding = (category: Category) => pending.flatMap(command => (command.operation === "add" && command.lineBlockId === category.id
    || command.operation === "add_technology_group" && !command.recordId && category.draft && command.values?.["title"] === category.title)
    ? [technologyName(command.values?.["display"] ?? "")] : []);
  const listed = new Set([...[...placed].flatMap(id => { const record = technologies.get(id); return record ? [technologyKey(record.display.rawText)] : []; }),
    ...unplaced.map(record => technologyKey(record.display.rawText)), ...categories.flatMap(adding).map(technologyKey)]);
  const apply = (command: PanelCommand) => submit(command).catch(() => {});
  const forget = (title: string) => setDrafts(values => values.filter(value => value !== title));
  const made = (title: string) => { forget(title); setCreated(technologyKey(title)); };
  function add(category: Category, name: string) {
    if (category.draft) void submit({ operation: "add_technology_group", recordKind: "technology", values: { title: category.title, display: name } })
      .then(() => made(category.title), () => {});
    else void apply({ operation: "add", recordKind: "technology", jobId: null, values: { display: name }, lineBlockId: category.id });
  }
  function move(recordId: string, category: Category, before: string | null) {
    if (busy || before === recordId) return;
    if (category.draft) void submit({ operation: "add_technology_group", recordId, values: { title: category.title } }).then(() => forget(category.title), () => {});
    else void apply({ operation: "move_technology", recordId, beforeRecordId: before, groupId: category.id });
  }
  const at = (category: string, before: string | null) => `${category}\n${before ?? ""}`;
  const target = (category: Category, before: string | null) => ({
    "data-drop-target": dragging !== null && dragging !== before && over === at(category.id, before) || undefined,
    onDragOver: (event: DragEvent<HTMLElement>) => {
      if (busy || !dragging || dragging === before || !event.dataTransfer.types.includes(dragType)) return;
      event.preventDefault(); event.dataTransfer.dropEffect = "move"; setOver(at(category.id, before));
    },
    onDrop: (event: DragEvent<HTMLElement>) => {
      if (busy || !dragging || event.dataTransfer.getData(dragType) !== scope) return;
      event.preventDefault(); move(dragging, category, before); setDragging(null); setOver(null);
    },
  });
  // Alt+↑/↓ moves inside a group, and past its first or last place into the group before or after it.
  function step(event: KeyboardEvent<HTMLButtonElement>, category: Category, recordId: string) {
    if (!event.altKey || event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault(); event.stopPropagation();
    const ids = category.records.map(record => record.id), up = event.key === "ArrowUp";
    const before = adjacentTechnology(ids, recordId, up ? -1 : 1);
    if (before !== undefined) { move(recordId, category, before); return; }
    const index = groups.findIndex(group => group.id === category.id), next = groups[index + (up ? -1 : 1)];
    if (index >= 0 && next) move(recordId, next, up ? null : next.records[0]?.id ?? null);
  }
  function name() {
    const title = (naming ?? "").split(/\s+/u).filter(Boolean).join(" ");
    if (!title) { setNaming(null); return; }
    if (categories.some(category => technologyKey(category.title) === technologyKey(title))) return;
    setDrafts(values => [...values, title]); setNaming(null);
  }
  const duplicate = naming !== null && categories.some(category => technologyKey(category.title) === technologyKey(naming.split(/\s+/u).filter(Boolean).join(" ")));
  const chip = (record: Technology, category: Category | null) => <li key={record.id} className="technology-chip" data-fact-id={record.id}
    {...(category ? target(category, record.id) : {})}
    aria-busy={pending.some(command => command.recordId === record.id) || undefined}>
    <button type="button" className="technology-drag" aria-label={`Порядок: ${recordTitle(record)}`} title="Перетащите или Alt+↑/↓"
      disabled={busy} draggable={!busy}
      onDragStart={event => {
        if (busy) { event.preventDefault(); return; }
        event.dataTransfer.setData(dragType, scope); event.dataTransfer.effectAllowed = "move";
        setDragging(record.id);
      }}
      onDragEnd={() => { setDragging(null); setOver(null); }}
      onKeyDown={event => { if (category) step(event, category, record.id); }}><span aria-hidden="true">⠿</span></button>
    <button type="button" className="technology-edit" aria-label={`Изменить: ${recordTitle(record)}`} disabled={paused}
      onClick={event => { event.stopPropagation(); edit(record.id); }}>
      <span>{recordTitle(record)}</span>{record.experience?.rawText && <small>{record.experience.rawText}</small>}
    </button>
    <button type="button" aria-label={category ? `Убрать из категории «${category.title}»: ${recordTitle(record)}` : `Убрать: ${recordTitle(record)}`}
      disabled={paused} onClick={event => {
        event.stopPropagation();
        void apply({ operation: "remove", recordId: record.id, ...(category ? { groupId: category.id } : {}) });
      }}><Icon name="close" /></button>
  </li>;
  return <div className="technology-select technology-categories">
    {categories.map(category => <section key={category.id} className="technology-category" aria-label={`Категория: ${category.title || "Без названия"}`}>
      <div className="technology-category-heading"><h4>{category.title || "Без названия"}</h4>
        {category.draft && <button type="button" className="icon" aria-label={`Убрать категорию: ${category.title}`} disabled={paused}
          onClick={() => forget(category.title)}><Icon name="close" /></button>}</div>
      <ul className="technology-values" aria-label={`Технологии категории: ${category.title}`}>
        {category.records.map(record => chip(record, category))}
        {[...new Set(adding(category))].filter(value => !category.records.some(record => technologyKey(record.display.rawText) === technologyKey(value)))
          .map(value => <li key={technologyKey(value)} className="technology-chip" aria-busy="true"><span>{value}</span><Spinner /></li>)}
      </ul>
      {!category.records.length && <small className="technology-note">В резюме появится с первой технологией.</small>}
      {dragging && <div className="technology-drop-end" {...target(category, null)}>{category.draft ? "Перетащите сюда" : "В конец категории"}</div>}
      <TechnologyAdd facts={facts} document={resumeDocument} jobId={null} label={category.title || "Без названия"} listed={listed} paused={paused}
        choose={value => add(category, value)} focus={category.draft || technologyKey(category.title) === created} />
    </section>)}
    {unplaced.length > 0 && <section className="technology-category" aria-label="Не в резюме">
      <div className="technology-category-heading"><h4>Не в резюме</h4></div>
      <small className="technology-note">Перетащите в категорию, чтобы показать в резюме.</small>
      <ul className="technology-values" aria-label="Технологии не в резюме">{unplaced.map(record => chip(record, null))}</ul>
    </section>}
    {creatable && (naming === null
      ? <button type="button" className="text-button fact-add" disabled={paused} onClick={() => setNaming("")}>+ Категория</button>
      : <div className="technology-category-new">
        <input aria-label="Название новой категории" placeholder="Название категории" maxLength={80} value={naming}
          autoFocus disabled={paused} onChange={event => setNaming(event.target.value)}
          onKeyDown={event => {
            if (event.key === "Enter") { event.preventDefault(); name(); }
            else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setNaming(null); }
          }} />
        <button type="button" className="text-button" disabled={paused || duplicate} onClick={name}>Создать</button>
        <button type="button" className="text-button" onClick={() => setNaming(null)}>Отмена</button>
        {duplicate && <small className="technology-note" role="alert">Категория с таким названием уже есть.</small>}
      </div>)}
  </div>;
}
