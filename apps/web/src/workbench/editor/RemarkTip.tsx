import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { remarkMessagesAttribute, remarkRecordAttribute } from "../../rich/remarks";

type Shown = { messages: string[]; recordId: string | null; left: number; top: number; bottom: number };

/** Reads what a marked element carries; null for an element that is no mark. */
export function remarkOf(element: Element | null): { messages: string[]; recordId: string | null } | null {
  const mark = element?.closest<HTMLElement>(".fcv-remark");
  if (!mark) return null;
  let messages: string[] = [];
  try {
    const parsed: unknown = JSON.parse(mark.getAttribute(remarkMessagesAttribute) ?? "[]");
    messages = Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string" && item.trim() !== "") : [];
  } catch { messages = []; }
  return messages.length ? { messages, recordId: mark.getAttribute(remarkRecordAttribute) } : null;
}

/** What a yellow mark means, shown beside it while the pointer rests on it, with a way to the fact it names (D127). The marks
 * had only a native title, which the tester never saw. Nothing here changes the document. */
export function RemarkTip({ host, openFact }: { host: RefObject<HTMLElement | null>; openFact: (recordId: string) => void }) {
  const [shown, setShown] = useState<Shown | null>(null);
  const tip = useRef<HTMLDivElement>(null), hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const cancelHide = () => { if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; } };
    // Leaving the mark gives the pointer a moment to reach the tip; leaving both hides it.
    const hideSoon = () => { cancelHide(); hideTimer.current = setTimeout(() => setShown(null), 220); };
    const over = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (tip.current && target && tip.current.contains(target)) { cancelHide(); return; }
      const remark = remarkOf(target), mark = target?.closest(".fcv-remark");
      if (!remark || !mark) { hideSoon(); return; }
      cancelHide();
      const rect = mark.getBoundingClientRect();
      setShown({ ...remark, left: rect.left, top: rect.top, bottom: rect.bottom });
    };
    const leave = () => hideSoon();
    // A press or a selection means the user is at work in the text: the tip gets out of the way at once. A press on the tip
    // itself is its button: hiding then would unmount the button before its click.
    const hide = (event?: Event) => {
      if (event && tip.current && event.target instanceof Node && tip.current.contains(event.target)) return;
      cancelHide(); setShown(null);
    };
    const selection = () => { if (!document.getSelection()?.isCollapsed) hide(); };
    element.addEventListener("mouseover", over);
    element.addEventListener("mouseleave", leave);
    document.addEventListener("mouseover", over);
    document.addEventListener("pointerdown", hide);
    document.addEventListener("selectionchange", selection);
    return () => { cancelHide(); element.removeEventListener("mouseover", over); element.removeEventListener("mouseleave", leave);
      document.removeEventListener("mouseover", over); document.removeEventListener("pointerdown", hide); document.removeEventListener("selectionchange", selection); };
  }, [host]);
  useLayoutEffect(() => {
    const element = tip.current;
    if (!element || !shown) return;
    const rect = element.getBoundingClientRect(), below = shown.bottom + 6;
    element.style.left = `${Math.max(8, Math.min(shown.left, innerWidth - rect.width - 8))}px`;
    element.style.top = `${below + rect.height < innerHeight - 8 ? below : Math.max(8, shown.top - rect.height - 6)}px`;
  }, [shown]);
  if (!shown) return null;
  return <div ref={tip} className="remark-tip" role="note" aria-label="Что проверить">
    <strong>Что проверить</strong>
    {shown.messages.map(message => <p key={message}>{message}</p>)}
    {shown.recordId && <button type="button" className="text-button" onMouseDown={event => event.preventDefault()}
      onClick={() => { const id = shown.recordId; setShown(null); if (id) openFact(id); }}>Открыть в фактах</button>}
  </div>;
}
