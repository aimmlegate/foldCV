import { useEffect, useLayoutEffect, useRef } from "react";
import { REFUSAL_SHOWN, refusalPlace, type Box } from "./refusal-notice";

export type Refusal = { id: number; text: string; line: Box };

/** A short message at the text the user was working on, when the editor did not take an input. It takes no pointer and
 * goes after 4 s; the notice area is not used for it. */
export function RefusalNotice({ refusal, done }: { refusal: Refusal | null; done: (id: number) => void }) {
  const element = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = element.current;
    if (!node || !refusal) return;
    const rect = node.getBoundingClientRect(), button = document.querySelector(".selection-action:not(.block-reword)")?.getBoundingClientRect();
    const place = refusalPlace(refusal.line, { width: rect.width, height: rect.height }, { width: innerWidth, height: innerHeight },
      button ? { left: button.left, top: button.top, right: button.right, bottom: button.bottom } : null);
    node.style.left = `${place.left}px`;
    node.style.top = `${place.top}px`;
  }, [refusal]);
  useEffect(() => {
    if (!refusal) return;
    const timer = setTimeout(() => done(refusal.id), REFUSAL_SHOWN);
    return () => clearTimeout(timer);
  }, [refusal, done]);
  if (!refusal) return null;
  return <div ref={element} className="refusal-notice" role="status">{refusal.text}</div>;
}
