import { errorMessage } from "../../errors/messages";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import { rulesRequest } from "../../api/client";
import { Icon } from "../ui/Icon";
import { rewriteCancellable, rewriteLabels, type RewriteActivity } from "../../rich/rewrite-progress";
import { textChanges, type TextPart } from "../../rich/text-changes";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";
import { RewriteOptions, useRewriteSettings } from "./RewriteOptions";

// Used until the saved presets from Settings are read, and when that read fails.
const builtInPresets = { shorten: "Сократи текст, сохрани факты и смысл.", clarify: "Сделай текст яснее, сохрани факты и смысл." };

function marked(parts: TextPart[], Mark: "del" | "ins") {
  return parts.map((part, index) => part.changed ? <Mark key={index}>{part.text}</Mark> : part.text);
}

type Anchor = { left: number; top: number; bottom: number } | null;

/** The saved presets from Settings, read on every opening: Settings may have saved new ones while the editor stayed mounted. */
export function useRewritePresets(open: boolean): typeof builtInPresets {
  const [presets, setPresets] = useState(builtInPresets);
  useEffect(() => {
    if (!open) return;
    let live = true;
    void rulesRequest().then(rules => { if (live) setPresets(rules.presets); }, () => {});
    return () => { live = false; };
  }, [open]);
  return presets;
}

/** A panel that floats by its anchor and stays inside the window; a press outside closes it. Gives the element that had
 * the focus before, for Escape to return to. */
export function useFloatingPanel(dialog: RefObject<HTMLElement | null>, open: boolean, anchor: Anchor, focusInstruction: boolean,
  close: () => void): RefObject<HTMLElement | null> {
  const returnFocus = useRef<HTMLElement | null>(null);
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
  return returnFocus;
}

/** «Было» with the removed words marked and «Станет» as a field with the added words marked; the field can be edited, and
 * the marks follow the edited text, so they show what Apply would change. */
export function RewriteComparison({ id, source, text, edit, disabled, rows, maxLength = 65536 }: { id: string; source: string; text: string;
  edit: (text: string) => void; disabled: boolean; rows?: number; maxLength?: number }) {
  const changes = useMemo(() => textChanges(source, text), [source, text]);
  return <>
    <section className="rewrite-before"><h3>Было</h3><p className="rewrite-source">{marked(changes.before, "del")}</p></section>
    <section className="rewrite-result"><label htmlFor={id}>Станет</label>
      {/* A copy of the text under the transparent field carries the marks while it is edited; the trailing space keeps a
          final empty line, as the field has one. */}
      <div className="rewrite-after"><div className="rewrite-marks" aria-hidden="true">{marked(changes.after, "ins")}{" "}</div>
        <textarea id={id} rows={rows} maxLength={maxLength} disabled={disabled} value={text} onChange={event => edit(event.currentTarget.value)} /></div></section>
  </>;
}

/** The stage of a running request with its timer and «Отменить», or its error. */
export function RewriteProgress({ error, busy, activity, cancel, checking }: { error: string; busy: boolean; activity: RewriteActivity | null;
  cancel: (id: string) => void; checking: boolean }) {
  return <div className="rewrite-progress-slot">{error ? <p className="notice warning" role="alert">{errorMessage(error)}</p> : busy && activity ? <>
    <OperationStatus label={rewriteLabels[activity.stage]} timed startedAt={activity.startedAt} />
    {rewriteCancellable(activity.stage) && <button className="text-button" onClick={() => cancel(activity.actionId)}>Отменить</button>}
  </> : checking ? <OperationStatus label="Проверяем подключение" /> : null}</div>;
}

export function RewritePanel({ open, close, instruction, change, submit, apply, preview, editPreview, busy, source, error, activity, cancel, anchor, focusInstruction }: {
  open: boolean; close: () => void; instruction: string; change: (value: string) => void;
  submit: () => void; busy: boolean; source: string; error: string;
  activity: RewriteActivity | null; cancel: (id: string) => void;
  preview: { text: string; applied?: boolean } | null; apply: () => void; editPreview: (text: string) => void;
  anchor: { left: number; top: number; bottom: number } | null; focusInstruction: boolean;
}) {
  const dialog = useRef<HTMLElement>(null);
  const presets = useRewritePresets(open);
  const settings = useRewriteSettings(open);
  const returnFocus = useFloatingPanel(dialog, open, anchor, focusInstruction, close);
  const fields = <><label htmlFor="uir-rewrite-instruction">Что изменить?</label><textarea id="uir-rewrite-instruction" rows={2} aria-label="Что изменить" disabled={busy} value={instruction} onChange={event => change(event.currentTarget.value)} />
    <div className="rewrite-chips"><button disabled={busy} onClick={() => change(presets.shorten)}>Сократить</button><button disabled={busy} onClick={() => change(presets.clarify)}>Сделать яснее</button></div>
    <RewriteOptions settings={settings} disabled={busy} /></>;
  return <section ref={dialog} hidden={!open} role="dialog" aria-modal="false" className="rewrite-panel uir-rewrite" aria-labelledby="uir-rewrite-title"
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); returnFocus.current?.focus(); }
      else if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing && !busy) {
        event.preventDefault(); if (preview && !(event.target instanceof HTMLTextAreaElement && event.target.id === "uir-rewrite-instruction")) { if (preview.text.trim()) apply(); }
        else if (instruction.trim() && source.trim()) submit();
      }
    }}>
    <div className="dialog-heading"><div><h2 id="uir-rewrite-title">Изменить текст</h2></div><button className="icon" aria-label={busy ? "Скрыть" : "Закрыть"} onClick={close}><Icon name="close" /></button></div>
    {!preview && <details className="rewrite-original"><summary>Выделено: {source.length} знаков</summary><blockquote className="rewrite-source">{source}</blockquote></details>}
    {preview ? <RewriteComparison id="uir-rewrite-result" source={source} text={preview.text} edit={editPreview}
      disabled={busy || preview.applied === true} />
      : fields}
    {preview && <details className="rewrite-adjust"><summary>Изменить инструкцию</summary>{fields}</details>}
    <RewriteProgress error={error} busy={busy} activity={activity} cancel={cancel} checking={settings.checking && !preview} />
    <div className="rewrite-actions"><Button variant="primary" busy={busy} busyLabel={preview ? "Применяем…" : "Готовим вариант…"} disabled={preview ? !preview.text.trim() : !instruction.trim() || !source.trim() || settings.checking} onClick={preview ? apply : submit}>{preview ? "Применить" : "Изменить текст"}<Icon name={preview ? "check" : "spark"} /></Button>
      {preview && <Button variant="quiet" disabled={busy || !instruction.trim()} onClick={submit}>Ещё вариант</Button>}
    </div>
  </section>;
}
