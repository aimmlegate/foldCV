import { Icon } from "../workbench/ui/Icon";

export function SelectionToolbar({ rewrite, disabled }: { rewrite: () => void; disabled: boolean }) {
  return <button type="button" className="selection-action uir-selection-action" disabled={disabled}
    onMouseDown={event => event.preventDefault()} onClick={rewrite}><Icon name="spark" />Изменить текст</button>;
}
