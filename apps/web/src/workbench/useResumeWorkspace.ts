import { useCallback, useEffect, useRef, useState } from "react";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import type { RichEditorHandle } from "../rich/Editor";
import type { AssistantHandle } from "../assistant/Drawer";
import { hasInput, importBody, type ResumeInput } from "../rich/import-source";
import { deleteProject, download, listProjects, projectRequest, RichApiFailure } from "../rich/api";
import { attachExclusiveWriter, type AttachedWriter } from "../background/connection";

function label(error: unknown): string {
  if (error instanceof RichApiFailure && error.code === "PROJECT_VERSION_UNSUPPORTED") return "Версия проекта не поддерживается. Исходные файлы сохранены.";
  if (error instanceof RichApiFailure && error.code === "ARCHIVE_VERSION_UNSUPPORTED") return "Версия файла проекта не поддерживается.";
  if (error instanceof RichApiFailure && error.code === "RICH_EXPORT_UNSUPPORTED") return "Этот блок пока не поддерживает экспорт. Изменения сохранены.";
  if (error instanceof RichApiFailure && error.code === "CONNECTION_REQUIRED") return "Настройте подключение модели и повторите обработку. Источник сохранён.";
  if (error instanceof RichApiFailure) return "Не удалось выполнить действие. Повторите попытку.";
  if (error instanceof TypeError) return "Нет связи с локальным сервисом. Проверьте его запуск и повторите попытку.";
  return error instanceof Error ? error.message : "Не удалось выполнить действие";
}
export const stageLabels = { assess_resume: "Проверяем, похоже ли содержимое на резюме", normalize_semantics: "Извлекаем факты", draft_prose: "Редактируем текст",
  assemble: "Открываем исходный текст", render: "Готовим DOCX" };
