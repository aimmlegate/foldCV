type Destination = { id: string; label: string };
export function BlockPanel({ id, available, close, command, destinations }: { id: string; available: boolean; close: () => void;
  command: (command: string, target?: string) => void; destinations: Destination[] }) {
  return <aside className="rich-block-panel" aria-label="Панель блока" data-block-id={id}>
    <header><h2>Блок</h2><button onClick={close} aria-label="Скрыть панель блока">×</button></header>
    {!available && <p role="status">Блок удалён. Откройте меню другого блока.</p>}
    <div className="rich-block-actions">
      <button disabled={!available} onClick={() => command("duplicate")}>Дублировать</button>
      <button disabled={!available} onClick={() => command("delete")}>Удалить</button>
      <button disabled={!available} onClick={() => command("up")}>Выше</button>
      <button disabled={!available} onClick={() => command("down")}>Ниже</button>
      <button disabled={!available} onClick={() => command("nest")}>Вложить</button>
      <button disabled={!available} onClick={() => command("unnest")}>Убрать вложенность</button>
      <button disabled={!available} onClick={() => command("merge")}>Объединить с предыдущим</button>
      <label>Переместить в<select aria-label="Переместить блок" value="" disabled={!available}
        onChange={event => command("move", event.currentTarget.value)}>
        <option value="">Выберите раздел</option>{destinations.filter(target => target.id !== id).map(target => <option key={target.id} value={target.id}>{target.label}</option>)}
      </select></label>
    </div>
  </aside>;
}
