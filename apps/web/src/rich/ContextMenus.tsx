import { SideMenuExtension } from "@blocknote/core/extensions";
import { AddBlockButton, FormattingToolbar, getFormattingToolbarItems, SideMenu, useExtension, useExtensionState } from "@blocknote/react";

export function BlockSideMenu({ open }: { open: (id: string) => void }) {
  const menu = useExtension(SideMenuExtension);
  const block = useExtensionState(SideMenuExtension, { selector: state => state?.block });
  return <SideMenu><AddBlockButton />{block && block.type !== "region" && <button className="bn-button rich-block-handle" type="button"
    aria-label="Меню блока" data-block-id={block.id} draggable onDragStart={event => menu.blockDragStart(event, block)} onDragEnd={() => menu.blockDragEnd()}
    onPointerEnter={() => menu.freezeMenu()} onPointerLeave={() => menu.unfreezeMenu()}
    onMouseDown={event => event.preventDefault()} onClick={() => open(block.id)}>⋮</button>}</SideMenu>;
}

export function SelectionToolbar({ rewrite, disabled }: { rewrite: () => void; disabled: boolean }) {
  return <FormattingToolbar>{getFormattingToolbarItems()}<button type="button" className="bn-button rich-selection-rewrite"
    disabled={disabled} onMouseDown={event => event.preventDefault()} onClick={rewrite}>Переписать выделенное</button></FormattingToolbar>;
}
