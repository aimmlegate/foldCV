import { useEffect, useState } from "react";
import { ConnectionWorkflow, type ConnectionView } from "../connection/workflow";
import { RichEditor } from "../rich/Editor";
import { AssistantDrawer } from "../assistant/Drawer";
import { projectRequest, readTimeline } from "../rich/api";
import type { TimelineReport } from "../contracts/generated/timeline_report";
import { useResumeWorkspace, warningLabel } from "./useResumeWorkspace";
import { History } from "./layout/History";
import { Header } from "./layout/Header";
import { Dialog } from "./ui/Dialog";
import { SourceForm } from "./import/SourceForm";
import { Progress } from "./import/Progress";
import { Assessment } from "./import/Assessment";
import { importView, reviewId } from "./import/view";
import { Settings } from "./settings/Settings";
import { FileDialog, type FileMode } from "./files/FileDialog";
import { projectFilename } from "./files/filename";

export function App({ portalHost }: { portalHost: HTMLElement }) {
  const workspace = useResumeWorkspace();
  const { response, writer, background, projects, input, setInput, textDraft, error, status, setStatus, busy, settings, setSettings,
    editor, assistant, acknowledge, action, fresh, open, remove, process, upload, exportFile } = workspace;
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600);
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [reviewed, setReviewed] = useState<string | null>(null), [sourceOpen, setSourceOpen] = useState(false);
  const [connection, setConnection] = useState<ConnectionView | null>(null);
  const [settingsVisited, setSettingsVisited] = useState(false), [fileMode, setFileMode] = useState<FileMode | null>(null);
  const [timeline, setTimeline] = useState<TimelineReport | null>(null);
  useEffect(() => { const workflow = new ConnectionWorkflow(setConnection); void workflow.peek(); return () => workflow.close(); }, []);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  const source = response?.workspace.preDraft?.sources.find(item => item.id === response.workspace.preDraft?.selectedSourceId);
  const view = importView(response, reviewed, sourceOpen);
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
  const openSettings = () => void action(async () => {
    await editor.current?.navigate(); setSettingsVisited(true); setSettings(true); if (innerWidth <= 600) setCollapsed(true);
  });
  function openFile(mode: FileMode) {
    workspace.dismissError();
    if (mode !== "export") { setFileMode(mode); return; }
    void action(async () => {
      const current = editor.current ? await editor.current.flush() : response;
      setTimeline(current ? await readTimeline(current.workspace.projectId).catch(() => null) : null); setFileMode(mode);
    });
  }
  const projectTitle = response?.identity?.title ?? response?.workspace.title ?? "resume";
  const filename = projectFilename(projectTitle, fileMode === "export" ? "docx" : "foldcv");
  const navigate = (id: string) => open(id).then(done => { if (done) { setSourceOpen(false); if (innerWidth <= 600) setCollapsed(true); } return done; });
  return <main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv">
    <History projects={projects} activeId={response?.workspace.projectId ?? null} busy={busy || creating && !background} collapse={() => setCollapsed(true)}
      fresh={() => { void fresh(); setSourceOpen(false); if (innerWidth <= 600) setCollapsed(true); }} open={navigate} remove={remove} openFile={() => openFile("open")} settings={openSettings}
      connection={connection?.snapshot.state === "connected" ? "Codex · подписка" : connection?.snapshot.state === "unchecked" ? "Подключение не проверено" : "Модель отключена"} />
    <section className="main-area">
      <Header title={settings ? "Настройки" : response?.identity?.title ?? response?.workspace.title ?? "Новое резюме"}
        subtitle={settings ? "FoldCV" : response?.identity?.subtitle || "Рабочий документ"} collapsed={collapsed} expand={() => setCollapsed(false)} status={status}
        ready={!settings && view === "editor"} busy={busy} save={() => openFile("save")} exportFile={() => openFile("export")} />
      <div className="screen uir-proof-screen" hidden={settings}>
        {error && <p role="alert" className="notice error">{error}</p>}
        {view === "progress" && response && generation && <Progress generation={generation} sourceName={source?.originalName ?? (input.kind === "file" ? input.file.name : "Вставленный текст")} busy={busy}
          cancel={() => void action(async () => acknowledge(await projectRequest(`/${response.workspace.projectId}/cancel`, "POST", {})))} />}
        {view === "assessment" && response && <Assessment response={response} open={() => setReviewed(reviewId(response))} back={() => setSourceOpen(true)} />}
        {view === "editor" && response?.workspace.project && <>
          {status !== "Сохранено" && status !== "Изменения сохраняются…" && <button className="text-button" disabled={busy} onClick={() => void action(async () => { await editor.current?.flush(); setStatus("Сохранено"); })}>Повторить сохранение</button>}
          <RichEditor key={response.workspace.projectId} initial={response} writer={writer} acknowledge={acknowledge} onStatus={setStatus} ref={editor} portalHost={portalHost}
            onHistoryNavigation={() => assistant.current?.history()} onAssistantFence={saved => assistant.current?.fence(saved)}
            assistant={<AssistantDrawer key={response.workspace.projectId} projectId={response.workspace.projectId} editor={editor} settingsOpen={settings} ref={assistant} background={writer !== null}
              title={projectTitle} settings={openSettings} />}
            contextActions={response.workspace.warnings.length > 0 && <button onClick={() => setWarningsOpen(true)}>Замечания к исходнику</button>} />
        </>}
        {view === "source" && <SourceForm input={input} change={setInput} textDraft={textDraft} busy={busy || creating} sourceName={source?.originalName ?? null}
          process={() => { setSourceOpen(false); void process(); }} warnings={response?.workspace.preDraft?.warnings.map(warningLabel) ?? []}
          failure={generation?.status === "failed" ? "Не удалось завершить обработку." : generation?.status === "cancelled" ? "Обработка отменена." : generation?.status === "interrupted" ? "Обработка прервана." : null} />}
      </div>
      {settingsVisited && <div className="screen" hidden={!settings}><Settings close={() => void action(async () => { await editor.current?.resume(); setSettings(false); })} connectionChanged={setConnection} /></div>}
      <Dialog open={warningsOpen} close={() => setWarningsOpen(false)} title="Замечания к исходнику">
        {response?.workspace.warnings.map(warning => <p className="dialog-copy" key={warning.id}>{warningLabel(warning.code)}</p>)}
      </Dialog>
    </section>
    {fileMode && <FileDialog key={fileMode} mode={fileMode} title={projectTitle} subtitle={response?.identity?.subtitle ?? ""} filename={filename}
      timeline={timeline} error={error} busy={busy} close={() => setFileMode(null)} download={() => exportFile(fileMode === "export" ? "export" : "archive",
        current => projectFilename(current.identity?.title ?? current.workspace.title, fileMode === "export" ? "docx" : "foldcv"))}
      upload={async file => { const done = await upload(file); if (done) { setSourceOpen(false); setSettings(false); if (innerWidth <= 600) setCollapsed(true); } return done; }} />}
  </main>;
}
