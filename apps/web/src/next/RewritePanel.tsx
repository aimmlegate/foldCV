import type { useRewrite } from "./useRewrite";

export function RewritePanel({ rewrite }: { rewrite: ReturnType<typeof useRewrite> }) {
  const target = rewrite.target;
  if (!target) return null;
  return <aside className="next-source-panel next-rewrite-panel" aria-label="Помощник текста" data-slot-owner={target.owner}>
    <header><h2>Улучшить текст</h2><button onClick={rewrite.close} aria-label="Закрыть помощник текста">Закрыть</button></header>
    <p>Выделение сохранено. Опишите, что изменить.</p>
    <label htmlFor="rewrite-instruction">Что изменить</label>
    <textarea id="rewrite-instruction" rows={5} maxLength={2000} value={rewrite.instruction}
      onChange={event => rewrite.setInstruction(event.target.value)} />
    <div className="next-rewrite-presets">
      <button disabled={rewrite.busy} onClick={() => rewrite.setInstruction(target.rules.presets.shorten)}>Сократить</button>
      <button disabled={rewrite.busy} onClick={() => rewrite.setInstruction(target.rules.presets.clarify)}>Яснее</button>
    </div>
    <button disabled={rewrite.busy || !rewrite.instruction.trim()} onClick={() => { void rewrite.submit(); }}>Обновить выделение</button>
    {rewrite.busy && <p role="status">Улучшаем текст… <button onClick={rewrite.invalidate}>Остановить улучшение</button></p>}
  </aside>;
}
