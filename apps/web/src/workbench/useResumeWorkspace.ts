import { errorMessage } from "../errors/messages";
import { useCallback, useEffect, useRef, useState } from "react";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import type { RichEditorHandle } from "../rich/Editor";
import type { AssistantHandle } from "../assistant/Drawer";
import { hasInput, importBody, type ResumeInput } from "../rich/import-source";
import { deleteProject, download, listProjects, projectRequest, request, RichApiFailure } from "../rich/api";
import { attachExclusiveWriter, type AttachedWriter } from "../background/connection";
import { FixedOperations } from "../background/fixed";
import { JobsApi } from "../background/api";
import { warningLabel } from "./import/notices";
export { warningLabel } from "./import/notices";

function label(error: unknown): string { return errorMessage(error); }
export const stageLabels = { assess_resume: "Проверяем, похоже ли содержимое на резюме", normalize_semantics: "Извлекаем факты", draft_prose: "Редактируем текст",
  assemble: "Применяем структуру шаблона", render: "Готовим DOCX" };
export function useResumeWorkspace() {
  const [response, setResponse] = useState<RichProjectResponse | null>(null);
  const [writer, setWriter] = useState<AttachedWriter | null>(null);
  const [background, setBackground] = useState(false);
  const [projects, setProjects] = useState<GuiProjectListResponse | null>(null);
  const [input, storeInput] = useState<ResumeInput>({ kind: "text", text: "" });
  const [textDraft, setTextDraft] = useState("");
  const [allowTextRewrite, setAllowTextRewrite] = useState(true);
  function setInput(next: ResumeInput) { storeInput(next); if (next.kind === "text") setTextDraft(next.text); }
  const [error, setError] = useState("");
  const dismissError = useCallback(() => setError(""), []);
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState<{ label: string; startedAt: number } | null>(null);
  function stage(label: string) { setOperation(current => current ? { ...current, label } : { label, startedAt: Date.now() }); }
  const [loading, setLoading] = useState(() => new URLSearchParams(location.search).has("project"));
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
  function select(next: RichProjectResponse, available = false) {
    if (activeProject.current !== next.workspace.projectId) {
      const draft = next.workspace.preDraft?.importDraft;
      setAllowTextRewrite(draft ? draft.allowTextRewrite ?? false : true);
    }
    setBackground(available); activeProject.current = next.workspace.projectId; acknowledge(next);
  }
  async function load(id: string) {
    const next = await projectRequest(`/${id}`);
    const connection = next.workspace.project ? await attachExclusiveWriter(id) : null;
    let available = connection !== null;
    if (!next.workspace.project) {
      try { await new JobsApi(id).projectJobs(); available = true; }
      catch (error) { if (!(error instanceof RichApiFailure) || error.code !== "JOB_DISABLED") throw error; }
    }
    await projectRequest(`/${id}/activate`, "POST", {});
    setProjects(await listProjects());
    return { next: connection?.view.response ?? next, connection, available };
  }
  async function leave() {
    if (!editor.current?.background) await assistant.current?.stop();
    if (editor.current) await editor.current.navigate();
  }
  async function action(work: () => Promise<void>, labelText = "Сохраняем последние изменения"): Promise<boolean> {
    if (acting.current) return false;
    const previousEditor = editor.current, previousProject = activeProject.current;
    acting.current = true; setBusy(true); setOperation({ label: labelText, startedAt: Date.now() }); setError("");
    try { await work(); return true; } catch (error) {
      let message = label(error);
      if (!settings && previousEditor?.background && editor.current === previousEditor && activeProject.current === previousProject) {
        try { await previousEditor.resume(); } catch (resumeError) { message += ` ${label(resumeError)}`; }
      }
      setError(message); return false;
    }
    finally { acting.current = false; setBusy(false); setOperation(null); }
  }
  function clear() {
    ++epoch.current; activeProject.current = null; setResponse(null); setWriter(null); setBackground(false); setStatus("Сохранено"); prepared.current = null;
    setAllowTextRewrite(true);
    setInput({ kind: "text", text: "" }); history.replaceState(null, "", location.pathname);
  }
  async function fresh() {
    await action(async () => {
      await leave();
      clear(); setSettings(false);
    }, "Подготавливаем новое резюме");
  }
  async function open(id: string) {
    return action(async () => {
      if (response?.workspace.projectId === id) { await editor.current?.resume(); setSettings(false); return; }
      await leave();
      const ticket = ++epoch.current, { next, connection, available } = await load(id);
      if (ticket === epoch.current) {
        setWriter(connection); select(next, available); setStatus("Сохранено"); prepared.current = null;
        setInput({ kind: "text", text: "" }); setSettings(false);
      }
    }, "Открываем резюме");
  }
  async function remove(id: string) {
    return action(async () => {
      if (activeProject.current === id) await leave();
      const result = await deleteProject(id);
      if (response?.workspace.projectId === id) clear();
      setProjects(await listProjects());
      if (result.status === "cleanup_incomplete") throw new RichApiFailure(result.errorCode ?? "PROJECT_CLEANUP_INCOMPLETE");
    }, "Удаляем резюме");
  }
  async function archive(id: string, archived: boolean) {
    return action(async () => {
      if (archived && activeProject.current === id) await leave();
      await request(`/${id}/catalog/${archived ? "archive" : "restore"}`, "POST", {});
      if (archived && activeProject.current === id) clear();
      setProjects(await listProjects());
    }, archived ? "Перемещаем резюме в архив" : "Восстанавливаем резюме");
  }
  async function projectLifecycle(id: string, kind: "archive" | "delete") {
    return action(async () => {
      if (activeProject.current !== id) return;
      if (kind === "archive") await leave();
      clear(); setProjects(await listProjects());
    });
  }
  useEffect(() => {
    const ticket = ++epoch.current;
    const id = new URLSearchParams(location.search).get("project");
    if (id) void load(id).then(({ next, connection, available }) => { if (ticket === epoch.current) { setWriter(connection); select(next, available); } }).catch(error => { if (ticket === epoch.current) setError(label(error)); }).finally(() => { if (ticket === epoch.current) setLoading(false); });
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
          select(selected); setAllowTextRewrite(allowTextRewrite); id = selected.workspace.projectId;
          prepared.current = { input, projectId: id };
          setProjects(await listProjects());
        }
      }
      if (id) {
        stage("Запускаем обработку резюме");
        try { await new FixedOperations(id).submit({ kind: "processing", allowTextRewrite }); select(await projectRequest(`/${id}`), true); }
        catch (error) {
          if (error instanceof RichApiFailure && error.code === "JOB_DISABLED") select(await projectRequest(`/${id}/generation`, "POST", { allowTextRewrite }));
          else throw error;
        }
      }
    }, input.kind === "file" ? "Загружаем и читаем файл" : "Читаем исходный текст");
  }
  async function upload(file: File) {
    return action(async () => {
      await leave();
      const body = new FormData(); body.append("file", file);
      ++epoch.current;
      const imported = await projectRequest("/archive", "POST", body);
      const connection = imported.workspace.project ? await attachExclusiveWriter(imported.workspace.projectId) : null;
      setWriter(connection); select(connection?.view.response ?? imported, connection !== null);
      prepared.current = null; setInput({ kind: "text", text: "" }); setSettings(false); setProjects(await listProjects());
    }, "Открываем файл проекта");
  }
  async function exportFile(kind: "export" | "archive", filename?: string | ((current: RichProjectResponse) => string)) {
    return action(async () => {
      const current = editor.current ? await editor.current.flush() : response;
      if (!current) throw new Error("Откройте резюме перед сохранением файла.");
      stage(kind === "export" ? "Создаём документ DOCX" : "Собираем файл проекта");
      const blob = await download(current.workspace.projectId, kind, current.workspace);
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = typeof filename === "function" ? filename(current) : filename ?? (kind === "export" ? "resume.docx" : "project.foldcv");
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "Сохраняем изменения перед скачиванием");
  }
  return { response, writer, background, projects, input, setInput, textDraft, allowTextRewrite, setAllowTextRewrite, error, status, setStatus, busy, operation, loading, settings, setSettings,
    editor, assistant, acknowledge, action, fresh, open, remove, archive, projectLifecycle, process, upload, exportFile, dismissError };
}
