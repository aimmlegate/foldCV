import type { useRewrite } from "./useRewrite";
import type { FieldProjection } from "./adapter";

export function RewritePanel({ rewrite, fields, close }: { rewrite: ReturnType<typeof useRewrite>; fields: readonly FieldProjection[]; close: () => void }) {
  const target = rewrite.target;
  if (!target) return null;
  return <aside className="next-source-panel next-rewrite-panel" aria-label="Помощник текста" data-slot-owner={target.owner}
    onKeyDown={event => { if (event.key === "Escape" && !rewrite.busy) { event.preventDefault();close(); } }}>
    <p className="next-panel-eyebrow">ПОМОЩНИК ПО ТЕКСТУ</p>
    <header><h2>Улучшить текст</h2><button disabled={rewrite.busy} onClick={close} aria-label="Закрыть помощник текста">Закрыть</button></header>
    <p>Выделение сохранено. Опишите, что изменить.</p>
    <details className="next-captured-selection" open><summary>Выбранный текст</summary>{target.selection.spans.map(span => <section key={span.fieldId}>
      <h3>{fields.find(field => field.fieldId === span.fieldId)?.label ?? "Текст"}</h3><blockquote data-captured-field={span.fieldId}>{span.capturedText}</blockquote>
    </section>)}</details>
    <label htmlFor="rewrite-instruction">Что изменить</label>
    <textarea id="rewrite-instruction" rows={5} maxLength={2000} value={rewrite.instruction}
      onChange={event => rewrite.setInstruction(event.target.value)} />
    <div className="next-rewrite-presets">
      <button disabled={rewrite.busy} onClick={() => rewrite.setInstruction(target.rules.presets.shorten)}>Сократить</button>
      <button disabled={rewrite.busy} onClick={() => rewrite.setInstruction(target.rules.presets.clarify)}>Яснее</button>
    </div>
    <button disabled={rewrite.busy || !rewrite.instruction.trim()} onClick={() => { void rewrite.submit(); }}>Обновить выделение</button>
    <p className="next-panel-hint">Текст изменится сразу. Вернуть предыдущую версию можно кнопкой «Отменить правку блока».</p>
    {rewrite.busy && <p role="status">Улучшаем текст… <button onClick={rewrite.invalidate}>Остановить улучшение</button></p>}
  </aside>;
}
