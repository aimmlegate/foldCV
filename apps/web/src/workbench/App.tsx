import { useEffect, useState } from "react";
import { ConnectionWorkflow, type ConnectionView } from "../connection/workflow";
import { SettingsPanel } from "../next/SettingsPanel";
import { AssistantSettings } from "../assistant/Settings";
import { RichEditor } from "../rich/Editor";
import { projectRequest } from "../rich/api";
import { useResumeWorkspace, warningLabel } from "./useResumeWorkspace";
import { History } from "./layout/History";
import { Header } from "./layout/Header";
import { Dialog } from "./ui/Dialog";
import { SourceForm } from "./import/SourceForm";
import { Progress } from "./import/Progress";
import { Assessment } from "./import/Assessment";
import { importView, reviewId } from "./import/view";

export function App({ portalHost }: { portalHost: HTMLElement }) {
  const workspace = useResumeWorkspace();
  const { response, projects, input, setInput, textDraft, error, status, setStatus, busy, settings, setSettings,
    editor, acknowledge, action, fresh, open, remove, process, upload, exportFile } = workspace;
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600);
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [reviewed, setReviewed] = useState<string | null>(null), [sourceOpen, setSourceOpen] = useState(false);
  const [connection, setConnection] = useState<ConnectionView | null>(null);
  useEffect(() => { const workflow = new ConnectionWorkflow(setConnection); void workflow.peek(); return () => workflow.close(); }, [settings]);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  const source = response?.workspace.preDraft?.sources.find(item => item.id === response.workspace.preDraft?.selectedSourceId);
  const view = importView(response, reviewed, sourceOpen);
  const openSettings = () => void action(async () => { await editor.current?.flush(); setSettings(true); });
  const navigate = (id: string) => open(id).then(done => { if (done) { setSourceOpen(false); if (innerWidth <= 600) setCollapsed(true); } return done; });
  return <main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv-uir-proof">
    <History projects={projects} activeId={response?.workspace.projectId ?? null} busy={busy || creating} collapse={() => setCollapsed(true)}
      fresh={() => { void fresh(); setSourceOpen(false); if (innerWidth <= 600) setCollapsed(true); }} open={navigate} remove={remove} upload={file => { void upload(file); setSourceOpen(false); }} settings={openSettings}
      connection={connection?.snapshot.state === "connected" ? "Codex · подписка" : connection?.snapshot.state === "unchecked" ? "Подключение не проверено" : "Модель отключена"} />
    <section className="main-area">
      <Header title={settings ? "Настройки" : response?.identity?.title ?? response?.workspace.title ?? "Новое резюме"}
        subtitle={settings ? "FoldCV" : response?.identity?.subtitle || "Рабочий документ"} collapsed={collapsed} expand={() => setCollapsed(false)} status={status}
        ready={!settings && view === "editor"} busy={busy} save={() => void exportFile("archive")} exportFile={() => void exportFile("export")} />
      <div className="screen uir-proof-screen" hidden={settings}>
        {error && <p role="alert" className="notice error">{error}</p>}
        {view === "progress" && response && generation && <Progress generation={generation} sourceName={source?.originalName ?? (input.kind === "file" ? input.file.name : "Вставленный текст")} busy={busy}
          cancel={() => void action(async () => acknowledge(await projectRequest(`/${response.workspace.projectId}/cancel`, "POST", {})))} />}
        {view === "assessment" && response && <Assessment response={response} open={() => setReviewed(reviewId(response))} back={() => setSourceOpen(true)} />}
        {view === "editor" && response?.workspace.project && <>
          {status !== "Сохранено" && status !== "Изменения сохраняются…" && <button className="text-button" disabled={busy} onClick={() => void action(async () => { await editor.current?.flush(); setStatus("Сохранено"); })}>Повторить сохранение</button>}
          <RichEditor key={response.workspace.projectId} initial={response} acknowledge={acknowledge} onStatus={setStatus} ref={editor} appearance="prototype" portalHost={portalHost}
            contextActions={response.workspace.warnings.length > 0 && <button onClick={() => setWarningsOpen(true)}>Замечания к исходнику</button>} />
        </>}
        {view === "source" && <SourceForm input={input} change={setInput} textDraft={textDraft} busy={busy || creating} sourceName={source?.originalName ?? null}
          process={() => { setSourceOpen(false); void process(); }} warnings={response?.workspace.preDraft?.warnings.map(warningLabel) ?? []}
          failure={generation?.status === "failed" ? "Не удалось завершить обработку." : generation?.status === "cancelled" ? "Обработка отменена." : generation?.status === "interrupted" ? "Обработка прервана." : null} />}
      </div>
      {settings && <div className="screen uir-pending-settings"><SettingsPanel close={() => setSettings(false)} analysisChanged={() => {}} assistant={models => <AssistantSettings models={models} />} /></div>}
      <Dialog open={warningsOpen} close={() => setWarningsOpen(false)} title="Замечания к исходнику">
        {response?.workspace.warnings.map(warning => <p className="dialog-copy" key={warning.id}>{warningLabel(warning.code)}</p>)}
      </Dialog>
    </section>
  </main>;
}
