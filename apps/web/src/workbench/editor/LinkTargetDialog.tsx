import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { validLink } from "./link";

/** The address of one bound link. Any wording is kept; only web and mail addresses become DOCX links. */
export function LinkTargetDialog({ href, close, apply }: { href: string; close: () => void; apply: (href: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null), [value, setValue] = useState(href);
  useEffect(() => { const element = dialog.current; if (element && !element.open) element.showModal(); }, []);
  const note = value === "" ? "Без адреса текст ссылки останется обычным текстом."
    : validLink(value) ? "" : "Адрес без https:// или mailto: сохранится как текст и не станет ссылкой в DOCX.";
  return <dialog ref={dialog} className="modal" aria-labelledby="uir-link-target-title" onClose={close} onCancel={close}>
    <form onSubmit={event => { event.preventDefault(); apply(value); close(); }}>
      <div className="dialog-heading"><h2 id="uir-link-target-title">Адрес ссылки</h2><button type="button" className="icon" aria-label="Закрыть адрес ссылки" onClick={close}><Icon name="close" /></button></div>
      <label htmlFor="uir-link-target">Адрес</label><input id="uir-link-target" aria-label="Адрес ссылки" inputMode="url" value={value} onChange={event => setValue(event.currentTarget.value)} />
      {note && <p className="small muted">{note}</p>}
      <div className="dialog-actions"><button type="button" className="text-button" onClick={close}>Отмена</button><button className="button primary" disabled={value === href}>Сохранить адрес</button></div>
    </form>
  </dialog>;
}
