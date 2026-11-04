import * as Menu from "@radix-ui/react-dropdown-menu";
import type { ReactNode, Ref } from "react";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import type { MenuAction, MenuChoice } from "./studio";

const labels: Record<MenuAction, string> = { copy: "Копировать…", branding: "Логотип и подвал…", default: "Сделать основным",
  download: "Скачать YAML", reset: "Вернуть встроенный…", delete: "Удалить…" };
const order: readonly MenuAction[] = ["copy", "branding", "default", "download", "reset", "delete"];
const reasons: Partial<Record<MenuAction, string>> = { delete: "Основной шаблон удалить нельзя: сначала сделайте основным другой" };

/** The shown template's name and marks, Save and Check always in view, the rest in the «⋯» menu. `check` is absent for
 * a new template, which the server can check only once saved. */
export function TemplateToolbar({ name, chips, actions, dirty, busy, saving, checking, save, check, choose, more, children }: {
  name: string; chips: readonly { label: string; main?: boolean }[]; actions: Record<MenuAction, MenuChoice>;
  dirty: boolean; busy: boolean; saving: boolean; checking: boolean;
  save: () => void; check?: (() => void) | undefined; choose: (action: MenuAction) => void;
  more?: Ref<HTMLButtonElement>; children?: ReactNode;
}) {
  const offered = order.filter(action => actions[action] !== "hidden");
  return <div className="template-toolbar">
    <div className="template-heading"><h3 title={name}>{name}</h3>
      {chips.map(chip => <span key={chip.label} className={`template-chip${chip.main ? " main" : ""}`}>{chip.label}</span>)}</div>
    <div className="template-actions">
      <Button variant="primary" busy={saving} busyLabel="Сохраняем…" disabled={busy || !dirty} onClick={save}>Сохранить</Button>
      {check && <Button busy={checking} busyLabel="Проверяем…" disabled={busy} onClick={check}>Проверить</Button>}
      {offered.length > 0 && <Menu.Root modal={false}>
        <Menu.Trigger asChild><button ref={more} type="button" className="button template-more" aria-label="Ещё действия" title="Ещё действия" disabled={busy}>
          <Icon name="more" /></button></Menu.Trigger>
        <Menu.Portal><Menu.Content className="template-menu" align="end" sideOffset={6} collisionPadding={12}>
          {offered.map(action => <Menu.Item key={action} className={action === "delete" ? "danger" : undefined} disabled={actions[action] === "disabled"}
            title={actions[action] === "disabled" ? reasons[action] : undefined} onSelect={() => choose(action)}>{labels[action]}</Menu.Item>)}
        </Menu.Content></Menu.Portal>
      </Menu.Root>}
      {children}
    </div>
  </div>;
}
