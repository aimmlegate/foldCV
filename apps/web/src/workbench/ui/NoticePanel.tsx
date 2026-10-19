import * as Popover from "@radix-ui/react-popover";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

export function NoticePanel({ count, label = "Уведомления", onOpen, children }: {
  count: number; label?: string; onOpen?: () => void; children: ReactNode;
}) {
  if (!count) return null;
  return <Popover.Root onOpenChange={open => { if (open) onOpen?.(); }}>
    <Popover.Trigger asChild><button type="button" className="notice-trigger" aria-label={`${label}: ${count}`}>
      <Icon name="info" /><span className="notice-trigger-label">{label}</span><span className="notice-count">{count}</span>
    </button></Popover.Trigger>
    <Popover.Portal><Popover.Content className="notice-panel" aria-label={label} align="end" sideOffset={8} collisionPadding={12}>
      <div className="notice-panel-heading"><strong>{label}</strong><Popover.Close asChild>
        <button type="button" className="icon" aria-label="Закрыть уведомления"><Icon name="close" /></button>
      </Popover.Close></div>{children}
    </Popover.Content></Popover.Portal>
  </Popover.Root>;
}
