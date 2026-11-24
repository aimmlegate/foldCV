import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { addedClass, remarkBlockAttribute, remarkCellAttribute, remarkMessagesAttribute, remarkRecordAttribute } from "../../rich/remarks";
import type { AcceptTarget } from "../../rich/v7-connection";
import { tipPlace, type Box } from "./remark-tip";

type Remark = { messages: string[]; recordId: string | null; added: boolean; blockId: string | null; cellId: string | null };
type Shown = Remark & { mark: HTMLElement; x: number; y: number };

/** The pointer rests this long on a mark before its tip shows: a tip at once covered the lines the user was going to. */
export const TIP_DELAY = 500;
/** A tip with a button waits this long after the pointer leaves the mark, so the pointer can reach the button. The rest of
 * the tip takes no pointer (D179): a click there reaches the line under it and hides the tip. */
const BRIDGE = 600;

/** Reads what a marked element carries; null for an element that is no mark. */
export function remarkOf(element: Element | null): Remark | null {
  const mark = element?.closest<HTMLElement>(".fcv-remark");
  if (!mark) return null;
  let messages: string[] = [];
  try {
    const parsed: unknown = JSON.parse(mark.getAttribute(remarkMessagesAttribute) ?? "[]");
    messages = Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string" && item.trim() !== "") : [];
  } catch { messages = []; }
  return messages.length ? { messages, recordId: mark.getAttribute(remarkRecordAttribute), added: mark.classList.contains(addedClass),
    blockId: mark.getAttribute(remarkBlockAttribute), cellId: mark.getAttribute(remarkCellAttribute) } : null;
}

const plain = (rect: DOMRect): Box => ({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom });
/** The lines of a block mark: the boxes of all its spans, in order. */
function blockLines(host: HTMLElement, blockId: string): DOMRect[] {
  return [...host.querySelectorAll<HTMLElement>(`[${remarkBlockAttribute}="${CSS.escape(blockId)}"]`)].flatMap(span => [...span.getClientRects()]);
}
/** Whether the pointer is still on the mark: for a block mark, anywhere on its block's text. */
/** What «Принять» accepts in a tip «Нет в оригинале» (D179): the value of a word mark, the whole block of a block mark;
 * null for a tip with no such button. */
export function acceptTarget(remark: Remark): AcceptTarget | null {
  if (!remark.added) return null;
  if (remark.cellId) return { cellId: remark.cellId };
  return remark.blockId ? { blockId: remark.blockId } : null;
}
function onMark(shown: Shown, target: Element | null): boolean {
  if (!target) return false;
  if (shown.blockId) return !!target.closest(`[data-id="${CSS.escape(shown.blockId)}"] > .bn-block-content`);
  return shown.mark.contains(target);
}

/** What a mark means, shown near it once the pointer rests on it, with a way to the fact it names (D127). A tip with no
 * button takes no pointer, so a click goes to the text under it. Nothing here changes the document. */