export function warningLabel(code: string): string {
  if (code === "source_not_resume") return "Модель считает, что исходный текст не похож на резюме. Проверьте выбранный источник. Импорт продолжен.";
  if (code === "source_resume_uncertain") return "Модель не смогла уверенно определить, похоже ли содержимое на резюме. Импорт продолжен.";
  if (code === "source_details_unresolved") return "Часть сведений требует проверки. Сверьте факты с исходником.";
  return "Исходник сохранён. Часть сведений требует проверки.";
}
export function useResumeWorkspace() {
  const [response, setResponse] = useState<RichProjectResponse | null>(null);
  const [writer, setWriter] = useState<AttachedWriter | null>(null);
  const [projects, setProjects] = useState<GuiProjectListResponse | null>(null);
  const [input, storeInput] = useState<ResumeInput>({ kind: "text", text: "" });
  const [textDraft, setTextDraft] = useState("");
  function setInput(next: ResumeInput) { storeInput(next); if (next.kind === "text") setTextDraft(next.text); }
  const [error, setError] = useState("");
  const dismissError = useCallback(() => setError(""), []);
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(false);
  const editor = useRef<RichEditorHandle>(null);
  const assistant = useRef<AssistantHandle>(null);
  const epoch = useRef(0), acting = useRef(false), activeProject = useRef<string | null>(null);
  const prepared = useRef<{ input: ResumeInput; projectId: string } | null>(null);
  const acknowledge = useCallback((next: RichProjectResponse) => {
    if (next.workspace.projectId !== activeProject.current) return;
    setResponse(next);
    if (next.identity) setProjects(current => current ? { ...current, entries: current.entries.map(entry => entry.projectId === next.workspace.projectId
      ? { ...entry, title: next.identity?.title ?? entry.title, subtitle: next.identity?.subtitle ?? "" } : entry) } : current);
    const url = new URL(location.href); url.searchParams.set("project", next.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }, []);
  function select(next: RichProjectResponse) { activeProject.current = next.workspace.projectId; acknowledge(next); }
  async function load(id: string) {
    const next = await projectRequest(`/${id}`);
    const connection = next.workspace.project ? await attachExclusiveWriter(id) : null;
    return { next: connection?.view.response ?? next, connection };
  }
  async function leave() {
    if (!editor.current?.background) await assistant.current?.stop();
    if (editor.current) await editor.current.navigate();
  }
  async function action(work: () => Promise<void>): Promise<boolean> {
    if (acting.current) return false;
    const previousEditor = editor.current, previousProject = activeProject.current;
    acting.current = true; setBusy(true); setError("");
    try { await work(); return true; } catch (error) {
      let message = label(error);
      if (!settings && previousEditor?.background && editor.current === previousEditor && activeProject.current === previousProject) {
        try { await previousEditor.resume(); } catch (resumeError) { message += ` ${label(resumeError)}`; }
      }
      setError(message); return false;
    }
    finally { acting.current = false; setBusy(false); }
  }
  function clear() {
    ++epoch.current; activeProject.current = null; setResponse(null); setWriter(null); setStatus("Сохранено"); prepared.current = null;
    setInput({ kind: "text", text: "" }); history.replaceState(null, "", location.pathname);
  }
  async function fresh() {
    await action(async () => {
      await leave();
      clear(); setSettings(false);
    });
  }
  async function open(id: string) {
    return action(async () => {
      if (response?.workspace.projectId === id) { await editor.current?.resume(); setSettings(false); return; }
      await leave();
      const ticket = ++epoch.current, { next, connection } = await load(id);
      if (ticket === epoch.current) {
        setWriter(connection); select(next); setStatus("Сохранено"); prepared.current = null;
        setInput({ kind: "text", text: "" }); setSettings(false);
      }
    });
  }
  async function remove(id: string) {
    return action(async () => {
      if (activeProject.current === id) await leave();
      const result = await deleteProject(id);
      if (response?.workspace.projectId === id) clear();
      setProjects(await listProjects());
      if (result.status === "cleanup_incomplete") throw new RichApiFailure(result.errorCode ?? "PROJECT_CLEANUP_INCOMPLETE");
    });
  }
  useEffect(() => {
    const ticket = ++epoch.current;
    const id = new URLSearchParams(location.search).get("project");
    if (id) void load(id).then(({ next, connection }) => { if (ticket === epoch.current) { setWriter(connection); select(next); } }).catch(error => { if (ticket === epoch.current) setError(label(error)); });
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
        if (next.generation?.status === "completed" && next.workspace.project) {
          const connection = await attachExclusiveWriter(next.workspace.projectId);
          if (!alive || ticket !== epoch.current) return;
          setWriter(connection); acknowledge(connection?.view.response ?? next);
        } else acknowledge(next);
        if (next.generation?.status === "completed") setProjects(await listProjects());
      }).catch(error => { if (alive && ticket === epoch.current) setError(label(error)); }).finally(() => { polling = false; });
    }, 700);
    return () => { alive = false; clearInterval(timer); };
  }, [response?.workspace.projectId, generation?.status, acknowledge]);
  async function process() {
    await action(async () => {
      let id = response?.workspace.preDraft?.selectedSourceId ? response.workspace.projectId : null;
      if (hasInput(input)) {
        if (prepared.current?.input === input && !response?.workspace.project) id = prepared.current.projectId;
        else {
          const selected = await projectRequest("/input", "POST", importBody(input));
          select(selected); id = selected.workspace.projectId;
          prepared.current = { input, projectId: id };
          setProjects(await listProjects());
        }
      }
      if (id) select(await projectRequest(`/${id}/generation`, "POST", {}));
    });
  }
  async function upload(file: File) {
    return action(async () => {
      await leave();
      const body = new FormData(); body.append("file", file);
      ++epoch.current;
      const imported = await projectRequest("/archive", "POST", body);
      const connection = imported.workspace.project ? await attachExclusiveWriter(imported.workspace.projectId) : null;
      setWriter(connection); select(connection?.view.response ?? imported);
      prepared.current = null; setInput({ kind: "text", text: "" }); setSettings(false); setProjects(await listProjects());
    });
  }
  async function exportFile(kind: "export" | "archive", filename?: string | ((current: RichProjectResponse) => string)) {
    return action(async () => {
      const current = editor.current ? await editor.current.flush() : response;
      if (!current) throw new Error("Откройте резюме перед сохранением файла.");
      const blob = await download(current.workspace.projectId, kind, current.workspace);
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = typeof filename === "function" ? filename(current) : filename ?? (kind === "export" ? "resume.docx" : "project.foldcv");
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  return { response, writer, projects, input, setInput, textDraft, error, status, setStatus, busy, settings, setSettings,
    editor, assistant, acknowledge, action, fresh, open, remove, process, upload, exportFile, dismissError };
}
