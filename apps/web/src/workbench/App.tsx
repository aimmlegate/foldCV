import { errorMessage } from "../errors/messages";
import { useEffect, useState } from "react";
import { ConnectionWorkflow, type ConnectionView } from "../connection/workflow";
import { RichEditor } from "../rich/Editor";
import { TemplateEditor } from "../rich/TemplateEditor";
import { AssistantDrawer } from "../assistant/Drawer";
import { projectRequest, readTimeline } from "../rich/api";
import type { TimelineReport } from "../contracts/generated/timeline_report";
import { useResumeWorkspace, warningLabel } from "./useResumeWorkspace";
import { History } from "./layout/History";
import { Header } from "./layout/Header";
import { SourceForm } from "./import/SourceForm";
import { Progress } from "./import/Progress";
import { TaskProgress } from "./import/TaskProgress";
import { Assessment } from "./import/Assessment";
import { importView, reviewId } from "./import/view";
import { Settings } from "./settings/Settings";
import { readPaneOrder, savePaneOrder, type PaneOrder } from "./settings/interface";
import { FileDialog, type FileMode } from "./files/FileDialog";
import { projectFilename } from "./files/filename";
import { useGlobalJobs } from "../background/useGlobalJobs";
import { projectActivity } from "../background/status";
import { BackgroundJobs } from "./background/BackgroundJobs";
import { Icon } from "./ui/Icon";
import { OperationStatus } from "./ui/OperationStatus";
import { groupedWarnings, processingFailure } from "./import/notices";
import { NotificationCenter, NotificationProvider, NotificationSection } from "./ui/NotificationCenter";

