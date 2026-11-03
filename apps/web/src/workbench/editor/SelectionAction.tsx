import { useLayoutEffect, useRef } from "react";
import { Icon } from "../ui/Icon";

/** «Изменить текст» beside the selected text, where the tester looked for it; the toolbar button stays (D127). It never
 * takes the focus, so the selection it names survives the click. */
export function SelectionAction({ anchor, open }: { anchor: { left: number; bottom: number; top: number } | null; open: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    const element = button.current;
    if (!element || !anchor) return;
    const rect = element.getBoundingClientRect(), below = anchor.bottom + 8;
    element.style.left = `${Math.max(8, Math.min(anchor.left, innerWidth - rect.width - 8))}px`;
    element.style.top = `${below + rect.height < innerHeight - 8 ? below : Math.max(8, anchor.top - rect.height - 8)}px`;
  }, [anchor]);
  if (!anchor) return null;
  return <button ref={button} type="button" className="selection-action" title="Изменить выделенный текст с помощью модели"
    onMouseDown={event => event.preventDefault()} onClick={open}><Icon name="spark" /><span>Изменить текст</span></button>;
}
