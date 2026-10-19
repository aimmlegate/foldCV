import * as Popover from "@radix-ui/react-popover";
import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import { NoticePanel } from "./NoticePanel";
import { notificationTotal, updateNotificationCounts } from "./notification-counts";

type Notifications = {
  count: number; open: boolean; content: HTMLDivElement | null;
  change: (id: string, count: number) => void;
  setOpen: (open: boolean) => void; setContent: (element: HTMLDivElement | null) => void;
};
const Context = createContext<Notifications | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [counts, setCounts] = useState<ReadonlyMap<string, number>>(new Map());
  const [open, setOpen] = useState(false), [content, setContent] = useState<HTMLDivElement | null>(null);
  const change = useCallback((id: string, count: number) => {
    setCounts(previous => updateNotificationCounts(previous, id, count));
  }, []);
  const count = notificationTotal(counts);
  const value = useMemo(() => ({ count, open, content, change, setOpen, setContent }), [count, open, content, change]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function NotificationCenter() {
  const notices = useContext(Context);
  if (!notices) return null;
  return <Popover.Root open={notices.open} onOpenChange={notices.setOpen}>
    <Popover.Trigger asChild><button type="button" className="notice-trigger" aria-label={`Уведомления: ${notices.count}`}>
      <Icon name="info" /><span className="notice-trigger-label">Уведомления</span>
      {notices.count > 0 && <span className="notice-count">{notices.count}</span>}
    </button></Popover.Trigger>
    <Popover.Portal><Popover.Content className="notice-panel notification-center" aria-label="Уведомления" align="end" sideOffset={8} collisionPadding={12}>
      <div className="notice-panel-heading"><strong>Уведомления</strong><Popover.Close asChild>
        <button type="button" className="icon" aria-label="Закрыть уведомления"><Icon name="close" /></button>
      </Popover.Close></div>
      {notices.count === 0 && <p className="notification-empty">Уведомлений нет.</p>}
      <div className="notification-sections" ref={notices.setContent} />
    </Popover.Content></Popover.Portal>
  </Popover.Root>;
}

export function NotificationSection({ count, children, onOpen }: { count: number; children: ReactNode; onOpen?: (() => void) | undefined }) {
  const notices = useContext(Context), id = useId(), change = notices?.change;
  const open = notices?.open ?? false, opening = useRef(onOpen);
  opening.current = onOpen;
  useEffect(() => { change?.(id, count); }, [change, id, count]);
  useEffect(() => () => change?.(id, 0), [change, id]);
  useEffect(() => { if (open && count > 0) opening.current?.(); }, [open, count]);
  if (!notices) return <NoticePanel count={count} {...(onOpen ? { onOpen } : {})}>{children}</NoticePanel>;
  return notices.content && count > 0 ? createPortal(children, notices.content) : null;
}
