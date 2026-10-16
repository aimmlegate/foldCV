import { useEffect, useRef } from "react";
import { Icon } from "../ui/Icon";

export function BlockPanel({ id, text, available, close, command, destinations }: {
  id: string; text: string; available: boolean; close: () => void;
  command: (command: string, target?: string) => void; destinations: { id: string; label: string }[];
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => { panel.current?.querySelector("button")?.focus(); }, []);
  return <aside ref={panel} className="block-panel uir-block-panel" id="uir-block-panel" aria-label="Действия блока" data-block-id={id}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); } }}>
    <div className="panel-heading"><h2>Блок</h2><button className="icon" aria-label="Скрыть действия блока" onClick={close}><Icon name="close" /></button></div>
    <p className="block-scope">{available ? text.slice(0, 90) || "Пустой блок" : "Блок удалён. Выберите другой блок."}</p>
    <div className="block-actions">
      <button disabled={!available} onClick={() => command("duplicate")}>Дублировать</button><button className="danger" disabled={!available} onClick={() => command("delete")}>Удалить</button>
      <button disabled={!available} onClick={() => command("up")}>↑ Выше</button><button disabled={!available} onClick={() => command("down")}>↓ Ниже</button>
      <button disabled={!available} onClick={() => command("nest")}>→ Добавить отступ</button><button disabled={!available} onClick={() => command("unnest")}>← Убрать отступ</button>
      <button className="wide" disabled={!available} onClick={() => command("merge")}>Объединить с предыдущим</button>
    </div>
    <label htmlFor="uir-move-region">Переместить в</label><select id="uir-move-region" aria-label="Переместить блок" value="" disabled={!available} onChange={event => command("move", event.currentTarget.value)}>
      <option value="">Выберите область</option>{destinations.filter(target => target.id !== id).map(target => <option key={target.id} value={target.id}>{target.label}</option>)}
    </select>
  </aside>;
}
