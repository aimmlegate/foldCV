import { SideMenuExtension } from "@blocknote/core/extensions";
import { AddBlockButton, FormattingToolbar, getFormattingToolbarItems, SideMenu, useExtension, useExtensionState } from "@blocknote/react";
import { Icon } from "../workbench/ui/Icon";

export function BlockSideMenu({ open, prototype = false }: { open: (id: string) => void; prototype?: boolean }) {
  const menu = useExtension(SideMenuExtension);
  const block = useExtensionState(SideMenuExtension, { selector: state => state?.block });
  return <SideMenu>{!prototype && <AddBlockButton />}{block && block.type !== "region" && <button className="bn-button rich-block-handle" type="button"
    aria-label="Меню блока" data-block-id={block.id} draggable onDragStart={event => menu.blockDragStart(event, block)} onDragEnd={() => menu.blockDragEnd()}
    onPointerEnter={() => menu.freezeMenu()} onPointerLeave={() => menu.unfreezeMenu()}
    onMouseDown={event => event.preventDefault()} onClick={() => open(block.id)}>{prototype ? <Icon name="more" /> : "⋮"}</button>}</SideMenu>;
}

export function SelectionToolbar({ rewrite, disabled, prototype = false }: { rewrite: () => void; disabled: boolean; prototype?: boolean }) {
  if (prototype) return <button type="button" className="selection-action uir-selection-action" disabled={disabled}
    onMouseDown={event => event.preventDefault()} onClick={rewrite}><Icon name="spark" />Изменить текст</button>;
  return <FormattingToolbar>{getFormattingToolbarItems()}<button type="button" className="bn-button rich-selection-rewrite"
    disabled={disabled} onMouseDown={event => event.preventDefault()} onClick={rewrite}>Переписать выделенное</button></FormattingToolbar>;
}
