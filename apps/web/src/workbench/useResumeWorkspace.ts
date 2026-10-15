import { useCallback, useEffect, useRef, useState } from "react";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import type { RichEditorHandle } from "../rich/Editor";
import type { AssistantHandle } from "../assistant/Drawer";
import { hasInput, importBody, type ResumeInput } from "../rich/import-source";
import { deleteProject, download, listProjects, projectRequest, RichApiFailure } from "../rich/api";

function label(error: unknown): string {
  if (error instanceof RichApiFailure && error.code === "PROJECT_VERSION_UNSUPPORTED") return "Версия проекта не поддерживается. Исходные файлы сохранены.";
  if (error instanceof RichApiFailure && error.code === "ARCHIVE_VERSION_UNSUPPORTED") return "Версия файла проекта не поддерживается.";
  if (error instanceof RichApiFailure && error.code === "RICH_EXPORT_UNSUPPORTED") return "Этот блок пока не поддерживает экспорт. Изменения сохранены.";
  if (error instanceof RichApiFailure && error.code === "CONNECTION_REQUIRED") return "Настройте подключение модели и повторите обработку. Источник сохранён.";
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
  const [projects, setProjects] = useState<GuiProjectListResponse | null>(null);
  const [input, storeInput] = useState<ResumeInput>({ kind: "text", text: "" });
  const [textDraft, setTextDraft] = useState("");
  function setInput(next: ResumeInput) { storeInput(next); if (next.kind === "text") setTextDraft(next.text); }
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(false);
  const editor = useRef<RichEditorHandle>(null);
  const assistant = useRef<AssistantHandle>(null);
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
      await assistant.current?.stop();
      if (editor.current) await editor.current.flush();
      clear(); setSettings(false);
    });
  }
  async function open(id: string) {
    return action(async () => {
      if (response?.workspace.projectId === id) return;
      await assistant.current?.stop();
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
      await assistant.current?.stop();
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
        if (prepared.current?.input === input && !response?.workspace.project) id = prepared.current.projectId;
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
      await assistant.current?.stop();
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
  return { response, projects, input, setInput, textDraft, error, status, setStatus, busy, settings, setSettings,
    editor, assistant, acknowledge, action, fresh, open, remove, process, upload, exportFile };
}
