import * as Popover from "@radix-ui/react-popover";
import { useCallback, useEffect, useRef, useState } from "react";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import { SettingsPanel } from "../next/SettingsPanel";
import { useTheme } from "../next/theme";
import { RichEditor, type RichEditorHandle } from "./Editor";
import { download, listProjects, projectRequest, RichApiFailure } from "./api";
import sample from "../../../../tests/fixtures/recovery/E1.txt?raw";
import "../next/next.css";
import "./reference-fonts.css";
import "./editor.css";

function label(error: unknown): string {
  if (error instanceof RichApiFailure && error.code === "PROJECT_VERSION_UNSUPPORTED") return "Версия проекта не поддерживается. Исходные файлы сохранены.";
  if (error instanceof RichApiFailure && error.code === "ARCHIVE_VERSION_UNSUPPORTED") return "Версия файла проекта не поддерживается.";
  if (error instanceof RichApiFailure && error.code === "RICH_EXPORT_UNSUPPORTED") return "Этот блок пока не поддерживает экспорт. Изменения сохранены.";
  return error instanceof Error ? error.message : "Не удалось выполнить действие";
}
const stageLabels = { normalize_semantics: "Готовим факты", draft_prose: "Редактируем текст",
  assemble: "Собираем документ", render: "Готовим DOCX" };
