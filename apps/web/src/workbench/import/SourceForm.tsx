import { useEffect, useRef, useState } from "react";
import { preferencesRequest, saveImportModelRequest } from "../../api/client";
import { modelGroups, type ConnectionSnapshot } from "../../connection/workflow";
import type { ReasoningEffort } from "../../connection/reasoning";
import { errorMessage } from "../../errors/messages";
import { shownTemplate, templateImportStatus, type ImportOptions, type TemplateEntry } from "../../projects/api";
import { ModelOptions } from "../settings/ModelSelect";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { chosenEffort, EffortField, RewriteField } from "./ImportChoices";

/** A new resume from one file (PDF, DOCX, TXT, Markdown) with a template, the import model, its effort and the rewrite
 * choice. Without the template list the upload uses the default template. `active`: shown, not behind Settings. */
export function SourceForm({ active, busy, process, connection }: {
  active: boolean; busy: boolean; process: (file: File, options: ImportOptions, templateId: string | null) => void;
  connection: ConnectionSnapshot | null;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null), [rewrite, setRewrite] = useState(true);
  const [importModel, setImportModel] = useState<string | null>(null), [loaded, setLoaded] = useState(false);
  const [effort, setEffort] = useState<ReasoningEffort | null>(null);
  const [templates, setTemplates] = useState<TemplateEntry[]>([]), [templateId, setTemplateId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false), [modelError, setModelError] = useState("");
  const picked = useRef(false);
  // The form stays mounted behind Settings, which can change the default template, its versions and the import model.
  useEffect(() => {
    if (!active) return;
    let alive = true;
    void preferencesRequest().then(value => { if (alive) setImportModel(value.selectedImportModel ?? null); })
      .catch((error: unknown) => { if (alive) setModelError(errorMessage(error)); }).finally(() => { if (alive) setLoaded(true); });
    void templateImportStatus().then(value => {
      if (!alive) return;
      setTemplates(value.templates); setTemplateId(current => shownTemplate(value, current, picked.current));
    }).catch(() => {});
    return () => { alive = false; };
  }, [active]);
  const model = importModel ?? connection?.selectedModel ?? null;
  const reasoning = model ? connection?.modelReasoning?.[model] : undefined;
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
      value={templateId ?? ""} onChange={event => { picked.current = true; setTemplateId(event.currentTarget.value); }}>
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
          <ModelOptions groups={modelGroups(connection)} value={importModel} />
        </select></div>
      <EffortField effort={effort} reasoning={reasoning} disabled={busy} change={setEffort} />
      <RewriteField rewrite={rewrite} disabled={busy} change={setRewrite} />
      <Button className="import-process-button" variant="primary" busy={busy} busyLabel="Подготовка…" disabled={!file}
        onClick={() => { if (file) process(file, { allowTextRewrite: rewrite, effort: chosenEffort(effort, reasoning) }, templateId); }}>Обработать<Icon name="arrow" /></Button>
    </div>
    {modelError && <p className="notice error" role="alert">{modelError}</p>}
  </div></section>;
}
