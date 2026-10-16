import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { validLink } from "./link";

export function LinkDialog({ open, close, apply, selectedText }: { open: boolean; close: () => void; apply: (href: string, text: string) => void; selectedText: string }) {
  const dialog = useRef<HTMLDialogElement>(null), [href, setHref] = useState("");
  const [text, setText] = useState(selectedText);
  useEffect(() => {
    const element = dialog.current;
    if (open && !element?.open) element?.showModal();
    if (!open && element?.open) element.close();
  }, [open]);
  return <dialog ref={dialog} className="modal" aria-labelledby="uir-link-title" onClose={close} onCancel={close}>
    <form onSubmit={event => { event.preventDefault(); if (!validLink(href) || !text) return; apply(href, text); close(); }}>
      <div className="dialog-heading"><h2 id="uir-link-title">Ссылка</h2><button type="button" className="icon" aria-label="Закрыть ссылку" onClick={close}><Icon name="close" /></button></div>
      <label htmlFor="uir-link-text">Текст ссылки</label><input id="uir-link-text" aria-label="Текст ссылки" required value={text} onChange={event => setText(event.currentTarget.value)} />
      <label htmlFor="uir-link-url">Адрес</label><input id="uir-link-url" aria-label="Адрес ссылки" inputMode="url" required value={href} onChange={event => setHref(event.currentTarget.value)} />
      <div className="dialog-actions"><button type="button" className="text-button" onClick={close}>Отмена</button><button className="button primary" disabled={!validLink(href) || !text}>Вставить ссылку</button></div>
    </form>
  </dialog>;
}
