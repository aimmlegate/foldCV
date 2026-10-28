import { useEffect, useRef, useState } from "react";
import { preferencesRequest, saveImportModelRequest } from "../../api/client";
import type { ConnectionSnapshot } from "../../connection/workflow";
import { isReasoningEffort, type ReasoningEffort } from "../../connection/reasoning";
import { errorMessage } from "../../errors/messages";
import { templateImportStatus, type ImportOptions, type TemplateEntry } from "../../projects/api";
import { defaultReasoningLabel, reasoningLabels } from "../settings/ReasoningSelect";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

/** A new resume from one file (PDF, DOCX, TXT, Markdown) with a template, the import model, its effort and the rewrite
 * choice. Without the template list the upload uses the default template. */
export function SourceForm({ busy, process, connection }: {
  busy: boolean; process: (file: File, options: ImportOptions, templateId: string | null) => void; connection: ConnectionSnapshot | null;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null), [rewrite, setRewrite] = useState(true);
  const [importModel, setImportModel] = useState<string | null>(null), [loaded, setLoaded] = useState(false);
  const [effort, setEffort] = useState<ReasoningEffort | null>(null);
  const [templates, setTemplates] = useState<TemplateEntry[]>([]), [templateId, setTemplateId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false), [modelError, setModelError] = useState("");
  useEffect(() => {
    let alive = true;
    void preferencesRequest().then(value => { if (alive) setImportModel(value.selectedImportModel ?? null); })
      .catch((error: unknown) => { if (alive) setModelError(errorMessage(error)); }).finally(() => { if (alive) setLoaded(true); });
    void templateImportStatus().then(value => { if (alive) { setTemplates(value.templates); setTemplateId(value.defaultId); } }).catch(() => {});
    return () => { alive = false; };
  }, []);
  const models = connection?.models ?? [];
  const model = importModel ?? connection?.selectedModel ?? null;
  const reasoning = model ? connection?.modelReasoning?.[model] : undefined;
  const chosen = effort && reasoning?.supported.includes(effort) ? effort : null;
  async function changeModel(next: string | null) {
    setSaving(true); setModelError("");
    try { setImportModel((await saveImportModelRequest(next)).selectedImportModel ?? null); }
    catch (error) { setModelError(errorMessage(error)); } finally { setSaving(false); }
  }
  const choose = (next: File | undefined) => { if (next && !busy) setFile(next); };
  return <section className="new-screen" aria-label="Новое резюме"><div className="source-form">
    <h2>Добавить исходник</h2>
    <label htmlFor="import-template">Шаблон</label>
    <select className="model-select" id="import-template" aria-label="Шаблон" disabled={busy || templates.length === 0}
      value={templateId ?? ""} onChange={event => setTemplateId(event.currentTarget.value)}>
      {templates.length === 0 && <option value="">Шаблон по умолчанию</option>}
      {templates.map(entry => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
    </select>
    <button className="dropzone" type="button" disabled={busy} onClick={() => fileInput.current?.click()}
      onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); choose(event.dataTransfer.files[0]); }}>
      <span className="upload-mark"><Icon name="upload" /></span><span><strong>Выбрать файл</strong><small>PDF, DOCX, TXT, Markdown</small></span>
    </button>
    <input ref={fileInput} hidden type="file" aria-label="Исходное резюме" accept=".pdf,.docx,.txt,.md,.markdown" disabled={busy}
      onChange={event => { const next = event.currentTarget.files?.[0]; event.currentTarget.value = ""; choose(next); }} />
    {file && <div className="source-filename"><Icon name="file" /><span>{file.name}</span>
      <button className="icon" disabled={busy} aria-label="Убрать файл" onClick={() => setFile(null)}><Icon name="close" /></button></div>}
    <div className="source-bottom import-options">
      <div className="import-option"><label htmlFor="import-model">Модель</label>
        <select className="model-select" id="import-model" aria-label="Модель импорта" value={importModel ?? ""}
          disabled={busy || saving || !loaded || !connection?.metadataReady} onChange={event => void changeModel(event.currentTarget.value || null)}>
          <option value="">{connection?.selectedModel ? `Модель обработки · ${connection.selectedModel}` : "Модель обработки"}</option>
          {(importModel && !models.includes(importModel) ? [importModel, ...models] : models).map(name =>
            <option key={name} value={name} disabled={!models.includes(name)}>{name}{models.includes(name) ? "" : " · недоступна"}</option>)}
        </select></div>
      <div className="import-option"><label htmlFor="import-effort">Рассуждения</label>
        <select className="model-select" id="import-effort" aria-label="Уровень рассуждений импорта" value={chosen ?? ""}
          disabled={busy || !reasoning?.supported.length} onChange={event => {
            const next = event.currentTarget.value;
            setEffort(isReasoningEffort(next) ? next : null);
          }}>
          <option value="">{defaultReasoningLabel(reasoning?.default)}</option>
          {(reasoning?.supported ?? []).map(value => <option key={value} value={value}>{reasoningLabels[value]}</option>)}
        </select></div>
      <label className="import-rewrite" htmlFor="import-rewrite"><input className="switch" id="import-rewrite" type="checkbox" role="switch"
        checked={rewrite} disabled={busy} aria-describedby="import-rewrite-help" onChange={event => setRewrite(event.currentTarget.checked)} />
        <span>Переписывать текст<small id="import-rewrite-help">{rewrite ? "Модель улучшит формулировки." : "Только оформление."}</small></span></label>
      <Button className="import-process-button" variant="primary" busy={busy} busyLabel="Подготовка…" disabled={!file}
        onClick={() => { if (file) process(file, { allowTextRewrite: rewrite, effort: chosen }, templateId); }}>Обработать<Icon name="arrow" /></Button>
    </div>
    {modelError && <p className="notice error" role="alert">{modelError}</p>}
  </div></section>;
}
