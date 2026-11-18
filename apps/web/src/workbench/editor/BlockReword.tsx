import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { RewriteActivity } from "../../rich/rewrite-progress";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { RewriteOptions, useRewriteSettings } from "./RewriteOptions";
import { RewriteComparison, RewriteProgress, useFloatingPanel, useRewritePresets } from "./RewritePanel";
import { kindLabel, refusalLabel, rewordTarget, valueLimit, type RewordChange, type RewordPreview, type RewordValue } from "./reword";

type Shown = { blockId: string; right: number; top: number };

/** «Переписать» beside the block under the pointer, for a block whose text a model may reword (a trial of the look:
 * a plain button). It takes no focus and changes nothing by itself. */
export function BlockRewordButton({ host, blockIds, open }: { host: RefObject<HTMLElement | null>; blockIds: ReadonlySet<string>;
  open: (blockId: string) => void }) {
  const [shown, setShown] = useState<Shown | null>(null);
  const button = useRef<HTMLButtonElement>(null), hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const element = host.current;
    if (!element || blockIds.size === 0) { setShown(null); return; }
    const cancelHide = () => { if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; } };
    // Leaving the block gives the pointer a moment to reach the button.
    const hideSoon = () => { cancelHide(); hideTimer.current = setTimeout(() => setShown(null), 260); };
    const over = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (button.current && target && button.current.contains(target)) { cancelHide(); return; }
      const block = element.contains(target) ? rewordTarget(target, blockIds) : null;
      if (!block) { hideSoon(); return; }
      cancelHide();
      const rect = block.getBoundingClientRect();
      setShown({ blockId: block.getAttribute("data-id") ?? "", right: rect.right, top: rect.top });
    };
    const hide = () => { cancelHide(); setShown(null); };
    document.addEventListener("mouseover", over);
    element.addEventListener("scroll", hide, { passive: true });
    return () => { cancelHide(); document.removeEventListener("mouseover", over); element.removeEventListener("scroll", hide); };
  }, [host, blockIds]);
  useLayoutEffect(() => {
    const element = button.current, frame = host.current?.getBoundingClientRect();
    if (!element || !shown || !frame) return;
    const rect = element.getBoundingClientRect();
    // In the page's margin beside the block's first line, kept inside the page's pane.
    element.style.left = `${Math.max(frame.left + 8, Math.min(shown.right + 6, frame.right - rect.width - 12))}px`;
    element.style.top = `${Math.max(frame.top + 4, Math.min(shown.top, frame.bottom - rect.height - 4))}px`;
  }, [shown, host]);
  if (!shown) return null;
  return <button ref={button} type="button" className="selection-action block-reword" title="Переписать текст блока"
    onMouseDown={event => event.preventDefault()} onClick={() => { const id = shown.blockId; setShown(null); open(id); }}>
    <Icon name="spark" /><span>Переписать</span></button>;
}

/** The values of a preview the user works on: the text of each (edited or as the model gave it) and the ones left out. */
type Draft = { requestId: string; texts: Record<string, string>; skipped: ReadonlySet<string> };

/** A whole block reworded, in the panel of «Изменить текст»: the same chips, model choice, marks of the changed words,
 * editable result and «Ещё вариант», one comparison per value of the block. The request field holds everything the model
 * is told about style: a chip only puts its text there (`rules`: the unified rules of this kind of block), where the user
 * reads and edits it. Nothing changes until «Применить», and only the values left ticked are sent. */
