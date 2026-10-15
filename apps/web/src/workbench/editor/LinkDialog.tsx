import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";

export function LinkDialog({ open, close, apply }: { open: boolean; close: () => void; apply: (href: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null), [href, setHref] = useState("");
  useEffect(() => {
    const element = dialog.current;
    if (open && !element?.open) element?.showModal();
    if (!open && element?.open) element.close();
  }, [open]);
  return <dialog ref={dialog} className="modal" aria-labelledby="uir-link-title" onClose={close} onCancel={close}>
    <form onSubmit={event => { event.preventDefault(); if (!/^(https?:|mailto:)/i.test(href)) return; apply(href); close(); }}>
      <div className="dialog-heading"><h2 id="uir-link-title">Ссылка</h2><button type="button" className="icon" aria-label="Закрыть ссылку" onClick={close}><Icon name="close" /></button></div>
      <label>Адрес<input aria-label="Адрес ссылки" type="url" required value={href} onChange={event => setHref(event.currentTarget.value)} /></label>
      <div className="dialog-actions"><button type="button" className="text-button" onClick={close}>Отмена</button><button className="button primary" disabled={!/^(https?:|mailto:)/i.test(href)}>Добавить</button></div>
    </form>
  </dialog>;
}
