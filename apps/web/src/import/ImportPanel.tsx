import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import type { ExtractLocation } from "../contracts/generated/extract_result";
import type { ImportState, ImportWorkflow } from "./workflow";

const control = "rounded border border-outline bg-panel px-3 py-2 text-content hover:bg-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50";
const primary = "rounded border border-accent bg-accent px-3 py-2 text-accent-contrast focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50";
const field = "w-full rounded border border-outline bg-surface p-3 text-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

function locationLabel(location: ExtractLocation): string {
  const place = location.kind === "page" || location.kind === "image" ? `Страница ${location.page ?? "?"}`
    : location.kind === "table_cell" ? `Таблица ${(location.table ?? 0) + 1}${location.row === null || location.row === undefined ? "" : `, строка ${location.row + 1}`}${location.column === null || location.column === undefined ? "" : `, ячейка ${location.column + 1}`}`
      : location.kind === "header" ? "Верхний колонтитул" : location.kind === "footer" ? "Нижний колонтитул"
        : location.kind === "pasted" ? "Вставленный текст" : "Абзац";
  const item = location.paragraph === null || location.paragraph === undefined ? "" : ` · фрагмент ${location.paragraph + 1}`;
  return `${place}${item}`;
}

function gapLabel(code: string): string {
  return ({ NO_TEXT: "Текст на этой странице не найден", IMAGE: "Есть изображение без распознанного текста",
    SHAPE: "Фигура не прочитана", TEXT_BOX: "Текстовое поле не прочитано",
    UNSUPPORTED_CONTENT: "Часть содержимого не прочитана" } as Record<string, string>)[code] ?? "Есть пробел в извлечении";
}

