import { useCallback, useEffect, useRef, useState } from "react";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import { SettingsPanel } from "../next/SettingsPanel";
import { useTheme } from "../next/theme";
import { RichEditor, type RichEditorHandle } from "./Editor";
import { Projects } from "./Projects";
import { NewResume } from "./NewResume";
import { hasInput, importBody, type ResumeInput } from "./import-source";
import { deleteProject, download, listProjects, projectRequest, RichApiFailure } from "./api";
import "../next/next.css";
import "./reference-fonts.css";
import "./editor.css";
import "./shell.css";

function label(error: unknown): string {
  if (error instanceof RichApiFailure && error.code === "PROJECT_VERSION_UNSUPPORTED") return "Версия проекта не поддерживается. Исходные файлы сохранены.";
  if (error instanceof RichApiFailure && error.code === "ARCHIVE_VERSION_UNSUPPORTED") return "Версия файла проекта не поддерживается.";
  if (error instanceof RichApiFailure && error.code === "RICH_EXPORT_UNSUPPORTED") return "Этот блок пока не поддерживает экспорт. Изменения сохранены.";
  if (error instanceof RichApiFailure && error.code === "CONNECTION_REQUIRED") return "Настройте подключение модели и повторите обработку. Источник сохранён.";
  return error instanceof Error ? error.message : "Не удалось выполнить действие";
}
const stageLabels = { assess_resume: "Проверяем, похоже ли содержимое на резюме", normalize_semantics: "Извлекаем факты", draft_prose: "Редактируем текст",
  assemble: "Открываем исходный текст", render: "Готовим DOCX" };
function warningLabel(code: string): string {
  if (code === "source_not_resume") return "Модель считает, что исходный текст не похож на резюме. Проверьте выбранный источник. Импорт продолжен.";
  if (code === "source_resume_uncertain") return "Модель не смогла уверенно определить, похоже ли содержимое на резюме. Импорт продолжен.";
  return `Проверьте содержание: ${code}`;
}
export function App() {
  const theme = useTheme();
  const [response, setResponse] = useState<RichProjectResponse | null>(null);
  const [projects, setProjects] = useState<GuiProjectListResponse | null>(null);
  const [input, setInput] = useState<ResumeInput>({ kind: "text", text: "" });
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const editor = useRef<RichEditorHandle>(null);
  const epoch = useRef(0), acting = useRef(false);
  const prepared = useRef<{ input: ResumeInput; projectId: string } | null>(null);
  const acknowledge = useCallback((next: RichProjectResponse) => {
    setResponse(next);
    if (next.identity) setProjects(current => current ? { ...current, entries: current.entries.map(entry => entry.projectId === next.workspace.projectId
      ? { ...entry, title: next.identity?.title ?? entry.title, subtitle: next.identity?.subtitle ?? "" } : entry) } : current);
    const url = new URL(location.href); url.searchParams.set("project", next.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }, []);
  async function action(work: () => Promise<void>): Promise<boolean> {
    if (acting.current) return false;
    acting.current = true; setBusy(true); setError("");
    try { await work(); return true; } catch (error) { setError(label(error)); return false; }
    finally { acting.current = false; setBusy(false); }
  }
  function clear() {
    ++epoch.current; setResponse(null); setStatus("Сохранено"); prepared.current = null;
    setInput({ kind: "text", text: "" }); history.replaceState(null, "", location.pathname);
  }
  async function fresh() {
    await action(async () => {
      if (editor.current) await editor.current.flush();
      clear(); setSettings(false);
    });
  }
  async function open(id: string) {
    return action(async () => {
      if (response?.workspace.projectId === id) return;
      if (editor.current) await editor.current.flush();
      const ticket = ++epoch.current, next = await projectRequest(`/${id}`);
      if (ticket === epoch.current) {
        acknowledge(next); setStatus("Сохранено"); prepared.current = null;
        setInput({ kind: "text", text: "" });
      }
    });
  }
  async function remove(id: string) {
    return action(async () => {
      if (editor.current) await editor.current.flush();
      const result = await deleteProject(id);
      if (response?.workspace.projectId === id) clear();
      setProjects(await listProjects());
      if (result.status === "cleanup_incomplete") throw new RichApiFailure(result.errorCode ?? "PROJECT_CLEANUP_INCOMPLETE");
    });
  }
  useEffect(() => {
    const ticket = ++epoch.current;
    const id = new URLSearchParams(location.search).get("project");
    if (id) void projectRequest(`/${id}`).then(value => { if (ticket === epoch.current) acknowledge(value); }).catch(error => { if (ticket === epoch.current) setError(label(error)); });
    void listProjects().then(setProjects).catch(error => setError(label(error)));
    return () => { ++epoch.current; };
  }, [acknowledge]);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  useEffect(() => {
    if (!response || !generation || !["queued", "running"].includes(generation.status)) return;
    let alive = true, polling = false;
    const ticket = epoch.current;
    const timer = setInterval(() => {
      if (polling) return;
      polling = true;
      void projectRequest(`/${response.workspace.projectId}`).then(async next => {
        if (!alive || ticket !== epoch.current) return;
        acknowledge(next);
        if (next.generation?.status === "completed") setProjects(await listProjects());
      }).catch(error => { if (alive && ticket === epoch.current) setError(label(error)); }).finally(() => { polling = false; });
    }, 700);
    return () => { alive = false; clearInterval(timer); };
  }, [response?.workspace.projectId, generation?.status, acknowledge]);
  async function process() {
    await action(async () => {
      let id = response?.workspace.preDraft?.selectedSourceId ? response.workspace.projectId : null;
      if (hasInput(input)) {
        if (prepared.current?.input === input) id = prepared.current.projectId;
        else {
          const selected = await projectRequest("/input", "POST", importBody(input));
          acknowledge(selected); id = selected.workspace.projectId;
          prepared.current = { input, projectId: id };
          setProjects(await listProjects());
        }
      }
      if (id) acknowledge(await projectRequest(`/${id}/generation`, "POST", {}));
    });
  }
  async function upload(file: File) {
    await action(async () => {
      if (editor.current) await editor.current.flush();
      const body = new FormData(); body.append("file", file);
      ++epoch.current; acknowledge(await projectRequest("/archive", "POST", body));
      prepared.current = null; setInput({ kind: "text", text: "" }); setProjects(await listProjects());
    });
  }
  async function exportFile(kind: "export" | "archive") {
    await action(async () => {
      const current = editor.current ? await editor.current.flush() : response;
      if (!current) return;
      const blob = await download(current.workspace.projectId, kind, current.workspace);
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = kind === "export" ? "resume.docx" : "project.foldcv";
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
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
          <RichEditor key={response.workspace.projectId} initial={response} acknowledge={acknowledge} onStatus={setStatus} ref={editor} />
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
    {settings && <SettingsPanel close={() => setSettings(false)} analysisChanged={() => {}} appearance={<label>Тема<select aria-label="Тема" value={theme.mode}
      onChange={event => theme.select(event.target.value)}><option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option></select></label>} />}
  </main>;
}
