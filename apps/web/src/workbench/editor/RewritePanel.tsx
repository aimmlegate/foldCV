import { useEffect, useRef } from "react";
import { Icon } from "../ui/Icon";

export function RewritePanel({ open, close, instruction, change, submit, busy, source }: {
  open: boolean; close: () => void; instruction: string; change: (value: string) => void;
  submit: () => void; busy: boolean; source: string;
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
    <div className="dialog-heading"><h2 id="uir-rewrite-title">Изменить текст</h2><button className="icon" aria-label="Закрыть изменение текста" onClick={close}><Icon name="close" /></button></div>
    <p className="rewrite-scope"><Icon name="file" />Выделенный текст · {source.length} знаков</p>
    <blockquote className="rewrite-source">{source}</blockquote>
    <label>Что изменить<textarea aria-label="Инструкция для фрагмента" value={instruction} onChange={event => change(event.currentTarget.value)} /></label>
    <div className="dialog-actions"><button type="button" className="text-button" onClick={close}>Закрыть</button><button type="button" className="button primary" disabled={busy || !instruction.trim()} onClick={submit}><Icon name="spark" />{busy ? "Изменяю…" : "Изменить"}</button></div>
  </dialog>;
}
