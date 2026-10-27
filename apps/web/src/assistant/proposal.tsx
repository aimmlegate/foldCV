import { useEffect, useRef } from "react";
import type { Proposal } from "./api";

const states = { draft: "Вариант готов к просмотру", applied: "Вариант сохранён", discarded: "Вариант отклонён" };
const effects: Record<string, string> = { set_block_text: "Текст", replace_text: "Текст", insert_blocks: "Структура",
  delete_blocks: "Структура", move_block: "Структура", format_block: "Оформление", update_fact: "Факты", create_fact: "Факты",
  delete_fact: "Факты", undo: "История", redo: "История", rename: "Название", formatting_date: "Дата оформления",
  archive: "Архив", restore: "Архив", delete: "Удаление проекта" };
const actions: Record<string, string> = { rename: "Переименовать резюме", formatting_date: "Изменить дату оформления",
  archive: "Перенести резюме в архив", restore: "Вернуть резюме из архива", delete: "Удалить резюме" };

/** Apply needs a draft, the edits flag and a preview that is still current; Discard needs only a draft. */
export function proposalControls(value: Proposal, busy: boolean, stale: boolean, allowEdits: boolean): { apply: boolean; discard: boolean; reason: string | null } {
  const draft = value.state === "draft";
  return { apply: !busy && draft && !stale && allowEdits, discard: !busy && draft,
    reason: !draft ? null : stale ? "После подготовки варианта документ изменился. Подготовьте новый вариант; текущие правки сохранены."
      : !allowEdits ? "Разрешите правки, затем отдельно нажмите «Применить»." : null };
}

export function proposalTitle(value: Proposal): string {
  const op = value.ops[0];
  if (op?.op === "history") return op.direction === "redo" ? "Повторить отменённое действие" : "Отменить последнее действие";
  if (op?.op === "action") return actions[op.action] ?? "Действие с проектом";
  return "Изменения в резюме";
}

export function ProposalPreview({ value, busy, stale, allowEdits, apply, discard }: {
  value: Proposal; busy: boolean; stale: boolean; allowEdits: boolean; apply: () => void; discard: () => void;
}) {
  const controls = proposalControls(value, busy, stale, allowEdits);
  const button = useRef<HTMLButtonElement>(null), heading = useRef<HTMLHeadingElement>(null);
  const wasBusy = useRef(busy), restoreFocus = useRef(false);
  useEffect(() => {
    // A keyboard Apply keeps focus on the result: the button while it is usable, else the heading.
    if (wasBusy.current && !busy && restoreFocus.current) { (button.current?.disabled ? heading.current : button.current)?.focus(); restoreFocus.current = false; }
    wasBusy.current = busy;
  }, [busy]);
  const title = proposalTitle(value);
  return <article className="chat-proposal" aria-label={`Вариант: ${title}`}>
    <h3 ref={heading} tabIndex={-1}>{stale && value.state === "draft" ? "Вариант устарел" : states[value.state]}</h3>
    <p>{title}</p>
    {value.summary && <p>{value.summary}</p>}
    {value.state === "draft" && <p>Документ пока не изменён этим вариантом.</p>}
    {value.kind !== "history" && value.preview.map((change, index) => <details key={`${change.target}:${String(index)}`} open className="chat-proposal-change">
      <summary>{effects[change.label] ?? "Изменение"} · {index + 1}</summary>
      <div className="chat-proposal-comparison"><div><h4>Сейчас</h4><pre>{change.before || "Нет"}</pre></div>
        <div><h4>После применения</h4><pre>{change.after || "Нет"}</pre></div></div>
    </details>)}
    {value.kind === "history" ? <p>Навигация по истории редактора. Новая запись в истории не создаётся.</p>
      : value.kind === "edit" && <p>После сохранения — одна отмена в истории редактора.</p>}
    {controls.reason && <p role="status">{controls.reason}</p>}
    <div className="chat-proposal-actions"><button ref={button} type="button" className="primary" disabled={!controls.apply}
      onClick={event => { restoreFocus.current = event.detail === 0; apply(); }}>Применить</button>
      <button type="button" className="text-button" disabled={!controls.discard} onClick={discard}>Отклонить</button></div>
  </article>;
}
