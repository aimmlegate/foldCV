import { errorMessage } from "../errors/messages";
import { lazy, Suspense, useEffect, useState, type CSSProperties } from "react";
import { ConnectionWorkflow, connectionSummary, type ConnectionView } from "../connection/workflow";
import { TemplateEditor } from "../rich/TemplateEditor";
import { AssistantDrawer } from "../assistant/Drawer";
import { useResumeWorkspace } from "./useResumeWorkspace";
import { APP_NAME } from "./app-name";
import { History } from "./layout/History";
import { Header } from "./layout/Header";
import { SourceForm } from "./import/SourceForm";
import { PreDraft } from "./import/PreDraft";
import { TaskProgress } from "./import/TaskProgress";
import { TaskNotices } from "./import/TaskNotices";
import { sourceSummary } from "./import/progress";
import { Settings } from "./settings/Settings";
import { readPaneOrder, savePaneOrder, type PaneOrder, readAppearance, saveAppearance, type Appearance } from "./settings/interface";
import { FileDialog, type FileMode } from "./files/FileDialog";
import { projectFilename, projectStem } from "./files/filename";
import { Icon } from "./ui/Icon";
import { OperationStatus } from "./ui/OperationStatus";
import { PanelHandle, readPanelSize, savePanelSize } from "./ui/PanelHandle";
import { NotificationCenter, NotificationProvider, NotificationSection } from "./ui/NotificationCenter";
import { screenTitle, visit, type Screen } from "./templates/screen";

// Loaded on first visit: the YAML parser and Monaco stay out of the startup bundle.
const TemplatesScreen = lazy(() => import("./templates/TemplatesScreen"));

const historyWidths = { minimum: 160, maximum: 360 };

