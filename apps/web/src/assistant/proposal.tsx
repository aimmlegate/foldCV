import { useEffect, useRef } from "react";
import type { Proposal } from "./api";
import { Button } from "../workbench/ui/Button";

const states = { draft: "Предложенные правки", applied: "Правки применены", discarded: "Правки отклонены" };
const effects: Record<string, string> = { set_block_text: "Текст", replace_text: "Текст", insert_blocks: "Структура",
  delete_blocks: "Структура", move_block: "Структура", format_block: "Оформление", update_fact: "Факты", create_fact: "Факты",
  delete_fact: "Факты", undo: "История", redo: "История", rename: "Название", formatting_date: "Дата оформления",
  archive: "Архив", restore: "Архив", delete: "Удаление резюме" };
const actions: Record<string, string> = { rename: "Переименовать резюме", formatting_date: "Изменить дату оформления",
  archive: "Перенести резюме в архив", restore: "Вернуть резюме из архива", delete: "Удалить резюме" };

/** Apply needs a draft, the edits flag and a preview that is still current; Discard needs only a draft. */
export function proposalControls(value: Proposal, busy: boolean, stale: boolean, allowEdits: boolean): { apply: boolean; discard: boolean; reason: string | null } {
  const draft = value.state === "draft";
  return { apply: !busy && draft && !stale && allowEdits, discard: !busy && draft,
    reason: !draft ? null : stale ? "Документ изменился. Попросите новые правки."
      : !allowEdits ? "Включите «Разрешить правки», затем нажмите «Применить»." : null };
}

export function proposalTitle(value: Proposal): string {
  const op = value.ops[0];
  if (op?.op === "history") return op.direction === "redo" ? "Повторить отменённое действие" : "Отменить последнее действие";
  if (op?.op === "action") return actions[op.action] ?? "Действие с резюме";
  return "Изменения в резюме";
}

/** A history entry with no text, such as a change of form only, has nothing to compare. */
function shownChanges(value: Proposal): Proposal["preview"] {
  return value.kind === "history" ? value.preview.filter(change => change.before || change.after) : value.preview;
}

export function ProposalPreview({ value, busy, applying, stale, allowEdits, apply, discard }: {
  value: Proposal; busy: boolean; applying: boolean; stale: boolean; allowEdits: boolean; apply: () => void; discard: () => void;
}) {
  const controls = proposalControls(value, busy, stale, allowEdits);
  const button = useRef<HTMLButtonElement>(null), heading = useRef<HTMLHeadingElement>(null);
  const wasBusy = useRef(busy), restoreFocus = useRef(false);
  useEffect(() => {
    // A keyboard Apply keeps focus on the result: the button while it is usable, else the heading.
    if (wasBusy.current && !busy && restoreFocus.current) { (button.current && !button.current.disabled ? button.current : heading.current)?.focus(); restoreFocus.current = false; }
    wasBusy.current = busy;
  }, [busy]);
  const title = proposalTitle(value);
  return <article className="chat-proposal" data-state={value.state} aria-label={`Правки: ${title}`}>
    <h3 ref={heading} tabIndex={-1}>{stale && value.state === "draft" ? "Правки устарели" : states[value.state]}</h3>
    <p>{title}</p>
    {value.summary && <p>{value.summary}</p>}
    {shownChanges(value).map((change, index) => <details key={`${change.target}:${String(index)}`} open className="chat-proposal-change">
      <summary>{effects[change.label] ?? "Изменение"} · {index + 1}</summary>
      <div className="chat-proposal-comparison"><div><h4>Было</h4><pre>{change.before || "Нет"}</pre></div>
        <div><h4>Станет</h4><pre>{change.after || "Нет"}</pre></div></div>
    </details>)}
    {/* A decided proposal shows its outcome instead of buttons that can never work again. */}
    {value.state === "draft" && <>
      {value.kind === "edit" && <p>Можно отменить одним шагом.</p>}
      {controls.reason && <p role="status">{controls.reason}</p>}
      <div className="chat-proposal-actions"><Button ref={button} variant="primary" className="small" busy={applying} busyLabel="Применяем…" disabled={!controls.apply}
        onClick={event => { restoreFocus.current = event.detail === 0; apply(); }}>Применить</Button>
        <button type="button" className="text-button" disabled={!controls.discard} onClick={discard}>Отклонить</button></div>
    </>}
    {value.state === "applied" && value.kind === "edit" && <p className="chat-proposal-result">Изменения внесены в резюме. Отменить — кнопкой «Отменить» над документом.</p>}
  </article>;
}
