import { useEffect, useRef } from "react";
import { Icon } from "../ui/Icon";

export function RewritePanel({ open, close, instruction, change, submit, busy, source, error }: {
  open: boolean; close: () => void; instruction: string; change: (value: string) => void;
  submit: () => void; busy: boolean; source: string; error: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null), returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      element.show(); element.querySelector("textarea")?.focus();
    } else if (!open && element.open) {
      element.close(); returnFocus.current?.focus();
    }
  }, [open]);
  return <dialog ref={dialog} className="rewrite-panel uir-rewrite" aria-labelledby="uir-rewrite-title" onClose={close}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); close(); } }}>
    <div className="dialog-heading"><div><h2 id="uir-rewrite-title">Изменить текст</h2></div><button className="icon" aria-label="Закрыть изменение текста" onClick={close}><Icon name="close" /></button></div>
    <p className="rewrite-scope"><Icon name="file" />Только выделенный фрагмент · {source.length} знаков</p>
    <blockquote className="rewrite-source">{source}</blockquote>
    <label htmlFor="uir-rewrite-instruction">Что изменить?</label><textarea id="uir-rewrite-instruction" rows={2} aria-label="Инструкция для фрагмента" disabled={busy} value={instruction} onChange={event => change(event.currentTarget.value)} />
    <div className="rewrite-chips"><button disabled={busy} onClick={() => change("Сократи текст, сохрани факты и смысл.")}>Сократить</button><button disabled={busy} onClick={() => change("Сделай текст яснее, сохрани факты и смысл.")}>Сделать яснее</button></div>
    {error && <p className="notice warning" role="alert">{error}</p>}
    <button type="button" className="button primary" disabled={busy || !instruction.trim()} onClick={submit}>{busy ? "Изменяю…" : "Изменить текст"}<Icon name="spark" /></button>
    <p className="rewrite-boundary">Правка заменит только захваченный фрагмент. Её можно отменить в общей истории.</p>
  </dialog>;
}
