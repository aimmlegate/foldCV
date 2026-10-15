import { useState } from "react";
import { SettingsPanel } from "../next/SettingsPanel";
import { RichEditor } from "./Editor";
import { AssistantDrawer } from "../assistant/Drawer";
import { AssistantSettings } from "../assistant/Settings";
import { Projects } from "./Projects";
import { NewResume } from "./NewResume";
import { projectRequest } from "./api";
import { useResumeWorkspace, stageLabels, warningLabel } from "../workbench/useResumeWorkspace";
import "../next/next.css";
import "./reference-fonts.css";
import "./editor.css";
import "./shell.css";

export function App() {
  const { response, projects, input, setInput, error, status, setStatus, busy, settings, setSettings,
    editor, assistant, acknowledge, action, fresh, open, remove, process, upload, exportFile } = useResumeWorkspace();
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  const selectedSource = response?.workspace.preDraft?.sources.find(source => source.id === response.workspace.preDraft?.selectedSourceId);
  const title = response?.identity?.title ?? response?.workspace.title ?? "Новое резюме";
  const subtitle = response?.identity?.subtitle;
  return <main data-app="foldcv-rich">
    <div className="rich-shell" hidden={settings} data-history-collapsed={historyCollapsed}>
      <div className="rich-main">
        <header className="next-header">
          <button className="next-brand" disabled={busy || creating} onClick={() => void fresh()}>FoldCV</button>
          <div className="rich-resume-heading"><span>{title}</span>{subtitle && <small>{subtitle}</small>}</div>
          {response?.workspace.project && <span className="next-save" role="status">{status}</span>}
          {response?.workspace.project && <div className="next-actions">
            <button disabled={busy} onClick={() => editor.current?.undo()}>Отменить</button>
            <button disabled={busy} onClick={() => editor.current?.redo()}>Повторить</button>
            <button disabled={busy} onClick={() => void exportFile("archive")}>Сохранить файл проекта</button>
            <button disabled={busy} onClick={() => void exportFile("export")}>Скачать DOCX</button>
            {status !== "Сохранено" && status !== "Изменения сохраняются…" && <button disabled={busy} onClick={() => void action(async () => {
              await editor.current?.flush(); setStatus("Сохранено");
            })}>Повторить сохранение</button>}
          </div>}
        </header>
        {error && <p className="next-message" role="alert">{error}</p>}
        {creating && response && <div className="next-progress" role="status"><span>{stageLabels[generation.stage]}…</span>
          <button disabled={busy} onClick={() => void action(async () => { acknowledge(await projectRequest(`/${response.workspace.projectId}/cancel`, "POST", {})); })}>Остановить</button></div>}
        {generation?.status === "failed" && <p className="next-warning" role="alert">Обработка не завершилась: {generation.errorCode}. Исходник сохранён.</p>}
        {response?.workspace.project ? <>
          {response.workspace.warnings.map(warning => <p className="next-warning" key={warning.id}>{warningLabel(warning.code)}</p>)}
          <div className="rich-editor-scroll"><RichEditor key={response.workspace.projectId} initial={response} acknowledge={acknowledge} onStatus={setStatus} ref={editor}
            onHistoryNavigation={() => assistant.current?.history()} onAssistantFence={saved => assistant.current?.fence(saved)} /></div>
          <AssistantDrawer key={response.workspace.projectId} projectId={response.workspace.projectId} editor={editor} settingsOpen={settings} ref={assistant}
            settings={() => void action(async () => { await editor.current?.flush(); setSettings(true); })} />
        </> : <>
          <NewResume input={input} change={setInput} busy={busy || creating} sourceName={selectedSource?.originalName ?? null} process={() => void process()} />
          {response?.workspace.preDraft?.warnings.map((warning, index) => <p className="next-warning" role="alert" key={`${warning}:${index}`}>{warning}</p>)}
        </>}
      </div>
      <aside className="rich-resume-sidebar" aria-label="История резюме" data-collapsed={historyCollapsed}>
        <button className="rich-history-toggle" aria-expanded={!historyCollapsed} aria-controls="rich-resume-navigation"
          aria-label={historyCollapsed ? "Развернуть историю резюме" : "Свернуть историю резюме"} onClick={() => setHistoryCollapsed(value => !value)}>{historyCollapsed ? "›" : "‹"}</button>
        <div className="rich-sidebar-content" id="rich-resume-navigation" hidden={historyCollapsed}>
        <button className="next-create" disabled={busy || creating} onClick={() => void fresh()}>Новое резюме</button>
        <div className="rich-resume-list"><Projects list={projects} busy={busy || creating} activeId={response?.workspace.projectId ?? null}
          open={open} remove={remove} /></div>
        <div className="rich-sidebar-tools">
          <label>Открыть проект<input aria-label="Открыть файл проекта" type="file" accept=".foldcv,.zip" disabled={busy || creating}
            onChange={event => { const file = event.currentTarget.files?.[0]; if (file) void upload(file); event.currentTarget.value = ""; }} /></label>
          <button disabled={busy} onClick={() => void action(async () => {
            if (editor.current) await editor.current.flush();
            setSettings(true);
          })}>Настройки</button>
        </div></div>
      </aside>
    </div>
    {settings && <SettingsPanel close={() => setSettings(false)} analysisChanged={() => {}} assistant={models => <AssistantSettings models={models} />} />}
  </main>;
}