export function BlockRewritePanel({ open, close, instruction, change, rules, submit, apply, preview, busy, error, activity, cancel, anchor }: {
  open: boolean; close: () => void; instruction: string; change: (value: string) => void; rules: string; submit: () => void;
  apply: (changes: RewordChange[]) => void; preview: RewordPreview | null; busy: boolean; error: string;
  activity: RewriteActivity | null; cancel: (id: string) => void; anchor: { left: number; top: number; bottom: number } | null;
}) {
  const dialog = useRef<HTMLElement>(null);
  const presets = useRewritePresets(open), settings = useRewriteSettings(open);
  // The request field takes the focus, so Escape closes the panel and the keys go to it, not to the page behind.
  const returnFocus = useFloatingPanel(dialog, open, anchor, true, close);
  const [draft, setDraft] = useState<Draft | null>(null);
  // A new preview starts from the model's texts with every changed value ticked.
  const current = preview && draft?.requestId === preview.requestId ? draft
    : preview ? { requestId: preview.requestId, texts: {}, skipped: new Set<string>() } : null;
  const values = preview?.values ?? [], changed = values.filter(value => value.state === "changed");
  const refused = values.filter(value => value.state === "refused"), same = values.length - changed.length - refused.length;
  const textOf = (value: RewordValue) => current?.texts[value.id] ?? value.after ?? "";
  const chosen = changed.filter(value => !current?.skipped.has(value.id) && textOf(value).trim() && textOf(value).trim() !== value.before);
  const send = () => apply(chosen.map(value => ({ recordId: value.recordId, field: value.field, value: textOf(value).trim() })));
  const asked = instruction.trim() !== "";
  const fields = <><label htmlFor="uir-reword-instruction">Что изменить?</label>
    <textarea id="uir-reword-instruction" rows={rules && instruction === rules ? 8 : 3} aria-label="Что изменить"
      placeholder="Напишите запрос или выберите готовый ниже: его текст появится здесь"
      disabled={busy} value={instruction} onChange={event => change(event.currentTarget.value)} />
    <div className="rewrite-chips">{rules && <button disabled={busy} aria-pressed={instruction === rules} onClick={() => change(rules)}>По правилам</button>}
      <button disabled={busy} onClick={() => change(presets.shorten)}>Сократить</button>
      <button disabled={busy} onClick={() => change(presets.clarify)}>Сделать яснее</button></div>
    <RewriteOptions settings={settings} disabled={busy} /></>;
  return <section ref={dialog} hidden={!open} role="dialog" aria-modal="false" className="rewrite-panel uir-rewrite reword-panel" aria-labelledby="uir-reword-title"
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); returnFocus.current?.focus(); }
      else if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing && !busy) {
        event.preventDefault();
        if (preview && !(event.target instanceof HTMLTextAreaElement && event.target.id === "uir-reword-instruction")) { if (chosen.length) send(); }
        else if (asked) submit();
      }
    }}>
    <div className="dialog-heading"><div><h2 id="uir-reword-title">Переписать блок</h2></div>
      <button className="icon" aria-label={busy ? "Скрыть" : "Закрыть"} onClick={close}><Icon name="close" /></button></div>
    {preview && current ? <>
      {changed.length === 0 && <p className="reword-note">{refused.length ? "Ни одно предложение модели не прошло проверку."
        : "Модель не предложила изменений: текст уже соответствует запросу."}</p>}
      <div className="reword-values">
        {changed.map(value => <section key={value.id} className="reword-value" data-skipped={current.skipped.has(value.id) || undefined}>
          <label className="reword-pick"><input type="checkbox" checked={!current.skipped.has(value.id)} disabled={busy} onChange={event => {
            const skipped = new Set(current.skipped); if (event.currentTarget.checked) skipped.delete(value.id); else skipped.add(value.id);
            setDraft({ ...current, skipped }); }} /><strong>{kindLabel(value.kind)}</strong></label>
          <RewriteComparison id={`uir-reword-${value.id}`} rows={1} maxLength={valueLimit} source={value.before} text={textOf(value)} disabled={busy || current.skipped.has(value.id)}
            edit={text => setDraft({ ...current, texts: { ...current.texts, [value.id]: text } })} />
        </section>)}
        {refused.map(value => <section key={value.id} className="reword-value reword-refused">
          <p className="reword-pick"><strong>{kindLabel(value.kind)}</strong> — не принято: {refusalLabel(value)}</p>
          <section className="rewrite-before"><h3>Было</h3><p className="rewrite-source">{value.before}</p></section>
          <section className="rewrite-before"><h3>Предложено</h3><p className="rewrite-source">{value.after}</p></section>
        </section>)}
      </div>
      {same > 0 && <p className="reword-note">Без изменений: {same}.</p>}
      <details className="rewrite-adjust"><summary>Изменить инструкцию</summary>{fields}</details>
    </> : fields}
    <RewriteProgress error={error} busy={busy} activity={activity} cancel={cancel} checking={settings.checking && !preview} />
    <div className="rewrite-actions">
      {preview ? <Button variant="primary" busy={busy} busyLabel="Применяем…" disabled={chosen.length === 0} onClick={send}>
          Применить ({chosen.length})<Icon name="check" /></Button>
        : <Button variant="primary" busy={busy} busyLabel="Готовим вариант…" disabled={settings.checking || !asked} onClick={submit}>
          Переписать<Icon name="spark" /></Button>}
      {preview && <Button variant="quiet" disabled={busy || !asked} onClick={submit}>Ещё вариант</Button>}
    </div>
  </section>;
}
