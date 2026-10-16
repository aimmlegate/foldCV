import { SideMenuExtension } from "@blocknote/core/extensions";
import { SideMenu, useExtension, useExtensionState } from "@blocknote/react";
import { Icon } from "../workbench/ui/Icon";

export function BlockSideMenu({ open }: { open: (id: string) => void }) {
  const menu = useExtension(SideMenuExtension);
  const block = useExtensionState(SideMenuExtension, { selector: state => state?.block });
  return <SideMenu>{block && block.type !== "region" && <button className="bn-button rich-block-handle" type="button"
    aria-label="Меню блока" data-block-id={block.id} draggable onDragStart={event => menu.blockDragStart(event, block)} onDragEnd={() => menu.blockDragEnd()}
    onPointerEnter={() => menu.freezeMenu()} onPointerLeave={() => menu.unfreezeMenu()}
    onMouseDown={event => event.preventDefault()} onClick={() => open(block.id)}><Icon name="more" /></button>}</SideMenu>;
}

export function SelectionToolbar({ rewrite, disabled }: { rewrite: () => void; disabled: boolean }) {
  return <button type="button" className="selection-action uir-selection-action" disabled={disabled}
    onMouseDown={event => event.preventDefault()} onClick={rewrite}><Icon name="spark" />Изменить текст</button>;
}