export function RemarkTip({ host, openFact, accept = null }: { host: RefObject<HTMLElement | null>; openFact: (recordId: string) => void;
  /** Accepts a green mark's value or block; null where the page takes no edit. */
  accept?: ((target: AcceptTarget) => void) | null }) {
  const accepting = useRef(accept);
  accepting.current = accept;
  const [shown, setShown] = useState<Shown | null>(null);
  const tip = useRef<HTMLDivElement>(null), current = useRef<Shown | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null), showTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const waiting = useRef<HTMLElement | null>(null);
  current.current = shown;
  useEffect(() => {
    // The pane can be made again (a change of layout), so it is read at each event.
    const cancelHide = () => { if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; } };
    const cancelShow = () => { if (showTimer.current) { clearTimeout(showTimer.current); showTimer.current = null; } waiting.current = null; };
    const hide = () => { cancelHide(); cancelShow(); setShown(null); };
    const hideSoon = () => {
      cancelShow();
      if (!current.current) return;
      if (!current.current.recordId && !(accepting.current && acceptTarget(current.current))) { hide(); return; }
      if (!hideTimer.current) hideTimer.current = setTimeout(() => { hideTimer.current = null; setShown(null); }, BRIDGE);
    };
    const busy = (event: MouseEvent) => event.buttons !== 0 || !(document.getSelection()?.isCollapsed ?? true);
    const over = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (tip.current && target && tip.current.contains(target)) { cancelHide(); return; }
      const shownNow = current.current;
      if (shownNow && onMark(shownNow, target)) { cancelHide(); return; }
      const remark = remarkOf(target), mark = target?.closest<HTMLElement>(".fcv-remark") ?? null;
      if (!remark || !mark || !host.current?.contains(mark)) { hideSoon(); return; }
      if (waiting.current === mark) return;
      hideSoon();
      cancelShow();
      if (busy(event)) return;
      waiting.current = mark;
      const x = event.clientX, y = event.clientY;
      showTimer.current = setTimeout(() => {
        showTimer.current = null; waiting.current = null;
        if (!(document.getSelection()?.isCollapsed ?? true) || !mark.isConnected) return;
        cancelHide();
        setShown({ ...remark, mark, x, y });
      }, TIP_DELAY);
    };
    const move = (event: MouseEvent) => { if (waiting.current && busy(event)) cancelShow(); };
    // The pointer left the window.
    const out = (event: MouseEvent) => { if (!event.relatedTarget) hideSoon(); };
    const key = (event: KeyboardEvent) => { if (event.target instanceof Node && host.current?.contains(event.target)) hide(); };
    // A press, a key or a scroll means the user is at work: the tip gets out of the way at once. A press on the tip itself
    // is its button: hiding then would unmount the button before its click.
    const press = (event: Event) => {
      if (tip.current && event.target instanceof Node && tip.current.contains(event.target)) return;
      hide();
    };
    const selection = () => { if (!document.getSelection()?.isCollapsed) hide(); };
    document.addEventListener("keydown", key, true);
    document.addEventListener("mouseout", out);
    document.addEventListener("mouseover", over);
    document.addEventListener("mousemove", move, { passive: true });
    document.addEventListener("pointerdown", press);
    document.addEventListener("selectionchange", selection);
    document.addEventListener("scroll", hide, { capture: true, passive: true });
    return () => {
      cancelHide(); cancelShow();
      document.removeEventListener("keydown", key, true); document.removeEventListener("mouseout", out);
      document.removeEventListener("mouseover", over); document.removeEventListener("mousemove", move);
      document.removeEventListener("pointerdown", press); document.removeEventListener("selectionchange", selection);
      document.removeEventListener("scroll", hide, { capture: true });
    };
  }, [host]);
  useLayoutEffect(() => {
    const element = tip.current, frame = host.current;
    if (!element || !shown || !frame) return;
    const heightAt = (width: number) => { element.style.width = `${width}px`; return element.getBoundingClientRect().height; };
    const view = { width: innerWidth, height: innerHeight };
    const lines = shown.blockId ? blockLines(frame, shown.blockId) : [];
    const first = lines[0], last = lines.at(-1), paper = frame.querySelector(".resume-paper")?.getBoundingClientRect();
    const button = document.querySelector(".selection-action.block-reword")?.getBoundingClientRect() ?? null;
    const line = [...shown.mark.getClientRects()].find(rect => shown.y >= rect.top && shown.y <= rect.bottom) ?? shown.mark.getBoundingClientRect();
    const place = first && last && paper
      ? tipPlace({ window: view, heightAt, block: { first: plain(first), last: plain(last), paper: plain(paper), button: button && plain(button) } })
      : tipPlace({ window: view, heightAt, word: { line: plain(line), x: shown.x } });
    element.style.width = `${place.width}px`;
    element.style.left = `${place.left}px`;
    element.style.top = `${place.top}px`;
    element.dataset["place"] = place.place;
  }, [shown, host]);
  if (!shown) return null;
  const title = shown.added ? "Нет в оригинале" : "Что проверить";
  const target = accept ? acceptTarget(shown) : null;
  return <div ref={tip} className={shown.recordId || target ? "remark-tip" : "remark-tip remark-tip-passive"} role="note" aria-label={title}>
    <strong>{title}</strong>
    {shown.messages.map(message => <p key={message}>{message}</p>)}
    {shown.recordId && <button type="button" className="text-button" onMouseDown={event => event.preventDefault()}
      onClick={() => { const id = shown.recordId; setShown(null); if (id) openFact(id); }}>Открыть в фактах</button>}
    {target && accept && <button type="button" className="text-button" onMouseDown={event => event.preventDefault()}
      onClick={() => { setShown(null); accept(target); }}>{"cellId" in target ? "Принять" : "Принять блок"}</button>}
  </div>;
}
