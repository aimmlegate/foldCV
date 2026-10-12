import { useEffect, useMemo, useRef, useState } from "react";
import { FieldEditor, type FieldEditorHandle } from "./FieldEditor";
import { projectRequest, sourceRequest, migrationRequest, errorLabel, type Workspace } from "./api";
import { SourcePanel } from "./SourcePanel";
import { StructureControls } from "./StructureControls";
import { useEdits } from "./useEdits";
import { useRewrite } from "./useRewrite";
import { RewritePanel } from "./RewritePanel";
import { useExport } from "./useExport";
import { ExportPanel } from "./ExportPanel";
import { SettingsPanel } from "./SettingsPanel";
import { useAnalysis } from "./useAnalysis";
import { useRelated } from "./useRelated";
import { AnnotationActions } from "./Annotations";
import { ProjectsDialog } from "./ProjectsDialog";
import { usePortable } from "./usePortable";
import { MigrationNotice } from "./MigrationNotice";
import { StartProjects } from "./StartProjects";
import { StartDisclosure } from "./StartDisclosure";
import { GenerationProgress } from "./GenerationProgress";
import type { SourceContext } from "../contracts/generated/source_context";
import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import { documentFields } from "./fields";
import { useTheme } from "./theme";
import sample from "../../../../tests/fixtures/recovery/E1.txt?raw";

