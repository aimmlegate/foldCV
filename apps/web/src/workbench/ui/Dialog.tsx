import { useEffect, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";

export function Dialog({ open, close, title, children }: { open: boolean; close: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || !open) return;
    const previous = document.activeElement;
    dialog.showModal();
    return () => { dialog.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, [open]);
  return <dialog className="modal" ref={ref} aria-label={title} onCancel={event => { event.preventDefault(); close(); }}>
    <div className="dialog-heading"><h2>{title}</h2><button className="icon" aria-label="Закрыть" onClick={close}><Icon name="close" /></button></div>
    {children}
  </dialog>;
}
