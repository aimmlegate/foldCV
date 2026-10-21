import { errorMessage } from "../../errors/messages";
import { useEffect, useLayoutEffect, useRef } from "react";
import { Icon } from "../ui/Icon";
import { rewriteCancellable, rewriteLabels, type RewriteActivity, type RewritePreview } from "../../rich/rewrite-progress";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";

export function RewritePanel({ open, close, instruction, change, submit, apply, preview, editPreview, busy, source, error, activity, cancel, anchor, focusInstruction }: {
  open: boolean; close: () => void; instruction: string; change: (value: string) => void;
  submit: () => void; busy: boolean; source: string; error: string;
  activity: RewriteActivity | null; cancel: (id: string) => void;
  preview: RewritePreview | null; apply: () => void; editPreview: (text: string) => void;
  anchor: { left: number; top: number; bottom: number } | null; focusInstruction: boolean;
}) {
  const dialog = useRef<HTMLElement>(null), returnFocus = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    const element = dialog.current;
    if (!element || !open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const place = () => {
      const rect = element.getBoundingClientRect(), bottom = (anchor?.bottom ?? 120) + 8;
      element.style.left = `${Math.max(12, Math.min(anchor?.left ?? innerWidth - rect.width - 12, innerWidth - rect.width - 12))}px`;
      element.style.top = `${Math.max(12, Math.min(bottom + rect.height < innerHeight - 12 ? bottom : (anchor?.top ?? bottom) - rect.height - 8, innerHeight - rect.height - 12))}px`;
    };
    place(); const observer = new ResizeObserver(place); observer.observe(element); window.addEventListener("resize", place);
    if (focusInstruction) element.querySelector("textarea")?.focus();
    return () => { observer.disconnect(); window.removeEventListener("resize", place); };
  }, [open, anchor, focusInstruction]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !dialog.current?.contains(event.target)) close(); };
    document.addEventListener("pointerdown", outside); return () => document.removeEventListener("pointerdown", outside);
  }, [open, close]);
  const fields = <><label htmlFor="uir-rewrite-instruction">Что изменить?</label><textarea id="uir-rewrite-instruction" rows={2} aria-label="Инструкция для фрагмента" disabled={busy} value={instruction} onChange={event => change(event.currentTarget.value)} />
    <div className="rewrite-chips"><button disabled={busy} onClick={() => change("Сократи текст, сохрани факты и смысл.")}>Сократить</button><button disabled={busy} onClick={() => change("Сделай текст яснее, сохрани факты и смысл.")}>Сделать яснее</button></div></>;
  return <section ref={dialog} hidden={!open} role="dialog" aria-modal="false" className="rewrite-panel uir-rewrite" aria-labelledby="uir-rewrite-title"
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); returnFocus.current?.focus(); }
      else if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing && !busy) {
        event.preventDefault(); if (preview && !(event.target instanceof HTMLTextAreaElement && event.target.id === "uir-rewrite-instruction")) { if (preview.text.trim()) apply(); }
        else if (instruction.trim() && source.trim()) submit();
      }
    }}>
    <div className="dialog-heading"><div><h2 id="uir-rewrite-title">Изменить текст</h2></div><button className="icon" aria-label={busy ? "Скрыть окно изменения текста" : "Закрыть изменение текста"} onClick={close}><Icon name="close" /></button></div>
    {!preview && <details className="rewrite-original"><summary>Выделено: {source.length} знаков</summary><blockquote className="rewrite-source">{source}</blockquote></details>}
    {preview ? <>
      <section className="rewrite-result" aria-label="Предпросмотр правки"><label htmlFor="uir-rewrite-result">Новый текст — можно исправить вручную</label>
        <textarea id="uir-rewrite-result" aria-label="Новый текст" rows={5} maxLength={65536} disabled={busy || preview.applied === true} value={preview.text} onChange={event => editPreview(event.currentTarget.value)} /></section></>
      : fields}
    {preview && <details className="rewrite-adjust"><summary>Изменить инструкцию</summary>{fields}</details>}
    <div className="rewrite-progress-slot">{error ? <p className="notice warning" role="alert">{errorMessage(error)}</p> : busy && activity ? <>
      <OperationStatus label={rewriteLabels[activity.stage]} timed startedAt={activity.startedAt} />
      {rewriteCancellable(activity.stage) && <button className="text-button" onClick={() => cancel(activity.actionId)}>Отменить правку</button>}
    </> : null}</div>
    <div className="rewrite-actions"><Button variant="primary" busy={busy} busyLabel={preview ? "Применяем…" : "Готовим вариант…"} disabled={preview ? !preview.text.trim() : !instruction.trim() || !source.trim()} onClick={preview ? apply : submit}>{preview ? "Применить" : "Изменить текст"}<Icon name={preview ? "check" : "spark"} /></Button>
      {preview && <Button variant="quiet" disabled={busy || !instruction.trim()} onClick={submit}>Ещё вариант</Button>}
    </div>
  </section>;
}