export function ImportPanel({ state, workflow, text, onText, onExample, exampleDisabled }: {
  state: ImportState; workflow: ImportWorkflow; text: string; onText: (text: string) => void;
  onExample: () => void; exampleDisabled: boolean;
}) {
  const [page, setPage] = useState(0);
  const [clearPrompt, setClearPrompt] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const selected = state.entries.find((entry) => entry.result.sourceId === state.selectedId);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!selected || selected.result.sourceKind !== "pdf") { setOriginalUrl(null); return; }
    const bytes = workflow.original(selected.result.sourceId);
    if (!bytes) return;
    const url = URL.createObjectURL(new Blob([Uint8Array.from(bytes)], { type: "application/pdf" }));
    setOriginalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selected?.result.sourceId, workflow]);
  function downloadOriginal(): void {
    if (!selected) return;
    const bytes = workflow.original(selected.result.sourceId);
    if (!bytes) return;
    const url = URL.createObjectURL(new Blob([Uint8Array.from(bytes)], { type: selected.result.mimeType }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = selected.result.originalName;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  function fileSelected(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void workflow.file(file);
  }
  const units = selected?.result.units ?? [];
  const pageCount = Math.max(1, Math.ceil(units.length / 100));
  const shownPage = Math.min(page, pageCount - 1);
  return <section className="rounded border border-outline bg-panel p-5">
    <h2 className="mb-3 text-lg font-semibold">Исходное резюме</h2>
    <label htmlFor="source-file" className="mb-2 block">Выберите PDF, DOCX, TXT или Markdown</label>
    <input id="source-file" type="file" accept=".pdf,.docx,.txt,.md,.markdown" className={field} onChange={fileSelected} />
    <label htmlFor="source-text" className="mb-2 mt-4 block">Или вставьте текст резюме</label>
    <textarea id="source-text" className={`${field} min-h-44`} value={text} onChange={(event) => {
      const next = event.target.value;
      if (next.length > 6 * 1024 * 1024 || new TextEncoder().encode(next).length > 6 * 1024 * 1024) {
        setDraftError("Вставленный текст превышает 6 МБ. Сократите его перед импортом.");
        return;
      }
      setDraftError(null);
      onText(next);
    }} />
    <div className="my-3 flex flex-wrap gap-2">
      <button type="button" className={primary} disabled={!text || state.pending} onClick={() => void workflow.paste(text)}>Извлечь вставленный текст</button>
      {state.pending && <button type="button" className={control} onClick={() => workflow.cancel()}>Отменить импорт</button>}
      <button type="button" disabled={exampleDisabled} onClick={onExample} className={control}>Загрузить вымышленный пример</button>
    </div>
    <p className="text-sm text-muted">Извлечение выполняется локально. Обработка и генерация текста недоступны. Оригиналы и исправления остаются в памяти вкладки до явного сохранения проекта.</p>
    {state.pending && <p role="status" className="mt-3 text-sm">Читаем источник…</p>}
    {state.error && <p role="alert" className="mt-3 text-sm text-danger">{state.error}</p>}
    {draftError && <p role="alert" className="mt-3 text-sm text-danger">{draftError}</p>}
    {state.entries.length > 0 && <div className="mt-5 border-t border-outline pt-4">
      <label htmlFor="imported-source" className="mb-2 block font-semibold">Принятые источники ({state.entries.length})</label>
      <select id="imported-source" className={field} value={state.selectedId ?? ""} onChange={(event) => { workflow.select(event.target.value); setPage(0); }}>
        {state.entries.map((entry) => <option key={entry.result.sourceId} value={entry.result.sourceId}>{entry.result.originalName}</option>)}
      </select>
      {!clearPrompt ? <button type="button" className={`${control} mt-3`} onClick={() => setClearPrompt(true)}>Очистить импорт</button>
        : <div className="mt-3 flex flex-wrap items-center gap-2"><span className="text-sm text-danger">Несохранённые источники и исправления будут удалены.</span>
          <button type="button" className={control} onClick={() => { workflow.clear(); setClearPrompt(false); }}>Подтвердить очистку</button>
          <button type="button" className={control} onClick={() => setClearPrompt(false)}>Оставить</button></div>}
    </div>}
    {selected && <div className="mt-5 space-y-4 border-t border-outline pt-4">
      <div><h3 className="font-semibold">{selected.result.originalName}</h3>
        <p className="text-sm text-muted">{selected.result.sourceKind.toUpperCase()} · {selected.result.byteLength} байт · {selected.result.pageCount ? `${selected.result.pageCount} стр. · ` : ""}{selected.result.units.length} фрагментов · {selected.result.gaps.length} пробелов в извлечении</p>
        <div className="mt-2 flex flex-wrap gap-2"><button type="button" className={control} onClick={downloadOriginal}>Скачать исходный файл</button>
          {originalUrl && <a href={originalUrl} target="_blank" rel="noreferrer" className={control}>Открыть оригинал PDF</a>}</div>
      </div>
      {selected.result.links.length > 0 && <details className="text-sm"><summary className="cursor-pointer">Ссылки в исходном DOCX ({selected.result.links.length})</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">{selected.result.links.map((link) => <li key={`${link.part}:${link.relationshipId}`} className="break-all">{link.target}</li>)}</ul>
        <p className="mt-1 text-xs text-muted">Адреса сохранены как текст; приложение их не открывает при извлечении.</p>
      </details>}
      {selected.result.gaps.length > 0 && <section><h3 className="mb-2 font-semibold">Требуется проверка</h3><div className="max-h-80 space-y-3 overflow-y-auto">
        {selected.result.gaps.map((gap, index) => <div key={`${gap.code}-${index}`} className="rounded border border-outline bg-soft p-3 text-sm">
          <p>{locationLabel(gap.location)} · {gapLabel(gap.code)}</p>
          <label htmlFor={`gap-${index}`} className="mt-2 block">Ваш текст для этого места</label>
          <textarea id={`gap-${index}`} className={`${field} mt-1 min-h-20`} value={selected.overlays[`gap:${index}`] ?? ""}
            onChange={(event) => workflow.overlay(selected.result.sourceId, `gap:${index}`, event.target.value)} />
          <p className="mt-1 text-xs text-muted">Исправление пользователя хранится отдельно от извлечённого текста.</p>
        </div>)}</div></section>}
      <section><h3 className="mb-2 font-semibold">Извлечённый текст в порядке парсера</h3>
        <p className="mb-2 text-xs text-muted">Порядок не утверждает смысловой порядок колонок. Исходный текст не меняется при исправлении.</p>
        <div className="space-y-3">{units.slice(shownPage * 100, (shownPage + 1) * 100).map((unit) => <div key={unit.id} className="rounded border border-outline p-3 text-sm">
          <p className="mb-1 text-xs text-muted">{locationLabel(unit.location)}</p>
          <pre className="whitespace-pre-wrap break-words font-sans">{unit.text || "[текст не найден]"}</pre>
          <label htmlFor={`overlay-${unit.id}`} className="mt-2 block">Ваше исправление фрагмента</label>
          <textarea id={`overlay-${unit.id}`} className={`${field} mt-1 min-h-16`} value={selected.overlays[`unit:${unit.id}`] ?? ""}
            onChange={(event) => workflow.overlay(selected.result.sourceId, `unit:${unit.id}`, event.target.value)} />
        </div>)}</div>
        {pageCount > 1 && <div className="mt-3 flex items-center gap-2"><button type="button" className={control} disabled={shownPage === 0} onClick={() => setPage(shownPage - 1)}>Назад</button>
          <span className="text-sm">Фрагменты: страница {shownPage + 1} из {pageCount}</span>
          <button type="button" className={control} disabled={shownPage + 1 === pageCount} onClick={() => setPage(shownPage + 1)}>Далее</button></div>}
      </section>
    </div>}
  </section>;
}