export function App() {
  const theme = useTheme();
  const [text, setText] = useState("");
  const [input, setInput] = useState<"text" | "file">("text");
  const [fileName, setFileName] = useState("");
  const [fileAvailable, setFileAvailable] = useState(false);
  const [activity, setActivity] = useState<"input" | "create" | "control" | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [durability, setDurability] = useState<GuiProjectResponse["durability"]>("pending");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [opening, setOpening] = useState(() => new URLSearchParams(location.search).has("project"));
  const [error, setError] = useState("");
  const [slot, setSlot] = useState<string | null>(null);
  const [hasSelection, setHasSelection] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [selectionFingerprint, setSelectionFingerprint] = useState<string | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [source, setSource] = useState<SourceContext | null>(null);
  const sourceEpoch = useRef(0);
  const editor = useRef<FieldEditorHandle>(null);
  const lastSlot = useRef("profile");
  const requestEpoch = useRef(0);
  const chooser = useRef<HTMLInputElement>(null);
  const generation = workspace?.generations.find(item => item.id === generationId);
  const document = workspace?.project?.document;
  const fields = useMemo(() => document ? documentFields(document) : [], [document]);
  function accept(response: GuiProjectResponse) {
    setWorkspace(response.workspace); setSelectionFingerprint(response.selectionFingerprint ?? null);
    setDurability(response.durability); setSaveError(response.saveError ?? null);
    const url = new URL(location.href); url.searchParams.set("project", response.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }
  const edits = useEdits(workspace, editor, accept);
  const analysis = useAnalysis(workspace, edits);
  const related = useRelated(editor, edits);
  const rewrite = useRewrite(editor, edits);
  const exporter = useExport(workspace, editor, edits);
  const portable = usePortable(edits);
  const editorKey = `${workspace?.projectId}:${fields.map(field => field.fieldId).join("|")}`;
  const initialArtifact = workspace?.project?.renders.find(render => render.artifactAvailable && render.docx);
  async function showMigration() {
    if (!workspace) return;
    const epoch = ++sourceEpoch.current;setSourceOpen(true);setSourceBusy(true);setSource(null);
    try { const result = await migrationRequest(workspace.projectId);if (epoch === sourceEpoch.current) setSource(result); }
    catch { setError("Не удалось прочитать историю переноса. Текущий текст остаётся в редакторе."); }
    finally { if (epoch === sourceEpoch.current) setSourceBusy(false); }
  }

  useEffect(() => {
    if (!workspace || !generationId || !generation || !["queued", "running"].includes(generation.status)) return;
    let alive = true;
    const id = workspace.projectId, epoch = requestEpoch.current;
    const timer = window.setTimeout(() => {
      void projectRequest(`/v1/projects/${id}`).then(result => {
        if (alive && epoch === requestEpoch.current) accept(result);
      }).catch(error => { if (alive) setError(errorLabel(error)); });
    }, 250);
    return () => { alive = false; clearTimeout(timer); };
  }, [workspace, generationId, generation]);

  useEffect(() => {
    const id = new URLSearchParams(location.search).get("project");
    if (!id) return;
    let alive = true;const epoch = requestEpoch.current;
    void projectRequest(`/v1/projects/${encodeURIComponent(id)}`).then(response => {
      if (!alive || epoch !== requestEpoch.current) return;
      accept(response);
      const active = response.workspace.project ?? response.workspace.preDraft;
      const sourceId = response.workspace.preDraft?.selectedSourceId;
      setInput(response.workspace.preDraft?.selectedInput ?? "text");
      setFileName(active?.sources.find(source => source.id === sourceId)?.originalName ?? "");
      setFileAvailable(response.workspace.preDraft?.selectedInput === "file" && active?.sources.some(source => source.id === sourceId) === true);
      setText(response.workspace.preDraft?.extractedText ?? "");
      setGenerationId(response.workspace.generations.at(-1)?.id ?? null);
    }).catch(error => { if (alive && epoch === requestEpoch.current) setError(errorLabel(error)); })
      .finally(() => { if (alive) setOpening(false); });
    return () => { alive = false; };
  }, []);

  async function choose(file: File) {
    const epoch = ++requestEpoch.current;
    setInput("file"); setFileName(file.name); setFileAvailable(false);setGenerationId(null);setActivity("input");setBusy(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await projectRequest(workspace ? `/v1/projects/${workspace.projectId}/input` : "/v1/projects/input", workspace ? "PUT" : "POST", body);
      if (epoch === requestEpoch.current) { accept(result);setFileAvailable(result.workspace.preDraft?.selectedInput === "file"); }
    } catch (error) { if (epoch === requestEpoch.current) setError(errorLabel(error)); }
    finally { if (epoch === requestEpoch.current) { setBusy(false);setActivity(null); } }
  }
  async function create() {
    const epoch = ++requestEpoch.current;
    setBusy(true);setActivity("create");setError("");
    try {
      const result = await projectRequest(workspace ? `/v1/projects/${workspace.projectId}/generations` : "/v1/projects", "POST",
        input === "text" ? { text } : {});
      if (epoch === requestEpoch.current) { accept(result); setGenerationId(result.generationId); }
    } catch (error) { setError(errorLabel(error)); }
    finally { setBusy(false);setActivity(null); }
  }
  async function control(action: "cancel" | "retry") {
    if (!workspace || !generationId) return;
    setBusy(true);setActivity("control");setError("");
    try {
      const result = await projectRequest(`/v1/projects/${workspace.projectId}/generations/${generationId}/${action}`, "POST", {});
      accept(result); setGenerationId(result.generationId);
    } catch (error) { setError(errorLabel(error)); }
    finally { setBusy(false);setActivity(null); }
  }
  const running = generation && ["queued", "running"].includes(generation.status);
  const usable = input === "text" ? !!text.trim() : fileAvailable && workspace?.preDraft?.selectedInput === "file"
    && workspace.preDraft.extractionFingerprint !== null && !!workspace.preDraft.extractedText.trim();
  async function showSettings() {
    if (!await edits.flushBeforeAction()) { setError("Завершите ввод и сохраните правки перед открытием настроек.");return; }
    setSourceOpen(false);rewrite.close();setSettingsOpen(true);
  }
  async function openProject(id: string) {
    setBusy(true);setError("");
    try {
      if (!await edits.flushBeforeAction(true)) { setError("Сначала сохраните текущие правки.");return; }
      await projectRequest(`/v1/projects/${encodeURIComponent(id)}`);
      if (!await edits.flushBeforeAction(true)) { setError("Сначала сохраните новые правки.");return; }
      location.assign(`/next.html?project=${encodeURIComponent(id)}`);
    } catch { setError("Не удалось открыть проект. Текущий ввод остаётся в окне."); }
    finally { setBusy(false); }
  }
  async function showSource() {
    if (!workspace || !selectionFingerprint) return;
    const captured = editor.current?.capture();
    const first = captured?.spans[0];
    const epoch = ++sourceEpoch.current;
    setSourceOpen(true); setSourceBusy(true); setSource(null);
    try {
      const context = await sourceRequest({ projectId: workspace.projectId, documentRevision: workspace.documentRevision,
        selection: captured && first ? { projectId: workspace.projectId, documentRevision: workspace.documentRevision,
          dependencyFingerprint: selectionFingerprint, spans: [first, ...captured.spans.slice(1)] } : null,
        fieldIds: captured && first ? [] : fields.filter(field => field.slotId === (slot ?? lastSlot.current)).map(field => field.fieldId) });
      if (epoch !== sourceEpoch.current) return;
      setSource(context);
      if (context.status === "stale") {
        const refreshed = await projectRequest(`/v1/projects/${workspace.projectId}`);
        if (epoch === sourceEpoch.current) accept(refreshed);
      }
    } catch (error) { if (epoch === sourceEpoch.current) setError(errorLabel(error)); }
    finally { if (epoch === sourceEpoch.current) setSourceBusy(false); }
  }
  return <main data-app="foldcv-next" className="next-shell">
    <header className="next-header">
      <strong className="next-brand">FoldCV.</strong>
      <button className="next-title" disabled={busy || opening || edits.locked} aria-label="Меню проекта" onClick={() => setProjectsOpen(true)}>{workspace?.title ?? "Новое резюме"}</button>
      <span className="next-save" role="status">{edits.saving ? "Сохраняем…" : edits.pending ? "Есть несохранённые правки" : workspace
        ? durability === "durable" ? "Сохранено" : durability === "failed" ? "Сохранение не удалось" : durability === "in_memory" ? "В памяти приложения" : "Сохраняем…" : ""}</span>
      <div className="next-actions">
        <button disabled={!workspace || portable.busy || busy} onClick={() => { void portable.save(); }}>Сохранить проект</button><button disabled={!document || edits.locked} onClick={() => { setSettingsOpen(false);setSourceOpen(false);rewrite.close();void exporter.start(); }}>Экспорт DOCX</button>
        <button disabled={busy || opening} onClick={() => { void showSettings(); }}>Настройки</button>
        <label className="next-theme">Тема <select aria-label="Тема" value={theme.mode} onChange={event => theme.select(event.target.value)}>
          <option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option>
        </select></label>
      </div>
    </header>
    {error && <p className="next-message text-danger" role="alert">{error}</p>}
    {edits.error && <p className="next-message text-danger" role="alert">{edits.error} <button onClick={edits.retry}>Повторить сохранение</button></p>}
    {rewrite.message && <p className="next-message" role="status">{rewrite.message}</p>}
    {analysis.message && <p className="next-message" role="status">{analysis.message}
      {analysis.retryable && <button onClick={() => { void analysis.retry(); }}>Повторить проверку</button>}</p>}
    {analysis.error && <p role="alert">{analysis.error}</p>}
    {related.message && <p className="next-message" role="status">{related.message}
      {related.retryable && <button onClick={() => { void related.retry(); }}>Повторить обновление</button>}</p>}
    {portable.message && <p className="next-message" role="status">{portable.message}</p>}
    {workspace && <MigrationNotice notices={workspace.migrationNotices} showText={() => { void showMigration(); }} />}
    {!exporter.open && exporter.message && <p className="next-message text-danger" role="alert">{exporter.message}</p>}
    {saveError && !edits.error && workspace && <p className="next-message text-danger" role="alert">Не удалось сохранить проект. Данные остаются в окне.
      <button onClick={() => { void projectRequest(`/v1/projects/${workspace.projectId}/save`, "POST", {}).then(accept).catch(error => setError(errorLabel(error))); }}>Повторить сохранение</button></p>}
    {generation && <GenerationProgress generation={generation} busy={busy} control={action => { void control(action); }} />}
    {generation && initialArtifact && workspace && <a className="next-download" download="resume.docx"
      href={`/v1/projects/${workspace.projectId}/renders/${initialArtifact.id}/docx`}>Скачать исходный DOCX</a>}
    {settingsOpen ? <SettingsPanel close={() => setSettingsOpen(false)} analysisChanged={analysis.preferenceChanged} /> : exporter.open ? <ExportPanel exporter={exporter} workspace={workspace} /> : document ? <section className="next-editor-surface" aria-label="Документ">
      <p className="next-editor-note">Правки сохраняются локально. Отметка «Сохранено» появляется после записи на диск.</p>
      <div className="next-editor-tools"><button disabled={sourceBusy} onPointerDown={event => event.preventDefault()}
        onClick={() => { void showSource(); }}>Показать исходник</button>
        <button disabled={!hasSelection || rewrite.busy || edits.locked} onPointerDown={event => event.preventDefault()}
          onClick={() => { setSourceOpen(false); void rewrite.open(); }}>Улучшить выделение</button>
        <button disabled={rewrite.busy || edits.locked} data-slot-owner={slot ?? lastSlot.current} onPointerDown={event => event.preventDefault()}
          onClick={() => { setSourceOpen(false); void rewrite.open(slot ?? lastSlot.current); }}>Улучшить текст блока</button>
        <button disabled={edits.locked} onPointerDown={event => event.preventDefault()} onClick={() => { rewrite.invalidate(); edits.restore(slot ?? lastSlot.current); }}>Отменить правку блока</button>
        <StructureControls document={document} send={edits.structural} periods={edits.periods} disabled={edits.locked} />
      </div>
      <AnnotationActions.Provider value={{ suggestions: workspace?.relatedUpdateSuggestions ?? [], fields,
        projectRevision: workspace?.projectRevision ?? 1, documentRevision: workspace?.documentRevision ?? 1,
        disabled: related.busy || edits.pending || edits.locked, apply: suggestion => { void related.apply(suggestion); } }}>
      <div className="next-document"><FieldEditor ref={editor} key={editorKey} fields={edits.overlay(fields)} editable={!edits.locked} theme={theme.resolved} annotations={workspace?.annotations ?? []}
        derived={edits.pending ? null : workspace?.derivedState} callbacks={{
        buffer: values => { rewrite.invalidate(); edits.buffer(values); }, selection: value => setHasSelection(value !== null), slot: value => { setSlot(value); if (value) lastSlot.current = value; }, departure: edits.departure,
        restore: value => { rewrite.invalidate(); edits.restore(value); }, completion: edits.completion, compositionEnd: edits.compositionEnd,
      }} /></div></AnnotationActions.Provider>
      <p className="next-editor-status" aria-live="polite">{slot ? "Редактирование текста" : ""}</p>
    </section> : opening ? <section className="next-start" role="status">Открываем сохранённый проект…</section> : <section className="next-start">
      <div className="next-intro"><p className="next-eyebrow">ХОРОШИЙ ТЕКСТ НАЧИНАЕТСЯ С ФАКТОВ</p>
        <h1>Дайте резюме<br />чистый лист.</h1><p>Добавьте исходник. Получите полный документ<br />для окончательных правок.</p>
        <StartProjects refreshKey={`${workspace?.projectId ?? ""}:${durability}`} disabled={busy || !!running} open={id => { void openProject(id); }} manage={() => setProjectsOpen(true)} /></div>
      <div className="next-input">
        <div className="next-upload" onDragOver={event => event.preventDefault()} onDrop={event => {
          event.preventDefault(); const file = event.dataTransfer.files[0]; if (file && !busy && !running) void choose(file);
        }}>
          <h2>Начните с резюме</h2><p>Перетащите файл сюда или выберите его на компьютере.</p><p>PDF, DOCX, TXT, Markdown</p>
          <button disabled={busy || !!running} onClick={() => chooser.current?.click()}>Выбрать файл</button>
          <input ref={chooser} type="file" accept=".pdf,.docx,.txt,.md,.markdown" aria-label="Файл резюме" hidden onChange={event => {
            const file = event.target.files?.[0]; if (file) void choose(file); event.target.value = "";
          }} />
        </div>
        <button className="next-sample" disabled={busy || !!running} onClick={() => { setText(sample);setInput("text");setGenerationId(null);setError(""); }}>Открыть пример</button>
        <label className="next-paste-label" htmlFor="resume-input">Или вставьте текст</label>
        <textarea id="resume-input" rows={8} maxLength={60000} disabled={busy || !!running}
          value={input === "file" ? fileAvailable ? workspace?.preDraft?.extractedText ?? "" : "" : text}
          onChange={event => { setText(event.target.value);setInput("text");setGenerationId(null);setError(""); }} />
        <p className="next-selected">Выбрано: {input === "file" ? fileName : "вставленный текст"}</p>
        {fileAvailable && workspace?.preDraft?.warnings.length ? <p className="next-warning" role="status">{usable
          ? durability === "durable" ? "Часть содержимого не удалось прочитать. Исходник и доступный текст сохранены локально." : "Часть содержимого не удалось прочитать. Текст доступен в окне; запись на диск не подтверждена."
          : "Доступного текста нет. Выберите другой файл или вставьте текст."}</p> : null}
        {activity && <p role="status">{activity === "input" ? "Читаем и сохраняем исходник…" : activity === "create" ? "Начинаем создание резюме…" : "Завершаем действие…"}</p>}
        <button className="next-create" disabled={!usable || busy || !!running || workspace !== null && durability !== "durable"} onClick={() => { void create(); }}>Создать резюме</button>
        <StartDisclosure settings={() => { void showSettings(); }} />
      </div>
    </section>}
    {sourceOpen && workspace && <SourcePanel context={source} workspace={workspace} loading={sourceBusy}
      close={() => { ++sourceEpoch.current; setSourceOpen(false); setSourceBusy(false); }} />}
    <RewritePanel rewrite={rewrite} />
    {projectsOpen && <ProjectsDialog workspace={workspace} edits={edits} accept={accept} close={() => setProjectsOpen(false)} />}
  </main>;
}
