import { useRef } from "react";
import { hasInput, type ResumeInput } from "../../rich/import-source";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

export function SourceForm({ input, change, busy, process, textDraft, allowTextRewrite, changeTextRewrite }: {
  input: ResumeInput; change: (input: ResumeInput) => void; busy: boolean;
  process: () => void; textDraft: string; allowTextRewrite: boolean; changeTextRewrite: (allowed: boolean) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const name = input.kind === "file" ? input.file.name : null;
  return <section className="new-screen" aria-label="Новое резюме"><div className="source-form">
    <h2>Добавить исходник</h2>
    <button className="dropzone" type="button" disabled={busy} onClick={() => fileInput.current?.click()}
      onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file && !busy) change({ kind: "file", file }); }}>
      <span className="upload-mark"><Icon name="upload" /></span><span><strong>Выбрать файл</strong><small>PDF, DOCX, TXT, Markdown</small></span>
    </button>
    <input ref={fileInput} hidden type="file" aria-label="Исходное резюме" accept=".pdf,.docx,.txt,.md,.markdown" disabled={busy}
      onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) change({ kind: "file", file }); }} />
    {name && <div className="source-filename"><Icon name="file" /><span>{name}</span>{input.kind === "file" && <button className="icon" disabled={busy} aria-label="Убрать файл" onClick={() => change({ kind: "text", text: textDraft })}><Icon name="close" /></button>}</div>}
    <label htmlFor="source-text">Текст резюме</label><textarea className="source-text" id="source-text" aria-label="Текст резюме" placeholder="Имя, опыт работы, навыки…"
      disabled={busy || input.kind === "file"} value={textDraft} onChange={event => change({ kind: "text", text: event.currentTarget.value })} />
    {input.kind === "file" && <p className="small muted">Будет обработан выбранный файл. Уберите его, чтобы использовать текст.</p>}
    <label className="source-rewrite"><input type="checkbox" checked={allowTextRewrite} disabled={busy}
      aria-label="Разрешить переписывание текста" aria-describedby="source-rewrite-help" onChange={event => changeTextRewrite(event.currentTarget.checked)} />
      <span>Разрешить переписывание текста<small id="source-rewrite-help">Без галочки — только оформление.</small></span></label>
    <div className="source-bottom"><Button className="ml-auto" variant="primary" busy={busy} busyLabel="Подготовка…" disabled={!hasInput(input)} onClick={process}>Обработать<Icon name="arrow" /></Button></div>
  </div></section>;
}