export function App({ portalHost }: { portalHost: HTMLElement }) {
  const workspace = useResumeWorkspace();
  const jobs = useGlobalJobs();
  const { response, template, writer, background, projects, input, setInput, textDraft, error, status, setStatus, busy, settings, setSettings,
    editor, templateEditor, assistant, acknowledge, action, fresh, open, remove, archive, process, upload, exportFile } = workspace;
  // The shown opening is V1 or V7; only the editor and file paths differ.
  const shown = response ?? template?.response ?? null, mounted = () => editor.current ?? templateEditor.current;
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600);
  const [paneOrder, setPaneOrder] = useState(readPaneOrder);
  const changePaneOrder = (order: PaneOrder) => { savePaneOrder(order); setPaneOrder(order); };
  useEffect(() => {
    const narrow = matchMedia("(max-width: 600px)"), collapse = () => { if (narrow.matches) setCollapsed(true); };
    narrow.addEventListener("change", collapse); return () => narrow.removeEventListener("change", collapse);
  }, []);
  const [reviewed, setReviewed] = useState<string | null>(null), [sourceOpen, setSourceOpen] = useState(false);
  const [connection, setConnection] = useState<ConnectionView | null>(null);
  const [settingsVisited, setSettingsVisited] = useState(false), [fileMode, setFileMode] = useState<FileMode | null>(null);
  const [timeline, setTimeline] = useState<TimelineReport | null>(null);
  useEffect(() => { const workflow = new ConnectionWorkflow(setConnection); void workflow.peek(); return () => workflow.close(); }, []);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  const source = response?.workspace.preDraft?.sources.find(item => item.id === response.workspace.preDraft?.selectedSourceId);
  const view = workspace.importTask?.state === "running" && busy ? "template_progress" : template ? "editor" : importView(response, reviewed, sourceOpen);
  const sourceWarnings = response?.workspace.warnings ?? [];
  const draftWarnings = sourceWarnings.length ? [] : groupedWarnings(response?.workspace.preDraft?.warnings ?? [], response?.workspace.preDraft?.sources);
  const failure = processingFailure(generation);
  useEffect(() => {
    if (settings || view !== "editor") return;
    const save = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey || event.key.toLowerCase() !== "s") return;
      event.preventDefault();
      if (event.isComposing || busy || document.querySelector("dialog[open]")) return;
      workspace.dismissError(); setFileMode("save");
    };
    window.addEventListener("keydown", save); return () => window.removeEventListener("keydown", save);
  }, [settings, view, busy, workspace.dismissError]);
  const openSettings = () => void action(async current => {
    await mounted()?.navigate();
    if (!current()) return;
    setSettingsVisited(true); setSettings(true); if (innerWidth <= 600) setCollapsed(true);
  });
  function openFile(mode: FileMode) {
    workspace.dismissError();
    if (mode !== "export") { setFileMode(mode); return; }
    void action(async current => {
      if (template) { await templateEditor.current?.flush(); if (current()) { setTimeline(null); setFileMode(mode); } return; }
      const saved = editor.current ? await editor.current.flush() : response;
      if (!current()) return;
      const timeline = saved ? await readTimeline(saved.workspace.projectId).catch(() => null) : null;
      if (!current()) return;
      setTimeline(timeline); setFileMode(mode);
    });
  }
  const projectTitle = shown?.identity?.title ?? shown?.workspace.title ?? "resume";
  const filename = projectFilename(projectTitle, fileMode === "export" ? "docx" : "foldcv");
  const navigate = (id: string) => open(id).then(done => { if (done) { setSourceOpen(false); if (innerWidth <= 600) setCollapsed(true); } return done; });
  return <NotificationProvider><main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv" data-busy={busy}>
    <History projects={projects} activeId={shown?.workspace.projectId ?? null} activity={projectActivity(jobs.view.jobs)} busy={busy || creating && !background} collapse={() => setCollapsed(true)}
      fresh={() => { void fresh(); setSourceOpen(false); if (innerWidth <= 600) setCollapsed(true); }} open={navigate} remove={remove} archive={archive} openFile={() => openFile("open")} settings={openSettings}
      connection={connection?.snapshot.state === "connected" ? "Codex · подписка" : connection?.snapshot.state === "unchecked" ? "Подключение не проверено" : "Модель отключена"} />
    <section className="main-area">
      <Header title={settings ? "Настройки" : shown?.identity?.title ?? shown?.workspace.title ?? (workspace.loading ? "Открываем резюме…" : "Новое резюме")}
        subtitle={settings ? "FoldCV" : shown?.identity?.subtitle || "Рабочий документ"} collapsed={collapsed} expand={() => setCollapsed(false)} status={status}
        ready={!settings && view === "editor"} busy={busy} save={() => openFile("save")} exportFile={() => openFile("export")}
        rename={!settings && template?.connection ? title => { void workspace.renameTemplate(title); } : undefined}
        retrySave={status !== "Сохранено" && status !== "Изменения сохраняются…" && status !== "Требуется восстановление черновика" ? () => void action(async current => { await mounted()?.flush(); if (current()) setStatus("Сохранено"); }) : undefined}
        activity={<><NotificationCenter />{jobs.view.enabled && <BackgroundJobs registry={jobs.registry} view={jobs.view} openProject={navigate} />}</>} />
      <NotificationSection count={Number(!!error && !fileMode) + Number(!!jobs.view.error)}>
        <section className="notice-group" aria-label="Ошибки"><h3>Ошибки</h3>
          {error && !fileMode && <div className="notification-error" role="alert"><p>{errorMessage(error)}</p>
            <button className="icon" aria-label="Скрыть сообщение" onClick={workspace.dismissError}><Icon name="close" /></button></div>}
          {jobs.view.error && <p className="job-error" role="alert">Не удалось обновить задачи. Последнее известное состояние сохранено.</p>}
        </section>
      </NotificationSection>
      <NotificationSection count={sourceWarnings.length + draftWarnings.length + Number(!!failure)}>
        <section className="notice-group" aria-label="Замечания к исходнику"><h3>Замечания к исходнику</h3>
          {sourceWarnings.map(warning => <p className="notice warning" key={warning.id}>{warningLabel(warning.code)}
            {(warning.count ?? 1) > 1 && ` Повторов: ${warning.count}.`}
            {(warning.locations ?? []).map(location => `${location.sourceId}${location.page ? `, стр. ${location.page}` : ""}`).join("; ")}</p>)}
          {draftWarnings.map((warning, index) => <p className="notice warning" key={`${warning}:${index}`}>{warning}</p>)}
          {failure && <p className="notice warning" role="alert">{failure}</p>}
        </section>
      </NotificationSection>
      {busy && workspace.operation && !fileMode && <div className="workspace-operation">
        <OperationStatus label={workspace.operation.label} timed startedAt={workspace.operation.startedAt} />
        {workspace.operation.cancel && <button type="button" className="text-button" onClick={() => void workspace.operation?.cancel?.()}>Остановить импорт</button>}
      </div>}
      <div className="screen uir-proof-screen" hidden={settings}>
        {view === "template_progress" && workspace.importTask && <TaskProgress task={workspace.importTask}
          cancel={async () => { await workspace.operation?.cancel?.(); }} />}
        {view === "editor" && template && !template.response.workspace.project && <section className="progress-screen"><div className="progress-content">
          <h2>Импорт резюме</h2><p>Исходник и промежуточные результаты сохранены.</p>
          <button type="button" disabled={busy} onClick={() => void workspace.resumeTemplate()}>Продолжить импорт</button>
        </div></section>}
        {workspace.loading && <div className="workspace-loading"><OperationStatus label="Открываем резюме" detail="Загружаем документ, факты и историю проекта." timed /></div>}
        {view === "progress" && response && generation && <Progress key={`${response.workspace.projectId}:${generation.id}`} response={{ ...response, generation }} sourceName={source?.originalName ?? (input.kind === "file" ? input.file.name : "Вставленный текст")} busy={busy}
          cancel={() => void action(async () => acknowledge(await projectRequest(`/${response.workspace.projectId}/cancel`, "POST", {})), "Останавливаем обработку")} />}
        {view === "assessment" && response && <Assessment response={response} open={() => setReviewed(reviewId(response))} back={() => setSourceOpen(true)} />}
        {view === "editor" && response?.workspace.project && <>
          <RichEditor key={`${response.workspace.projectId}:${workspace.openingEpoch}`} initial={response} writer={writer} acknowledge={acknowledge} onStatus={setStatus} ref={editor} portalHost={portalHost} paneOrder={paneOrder}
            onComparisonOpen={() => setCollapsed(true)} />
        </>}
        {view === "editor" && template?.response.workspace.project && (template.connection
          ? <TemplateEditor key={`${template.response.workspace.projectId}:${workspace.openingEpoch}`} initial={template.response} connection={template.connection}
            onStatus={setStatus} onShown={workspace.acknowledgeTemplate} ref={templateEditor} portalHost={portalHost}
            assistant={<AssistantDrawer key={template.response.workspace.projectId} projectId={template.response.workspace.projectId} editor={templateEditor}
              settingsOpen={settings} ref={assistant} onProjectLifecycle={kind => workspace.projectLifecycle(template.response.workspace.projectId, kind)}
              title={projectTitle} settings={openSettings} />} />
          : <p className="notice warning" role="alert">{errorMessage("JOB_DISABLED")}</p>)}
        {view === "source" && !workspace.loading && <SourceForm input={input} change={setInput} textDraft={textDraft} busy={busy || creating} sourceName={source?.originalName ?? null}
          allowTextRewrite={workspace.allowTextRewrite} changeTextRewrite={workspace.setAllowTextRewrite}
          strictTemplate={workspace.templateImport} strict={workspace.strictImport} changeStrict={workspace.setStrictImport}
          process={() => { setSourceOpen(false); void process(); }} />}
      </div>
      {settingsVisited && <div className="screen" hidden={!settings}><Settings close={() => void action(async current => { await mounted()?.resume(); if (current()) setSettings(false); })} connectionChanged={setConnection} paneOrder={paneOrder} changePaneOrder={changePaneOrder} /></div>}
    </section>
    {fileMode && <FileDialog key={fileMode} mode={fileMode} title={projectTitle} subtitle={shown?.identity?.subtitle ?? ""} filename={filename}
      templateName={template?.response.workspace.project ? `${template.response.workspace.project.templatePackage.definition.template.name} · ${template.response.workspace.project.templatePackage.definition.template.revision}` : undefined}
      timeline={timeline} error={error} busy={busy} operation={workspace.operation?.label} close={() => setFileMode(null)} download={() => exportFile(fileMode === "export" ? "export" : "archive",
        current => projectFilename(current.identity?.title ?? current.workspace.title, fileMode === "export" ? "docx" : "foldcv"))}
      upload={async file => { const done = await upload(file); if (done) { setSourceOpen(false); setSettings(false); if (innerWidth <= 600) setCollapsed(true); } return done; }} />}
  </main></NotificationProvider>;
}
