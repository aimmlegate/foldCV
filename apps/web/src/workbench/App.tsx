import { errorMessage } from "../errors/messages";
import { useEffect, useState } from "react";
import { ConnectionWorkflow, connectionSummary, type ConnectionView } from "../connection/workflow";
import { TemplateEditor } from "../rich/TemplateEditor";
import { AssistantDrawer } from "../assistant/Drawer";
import { useResumeWorkspace } from "./useResumeWorkspace";
import { History } from "./layout/History";
import { Header } from "./layout/Header";
import { SourceForm } from "./import/SourceForm";
import { PreDraft } from "./import/PreDraft";
import { TaskProgress } from "./import/TaskProgress";
import { TaskNotices } from "./import/TaskNotices";
import { sourceSummary } from "./import/progress";
import { Settings } from "./settings/Settings";
import { readPaneOrder, savePaneOrder, type PaneOrder } from "./settings/interface";
import { FileDialog, type FileMode } from "./files/FileDialog";
import { projectFilename } from "./files/filename";
import { Icon } from "./ui/Icon";
import { OperationStatus } from "./ui/OperationStatus";
import { NotificationCenter, NotificationProvider, NotificationSection } from "./ui/NotificationCenter";

export function App({ portalHost }: { portalHost: HTMLElement }) {
  const workspace = useResumeWorkspace();
  const { template, projects, error, status, setStatus, busy, settings, setSettings,
    templateEditor, assistant, action, fresh, open, remove, archive, process, upload, exportFile, imports, importActions } = workspace;
  const shown = template?.response ?? null;
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600);
  const [paneOrder, setPaneOrder] = useState(readPaneOrder);
  const changePaneOrder = (order: PaneOrder) => { savePaneOrder(order); setPaneOrder(order); };
  useEffect(() => {
    const narrow = matchMedia("(max-width: 600px)"), collapse = () => { if (narrow.matches) setCollapsed(true); };
    narrow.addEventListener("change", collapse); return () => narrow.removeEventListener("change", collapse);
  }, []);
  const [connection, setConnection] = useState<ConnectionView | null>(null);
  const [settingsVisited, setSettingsVisited] = useState(false), [fileMode, setFileMode] = useState<FileMode | null>(null);
  useEffect(() => { const workflow = new ConnectionWorkflow(setConnection); void workflow.peek(); return () => workflow.close(); }, []);
  // The import screen shows only inside the importing resume; other resumes open and edit meanwhile.
  const shownImport = shown ? imports.get(shown.workspace.projectId) : undefined;
  const view = !template ? "source" : template.response.workspace.project ? "editor" : shownImport ? "template_progress" : "pre_draft";
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
    await templateEditor.current?.navigate();
    if (!current()) return;
    setSettingsVisited(true); setSettings(true); if (innerWidth <= 600) setCollapsed(true);
  });
  function openFile(mode: FileMode) {
    workspace.dismissError();
    if (mode !== "export") { setFileMode(mode); return; }
    void action(async current => {
      await templateEditor.current?.flush();
      if (current()) setFileMode(mode);
    });
  }
  const projectTitle = shown?.identity?.title ?? shown?.workspace.title ?? "resume";
  const filename = projectFilename(projectTitle, fileMode === "export" ? "docx" : "foldcv");
  const navigate = (id: string) => open(id).then(done => { if (done && innerWidth <= 600) setCollapsed(true); return done; });
  const templatePackage = template?.response.workspace.project?.templatePackage.definition;
  return <NotificationProvider><main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv" data-busy={busy}>
    <History projects={projects} activeId={shown?.workspace.projectId ?? null} busy={busy} collapse={() => setCollapsed(true)}
      fresh={() => { void fresh(); if (innerWidth <= 600) setCollapsed(true); }} open={navigate} remove={remove} archive={archive} openFile={() => openFile("open")} settings={openSettings}
      connection={connectionSummary(connection?.snapshot ?? null)} error={error} />
    <section className="main-area">
      <Header title={settings ? "Настройки" : shown?.identity?.title ?? shown?.workspace.title ?? (workspace.loading ? "Открываем резюме…" : "Новое резюме")}
        subtitle={settings ? "FoldCV" : shown?.identity?.subtitle || "Рабочий документ"} collapsed={collapsed} expand={() => setCollapsed(false)} status={status}
        ready={!settings && view === "editor"} busy={busy} save={() => openFile("save")} exportFile={() => openFile("export")}
        retrySave={status !== "Сохранено" && status !== "Изменения сохраняются…" ? () => void action(async current => { await templateEditor.current?.flush(); if (current()) setStatus("Сохранено"); }) : undefined}
        activity={<NotificationCenter />} />
      <NotificationSection count={Number(!!error && !fileMode)}>
        <section className="notice-group" aria-label="Ошибки"><h3>Ошибки</h3>
          {error && !fileMode && <div className="notification-error" role="alert"><p>{errorMessage(error)}</p>
            <button className="icon" aria-label="Скрыть ошибку" onClick={workspace.dismissError}><Icon name="close" /></button></div>}
        </section>
      </NotificationSection>
      <TaskNotices entries={imports} activeId={shown?.workspace.projectId ?? null}
        titleOf={id => projects?.entries.find(entry => entry.projectId === id)?.title} stop={importActions.stop}
        close={importActions.dismiss} open={id => void navigate(id)} />
      {busy && workspace.operation && !fileMode && <div className="workspace-operation">
        <OperationStatus label={workspace.operation.label} timed startedAt={workspace.operation.startedAt} />
      </div>}
      <div className="screen uir-proof-screen" hidden={settings}>
        {view === "template_progress" && shownImport && <TaskProgress entry={shownImport} source={sourceSummary(shown)} busy={busy}
          stop={() => importActions.stop(shownImport.projectId)} retry={() => importActions.retry(shownImport.projectId)}
          close={() => importActions.dismiss(shownImport.projectId)} open={() => importActions.reopen(shownImport.projectId)} />}
        {view === "pre_draft" && <PreDraft key={template?.response.workspace.projectId} ask={!template?.response.workspace.preDraft?.templateOperations.length}
          busy={busy} connection={connection?.snapshot ?? null} resume={options => void workspace.resumeTemplate(options)} />}
        {workspace.loading && <div className="workspace-loading"><OperationStatus label="Открываем резюме" timed /></div>}
        {view === "editor" && template?.response.workspace.project && <TemplateEditor key={`${template.response.workspace.projectId}:${workspace.openingEpoch}`}
          initial={template.response} connection={template.connection}
          onStatus={setStatus} onShown={workspace.acknowledgeTemplate} ref={templateEditor} portalHost={portalHost} paneOrder={paneOrder}
          assistant={<AssistantDrawer key={template.response.workspace.projectId} projectId={template.response.workspace.projectId} editor={templateEditor}
            settingsOpen={settings} ref={assistant} onProjectLifecycle={kind => workspace.projectLifecycle(template.response.workspace.projectId, kind)}
            title={projectTitle} settings={openSettings} />} />}
        {view === "source" && !workspace.loading && <SourceForm active={!settings} busy={busy} connection={connection?.snapshot ?? null}
          process={(file, options, templateId) => void process(file, options, templateId)} />}
      </div>
      {settingsVisited && <div className="screen" hidden={!settings}><Settings open={settings} close={() => void action(async current => { await templateEditor.current?.resume(); if (current()) setSettings(false); })} connectionChanged={setConnection} paneOrder={paneOrder} changePaneOrder={changePaneOrder} /></div>}
    </section>
    {fileMode && <FileDialog key={fileMode} mode={fileMode} title={projectTitle} subtitle={shown?.identity?.subtitle ?? ""} filename={filename}
      templateName={templatePackage ? `${templatePackage.template.name} · ${templatePackage.template.revision}` : undefined}
      error={error} busy={busy} operation={workspace.operation?.label} close={() => setFileMode(null)} download={() => exportFile(fileMode === "export" ? "export" : "archive",
        current => projectFilename(current.identity?.title ?? current.workspace.title, fileMode === "export" ? "docx" : "foldcv"))}
      upload={async file => { const done = await upload(file); if (done) { setSettings(false); if (innerWidth <= 600) setCollapsed(true); } return done; }} />}
  </main></NotificationProvider>;
}