export function App() {
  const theme = useTheme();
  const [response, setResponse] = useState<RichProjectResponse | null>(null);
  const [projects, setProjects] = useState<GuiProjectListResponse | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(false);
  const editor = useRef<RichEditorHandle>(null);
  const epoch = useRef(0);
  const acknowledge = useCallback((next: RichProjectResponse) => {
    setResponse(next);
    const url = new URL(location.href); url.searchParams.set("project", next.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }, []);
  async function action(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); } catch (error) { setError(label(error)); } finally { setBusy(false); }
  }
  async function open(id: string) {
    await action(async () => {
      if (editor.current) await editor.current.flush();
      const ticket = ++epoch.current, next = await projectRequest(`/${id}`);
      if (ticket === epoch.current) acknowledge(next);
    });
  }
  useEffect(() => {
    const ticket = ++epoch.current;
    const id = new URLSearchParams(location.search).get("project");
    if (id) void projectRequest(`/${id}`).then(value => { if (ticket === epoch.current) acknowledge(value); }).catch(error => setError(label(error)));
    void listProjects().then(setProjects).catch(error => setError(label(error)));
    return () => { ++epoch.current; };
  }, [acknowledge]);
  const generation = response?.generation;
  useEffect(() => {
    if (!response || !generation || !["queued", "running"].includes(generation.status)) return;
    let alive = true;
    const timer = setInterval(() => { void projectRequest(`/${response.workspace.projectId}`).then(next => {
      if (alive) acknowledge(next);
    }).catch(error => { if (alive) setError(label(error)); }); }, 700);
    return () => { alive = false; clearInterval(timer); };
  }, [response?.workspace.projectId, generation?.status, acknowledge]);
  async function upload(file: File, portable: boolean) {
    await action(async () => {
      if (editor.current) await editor.current.flush();
      const body = new FormData(); body.append("file", file);
      acknowledge(await projectRequest(portable ? "/archive" : "/input", "POST", body));
      setProjects(await listProjects());
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
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  return <Popover.Root open={settings} onOpenChange={setSettings} modal><main data-app="foldcv-rich">
    <header className="next-header">
      <button className="next-brand" disabled={busy || creating} onClick={() => void action(async () => {
        if (editor.current) await editor.current.flush();
        ++epoch.current; setResponse(null); history.replaceState(null, "", location.pathname); setProjects(await listProjects());
      })}>FoldCV</button>
      <span>{response?.workspace.title ?? "Новое резюме"}</span>
      {response?.workspace.project && <span className="next-save" role="status">{status}</span>}
      <div className="next-actions">
        {response?.workspace.project && <><button disabled={busy} onClick={() => editor.current?.undo()}>Отменить</button>
          <button disabled={busy} onClick={() => editor.current?.redo()}>Повторить</button>
          <button disabled={busy} onClick={() => void exportFile("archive")}>Сохранить файл проекта</button>
          <button disabled={busy} onClick={() => void exportFile("export")}>Скачать DOCX</button></>}
        {response?.workspace.project && status !== "Сохранено" && status !== "Изменения сохраняются…" && <button disabled={busy} onClick={() => void action(async () => {
          await editor.current?.flush(); setStatus("Сохранено");
        })}>Повторить сохранение</button>}
        <label>Открыть проект<input aria-label="Открыть файл проекта" type="file" accept=".foldcv,.zip" disabled={busy || creating}
          onChange={event => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, true); event.currentTarget.value = ""; }} /></label>
        <Popover.Trigger asChild><button>Настройки</button></Popover.Trigger>
      </div>
    </header>
    {error && <p className="next-message" role="alert">{error}</p>}
    {creating && response && <div className="next-progress" role="status"><span>{stageLabels[generation.stage]}…</span>
      <button onClick={() => void action(async () => { acknowledge(await projectRequest(`/${response.workspace.projectId}/cancel`, "POST", {})); })}>Остановить</button></div>}
    {response?.workspace.project ? <>
      {generation?.status === "failed" && <p className="next-warning" role="alert">Резюме импортировано. Операция не завершилась: {generation.errorCode}</p>}
      {response.workspace.warnings.map(warning => <p className="next-warning" key={warning.id}>Проверьте содержание: {warning.code}</p>)}
      <RichEditor key={response.workspace.projectId} initial={response} acknowledge={acknowledge} onStatus={setStatus} ref={editor} />
    </> : <div className="next-start">
      <section className="next-intro"><span className="next-eyebrow">FOLDCV</span><h1>Резюме, с которым удобно работать</h1>
        <p>Добавьте файл или вставьте текст. После создания резюме можно редактировать и сохранить в Word.</p>
        <section aria-label="Сохранённые проекты"><h2>Сохранённые проекты</h2>
          {projects?.entries.map(entry => <div key={entry.projectId}><button disabled={busy || creating} onClick={() => void open(entry.projectId)}>{entry.title}</button>
            {projects.errors.some(error => error.projectId === entry.projectId && error.errorCode === "PROJECT_VERSION_UNSUPPORTED") && <span> Другая версия</span>}</div>)}</section>
      </section>
      <section className="next-input">
        <div className="next-upload"><h2>Добавьте исходное резюме</h2><input type="file" aria-label="Исходное резюме" accept=".pdf,.docx,.txt" disabled={busy || creating}
          onChange={event => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, false); event.currentTarget.value = ""; }} /></div>
        <button disabled={busy || creating} onClick={() => setText(sample)}>Вставить пример</button>
        <label className="next-paste-label">Или вставьте текст<textarea aria-label="Текст резюме" value={text} disabled={busy || creating} onChange={event => setText(event.target.value)} rows={12} /></label>
        <button className="next-create" disabled={busy || creating || (!text.trim() && !response?.workspace.preDraft?.selectedSourceId)} onClick={() => void action(async () => {
          acknowledge(response?.workspace.preDraft?.selectedSourceId ? await projectRequest(`/${response.workspace.projectId}/generation`, "POST", {})
            : await projectRequest("", "POST", { text })); setProjects(await listProjects());
        })}>Создать резюме</button>
        {generation?.status === "failed" && <p role="alert">{generation.errorCode}</p>}
        {response?.workspace.preDraft?.warnings.map((warning, index) => <p role="alert" key={`${warning}:${index}`}>{warning}</p>)}
      </section>
    </div>}
    <Popover.Portal>
      <Popover.Content className="rich-settings" aria-label="Настройки">
        <SettingsPanel close={() => setSettings(false)} analysisChanged={() => {}} /><label>Тема<select value={theme.mode} onChange={event => theme.select(event.target.value)}><option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option></select></label>
        <Popover.Close>Закрыть</Popover.Close></Popover.Content></Popover.Portal>
  </main></Popover.Root>;
}