export function App({ portalHost }: { portalHost: HTMLElement }) {
  const workspace = useResumeWorkspace();
  const { template, projects, error, status, setStatus, busy, screen, setScreen, showResume,
    templateEditor, assistant, action, fresh, open, remove, archive, process, upload, exportFile, printPdf, imports, importActions } = workspace;
  const shown = template?.response ?? null;
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600);
  const [historyWidth, setHistoryWidth] = useState(() => readPanelSize("history", historyWidths.minimum, historyWidths.maximum));
  const changeHistoryWidth = (value: number | null) => { setHistoryWidth(value); savePanelSize("history", value); };
  const [paneOrder, setPaneOrder] = useState(readPaneOrder);
  const changePaneOrder = (order: PaneOrder) => { savePaneOrder(order); setPaneOrder(order); };
  const [appearance, setAppearance] = useState(readAppearance);
  const changeAppearance = (value: Appearance) => { saveAppearance(value); setAppearance(value); };
  useEffect(() => {
    const narrow = matchMedia("(max-width: 600px)"), collapse = () => { if (narrow.matches) setCollapsed(true); };
    narrow.addEventListener("change", collapse); return () => narrow.removeEventListener("change", collapse);
  }, []);
  const [connection, setConnection] = useState<ConnectionView | null>(null);
  const [visited, setVisited] = useState<ReadonlySet<Screen>>(() => new Set()), [fileMode, setFileMode] = useState<FileMode | null>(null);
  const onResume = screen === "resume";
  useEffect(() => { const workflow = new ConnectionWorkflow(setConnection); void workflow.peek(); return () => workflow.close(); }, []);
  // The import screen shows only inside the importing resume; other resumes open and edit meanwhile.
  const shownImport = shown ? imports.get(shown.workspace.projectId) : undefined;
  const view = !template ? "source" : template.response.workspace.project ? "editor" : shownImport ? "template_progress" : "pre_draft";
  useEffect(() => {
    if (!onResume || view !== "editor") return;
    const save = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey || event.key.toLowerCase() !== "s") return;
      event.preventDefault();
      if (event.isComposing || busy || document.querySelector("dialog[open]")) return;
      workspace.dismissError(); setFileMode("save");
    };
    window.addEventListener("keydown", save); return () => window.removeEventListener("keydown", save);
  }, [onResume, view, busy, workspace.dismissError]);
  const openScreen = (next: Exclude<Screen, "resume">) => void action(async current => {
    await templateEditor.current?.navigate();
    if (!current()) return;
    setVisited(value => visit(value, next)); setScreen(next); if (innerWidth <= 600) setCollapsed(true);
  });
  const openSettings = () => openScreen("settings");
  const backToResume = () => void action(async current => { await templateEditor.current?.resume(); if (current()) showResume(); });
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
  return <NotificationProvider><main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv" data-busy={busy}
    data-history-sized={historyWidth === null ? undefined : "true"}
    style={historyWidth === null ? undefined : { "--history-width": `${String(historyWidth)}px` } as CSSProperties}>
    <History projects={projects} activeId={shown?.workspace.projectId ?? null} busy={busy} collapse={() => setCollapsed(true)}
      handle={<PanelHandle className="history-handle" label="Ширина списка резюме" axis="x" sign={1} value={historyWidth ?? (innerWidth <= 1280 ? 187 : 208)}
        minimum={historyWidths.minimum} maximum={historyWidths.maximum} change={changeHistoryWidth} reset={() => changeHistoryWidth(null)} />}
      fresh={() => { void fresh(); if (innerWidth <= 600) setCollapsed(true); }} open={navigate} remove={remove} archive={archive} openFile={() => openFile("open")} settings={openSettings} templates={() => openScreen("templates")}
      connection={connectionSummary(connection?.snapshot ?? null)} error={error} />
    <section className="main-area">
      <Header title={screenTitle(screen, shown?.identity?.title ?? shown?.workspace.title ?? (workspace.loading ? "Открываем резюме…" : "Новое резюме"))}
        subtitle={!onResume ? APP_NAME : shown?.identity?.subtitle || "Рабочий документ"} collapsed={collapsed} expand={() => setCollapsed(false)} status={status}
        ready={onResume && view === "editor"} busy={busy} save={() => openFile("save")} exportFile={() => openFile("export")}
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
      <div className="screen uir-proof-screen" hidden={!onResume}>
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
            settingsOpen={!onResume} ref={assistant} onProjectLifecycle={kind => workspace.projectLifecycle(template.response.workspace.projectId, kind)}
            title={projectTitle} settings={openSettings} />} />}
        {view === "source" && !workspace.loading && <SourceForm active={onResume} busy={busy} connection={connection?.snapshot ?? null}
          process={(file, options, templateId) => void process(file, options, templateId)} />}
      </div>
      {visited.has("settings") && <div className="screen" hidden={screen !== "settings"}><Settings open={screen === "settings"} close={backToResume} connectionChanged={setConnection} paneOrder={paneOrder} changePaneOrder={changePaneOrder} appearance={appearance} changeAppearance={changeAppearance} /></div>}
      {visited.has("templates") && <div className="screen" hidden={screen !== "templates"}>
        <Suspense fallback={<OperationStatus label="Загружаем шаблоны" />}><TemplatesScreen open={screen === "templates"} close={backToResume} settings={openSettings} /></Suspense></div>}
    </section>
    {fileMode && <FileDialog key={fileMode} mode={fileMode} title={projectTitle} subtitle={shown?.identity?.subtitle ?? ""} filename={filename}
      templateName={templatePackage ? `${templatePackage.template.name} · ${templatePackage.template.revision}` : undefined}
      error={error} busy={busy} operation={workspace.operation?.label} close={() => setFileMode(null)} download={() => exportFile(fileMode === "export" ? "export" : "archive",
        current => projectFilename(current.identity?.title ?? current.workspace.title, fileMode === "export" ? "docx" : "foldcv"))}
      print={() => printPdf(projectStem(projectTitle))}
      upload={async file => { const done = await upload(file); if (done) { showResume(); if (innerWidth <= 600) setCollapsed(true); } return done; }} />}
  </main></NotificationProvider>;
}
