import { useEffect, useState } from "react";
import { ConnectionWorkflow, type ConnectionView } from "../connection/workflow";
import { SettingsPanel } from "../next/SettingsPanel";
import { AssistantSettings } from "../assistant/Settings";
import { RichEditor } from "../rich/Editor";
import { NewResume } from "../rich/NewResume";
import { projectRequest } from "../rich/api";
import { useResumeWorkspace, stageLabels, warningLabel } from "./useResumeWorkspace";
import { History } from "./layout/History";
import { Header } from "./layout/Header";
import { Dialog } from "./ui/Dialog";

export function App({ portalHost }: { portalHost: HTMLElement }) {
  const workspace = useResumeWorkspace();
  const { response, projects, input, setInput, error, status, setStatus, busy, settings, setSettings,
    editor, acknowledge, action, fresh, open, remove, process, upload, exportFile } = workspace;
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600);
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [connection, setConnection] = useState<ConnectionView | null>(null);
  useEffect(() => { const workflow = new ConnectionWorkflow(setConnection); void workflow.peek(); return () => workflow.close(); }, [settings]);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  const source = response?.workspace.preDraft?.sources.find(item => item.id === response.workspace.preDraft?.selectedSourceId);
  const openSettings = () => void action(async () => { await editor.current?.flush(); setSettings(true); });
  const navigate = (id: string) => open(id).then(done => { if (done && innerWidth <= 600) setCollapsed(true); return done; });
  return <main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv-uir-proof">
    <History projects={projects} activeId={response?.workspace.projectId ?? null} busy={busy || creating} collapse={() => setCollapsed(true)}
      fresh={() => { void fresh(); if (innerWidth <= 600) setCollapsed(true); }} open={navigate} remove={remove} upload={file => void upload(file)} settings={openSettings}
      connection={connection?.snapshot.state === "connected" ? "Codex · подписка" : connection?.snapshot.state === "unchecked" ? "Подключение не проверено" : "Модель отключена"} />
    <section className="main-area">
      <Header title={settings ? "Настройки" : response?.identity?.title ?? response?.workspace.title ?? "Новое резюме"}
        subtitle={settings ? "FoldCV" : response?.identity?.subtitle || "Рабочий документ"} collapsed={collapsed} expand={() => setCollapsed(false)} status={status}
        ready={!settings && !!response?.workspace.project} busy={busy} save={() => void exportFile("archive")} exportFile={() => void exportFile("export")} />
      <div className="screen uir-proof-screen" hidden={settings}>
        {error && <p role="alert" className="notice error">{error}</p>}
        {creating && response && <div className="notice" role="status">{stageLabels[generation.stage]}…<button onClick={() => void action(async () => acknowledge(await projectRequest(`/${response.workspace.projectId}/cancel`, "POST", {})))}>Остановить</button></div>}
        {generation?.status === "failed" && <p className="notice error" role="alert">Обработка не завершилась: {generation.errorCode}. Исходник сохранён.</p>}
        {response?.workspace.project ? <>
          {status !== "Сохранено" && status !== "Изменения сохраняются…" && <button className="text-button" disabled={busy} onClick={() => void action(async () => { await editor.current?.flush(); setStatus("Сохранено"); })}>Повторить сохранение</button>}
          <RichEditor key={response.workspace.projectId} initial={response} acknowledge={acknowledge} onStatus={setStatus} ref={editor} appearance="prototype" portalHost={portalHost}
            contextActions={response.workspace.warnings.length > 0 && <button onClick={() => setWarningsOpen(true)}>Замечания к исходнику</button>} />
        </> : <NewResume input={input} change={setInput} busy={busy || creating} sourceName={source?.originalName ?? null} process={() => void process()} />}
      </div>
      {settings && <div className="screen uir-pending-settings"><SettingsPanel close={() => setSettings(false)} analysisChanged={() => {}} assistant={models => <AssistantSettings models={models} />} /></div>}
      <Dialog open={warningsOpen} close={() => setWarningsOpen(false)} title="Замечания к исходнику">
        {response?.workspace.warnings.map(warning => <p className="dialog-copy" key={warning.id}>{warningLabel(warning.code)}</p>)}
      </Dialog>
    </section>
  </main>;
}
