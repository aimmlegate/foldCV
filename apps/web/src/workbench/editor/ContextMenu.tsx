import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { MENU_LABELS, type MenuItem } from "./context-menu";

/** The page's own context menu (F5): the look of the present menus, only items that can run. It never takes the focus
 * from the editor, so the selection it names survives; its keys are caught while it is open. */
export function ContextMenu({ at, items, run, close, pasteHint }: { at: { x: number; y: number } | null; items: readonly MenuItem[];
  run: (item: MenuItem) => void; close: () => void; pasteHint: string | null }) {
  const menu = useRef<HTMLDivElement>(null), [active, setActive] = useState(0);
  useEffect(() => { setActive(0); }, [at]);
  useLayoutEffect(() => {
    const element = menu.current;
    if (!element || !at) return;
    const rect = element.getBoundingClientRect();
    element.style.left = `${Math.max(8, Math.min(at.x, innerWidth - rect.width - 8))}px`;
    element.style.top = `${Math.max(8, at.y + rect.height > innerHeight - 8 ? at.y - rect.height : at.y)}px`;
  }, [at, items, pasteHint]);
  useEffect(() => {
    if (!at) return;
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); return; }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault(); event.stopPropagation();
        setActive(value => (value + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault(); event.stopPropagation();
        const item = items[active];
        if (item) run(item);
        return;
      }
      // Any other key, ⌘V among them, goes to the editor and the menu closes.
      close();
    };
    const press = (event: MouseEvent) => { if (!menu.current?.contains(event.target as Node)) close(); };
    const scroll = () => close();
    addEventListener("keydown", key, true);
    addEventListener("mousedown", press, true);
    addEventListener("scroll", scroll, true);
    addEventListener("blur", scroll);
    return () => {
      removeEventListener("keydown", key, true); removeEventListener("mousedown", press, true);
      removeEventListener("scroll", scroll, true); removeEventListener("blur", scroll);
    };
  }, [at, items, active, run, close]);
  if (!at || items.length === 0) return null;
  return <div ref={menu} className="template-menu editor-context-menu" role="menu" aria-label="Действия с текстом"
    onMouseDown={event => event.preventDefault()} onContextMenu={event => event.preventDefault()}>
    {items.map((item, index) => <div key={item} role="menuitem" tabIndex={-1} className={item === "removeBlock" ? "danger" : undefined}
      data-highlighted={index === active ? "" : undefined} onMouseEnter={() => setActive(index)} onClick={() => run(item)}>
      {item === "paste" && pasteHint ? pasteHint : MENU_LABELS[item]}
    </div>)}
  </div>;
}
