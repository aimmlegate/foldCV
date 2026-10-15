import type { ResumeInput } from "./import-source";
import { hasInput } from "./import-source";

export function NewResume({ input, change, busy, sourceName, process }: {
  input: ResumeInput; change: (input: ResumeInput) => void; busy: boolean; sourceName: string | null;
  process: () => void;
}) {
  return <section className="rich-new-resume next-input" aria-label="Новое резюме">
    <h1>Новое резюме</h1>
    <p className="next-selected">Добавьте файл или вставьте текст. Модель проверит, похоже ли содержимое на резюме, затем извлечёт факты. В редакторе откроется исходный текст.</p>
    <div className="next-upload"><h2>Добавьте исходное резюме</h2>
      <input type="file" aria-label="Исходное резюме" accept=".pdf,.docx,.txt,.md,.markdown" disabled={busy}
        onChange={event => { const file = event.currentTarget.files?.[0]; if (file) change({ kind: "file", file }); event.currentTarget.value = ""; }} />
      {input.kind === "file" && <p>{input.file.name} <button disabled={busy} onClick={() => change({ kind: "text", text: "" })}>Убрать файл</button></p>}
    </div>
    <label className="next-paste-label">Или вставьте текст<textarea aria-label="Текст резюме" value={input.kind === "text" ? input.text : ""}
      disabled={busy} onChange={event => change({ kind: "text", text: event.target.value })} rows={12} /></label>
    {!hasInput(input) && sourceName && <p className="next-selected">Выбран источник: {sourceName}</p>}
    <button className="next-create" disabled={busy || (!hasInput(input) && !sourceName)} onClick={process}>Обработать</button>
  </section>;
}
