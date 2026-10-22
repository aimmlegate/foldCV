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
import { WorkspaceReads } from "./read-capture";
import type { ReadCapture } from "../contracts/template-export";
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
  const reads = useRef(new WorkspaceReads());
  const [opening, setOpening] = useState<ReadCapture | null>(null);
  const lifetime = useRef<object | null>(null), acting = useRef<object | null>(null);
  const activeProject = useRef<string | null>(null);
  const prepared = useRef<{ input: ResumeInput; projectId: string } | null>(null);
  const adopt = useCallback((next: RichProjectResponse, capture: ReadCapture | null) => {
    if (!reads.current.matchesOpening(capture) || next.workspace.projectId !== capture?.projectId
      || next.workspace.projectId !== activeProject.current) return;
    setResponse(next);
    if (next.identity) setProjects(current => current ? { ...current, entries: current.entries.map(entry => entry.projectId === next.workspace.projectId
      ? { ...entry, title: next.identity?.title ?? entry.title, subtitle: next.identity?.subtitle ?? "" } : entry) } : current);
    const url = new URL(location.href); url.searchParams.set("project", next.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }, []);
  const acknowledge = useCallback((next: RichProjectResponse) => adopt(next, opening), [adopt, opening]);
  function select(next: RichProjectResponse, available = false, loaded?: ReadCapture) {
    if (loaded && loaded.projectId !== next.workspace.projectId) throw new RichApiFailure("INVALID_RESULT");
    let capture = loaded ?? reads.current.opening;
    if (loaded || capture?.projectId !== next.workspace.projectId) {
      capture = loaded ?? reads.current.beginSelection(next.workspace.projectId);
      if (!reads.current.adoptSelection(capture)) return;
      setOpening(capture);
    }
    if (activeProject.current !== next.workspace.projectId) {
      const draft = next.workspace.preDraft?.importDraft;
      setAllowTextRewrite(draft ? draft.allowTextRewrite ?? false : true);
    }
    setBackground(available); activeProject.current = next.workspace.projectId; adopt(next, capture);
  }
  async function load(id: string, capture: ReadCapture) {
    const next = await projectRequest(`/${id}`);
    if (!reads.current.selectionCurrent(capture)) return null;
    if (next.workspace.projectId !== id) throw new RichApiFailure("INVALID_RESULT");
    const connection = next.workspace.project ? await attachExclusiveWriter(id) : null;
    if (!reads.current.selectionCurrent(capture)) return null;
    let available = connection !== null;
    if (!next.workspace.project) {
      try { await new JobsApi(id).projectJobs(); available = true; }
      catch (error) { if (!(error instanceof RichApiFailure) || error.code !== "JOB_DISABLED") throw error; }
    }
    if (!reads.current.selectionCurrent(capture)) return null;
    await projectRequest(`/${id}/activate`, "POST", {});
    if (!reads.current.selectionCurrent(capture)) return null;
    const catalog = await listProjects();
    return { next: connection?.view.response ?? next, connection, available, catalog };
  }
  async function leave(current: () => boolean) {
    const previousEditor = editor.current, previousAssistant = assistant.current;
    if (!previousEditor?.background) await previousAssistant?.stop();
    if (current()) await previousEditor?.navigate();
  }
  async function action(work: (current: () => boolean) => Promise<void>, labelText = "Сохраняем последние изменения"): Promise<boolean> {
    const owner = lifetime.current;
    if (!owner || acting.current) return false;
    const current = () => lifetime.current === owner, operation = {};
    const previousEditor = editor.current, previousProject = activeProject.current;
    acting.current = operation; setBusy(true); setOperation({ label: labelText, startedAt: Date.now() }); setError("");
    try { await work(current); return current(); } catch (error) {
      if (!current()) return false;
      let message = label(error);
      if (!settings && previousEditor?.background && editor.current === previousEditor && activeProject.current === previousProject) {
        try { await previousEditor.resume(); } catch (resumeError) { message += ` ${label(resumeError)}`; }
      }
      if (current()) setError(message); return false;
    }
    finally {
      if (acting.current === operation) acting.current = null;
      if (current()) { setBusy(false); setOperation(null); }
    }
  }
  function clear() {
    reads.current.clear(); setOpening(null); activeProject.current = null; setResponse(null); setWriter(null); setBackground(false); setStatus("Сохранено"); prepared.current = null;
    setAllowTextRewrite(true);
    setInput({ kind: "text", text: "" }); history.replaceState(null, "", location.pathname);
  }
  async function fresh() {
    await action(async current => {
      await leave(current);
      if (!current()) return;
      clear(); setSettings(false);
    }, "Подготавливаем новое резюме");
  }
  async function open(id: string) {
    return action(async current => {
      if (response?.workspace.projectId === id) { await editor.current?.resume(); if (current()) setSettings(false); return; }
      await leave(current);
      if (!current()) return;
      const capture = reads.current.beginSelection(id);
      try {
        const result = await load(id, capture);
        if (result && reads.current.selectionCurrent(capture)) {
          setWriter(result.connection); select(result.next, result.available, capture); setProjects(result.catalog);
          setStatus("Сохранено"); prepared.current = null;
          setInput({ kind: "text", text: "" }); setSettings(false);
        }
      } finally { reads.current.cancelSelection(capture); }
    }, "Открываем резюме");
  }
  async function remove(id: string) {
    return action(async current => {
      if (activeProject.current === id) await leave(current);
      if (!current()) return;
      const result = await deleteProject(id);
      if (!current()) return;
      if (response?.workspace.projectId === id) clear();
      const catalog = await listProjects();
      if (!current()) return;
      setProjects(catalog);
      if (result.status === "cleanup_incomplete") throw new RichApiFailure(result.errorCode ?? "PROJECT_CLEANUP_INCOMPLETE");
    }, "Удаляем резюме");
  }
  async function archive(id: string, archived: boolean) {
    return action(async current => {
      if (archived && activeProject.current === id) await leave(current);
      if (!current()) return;
      await request(`/${id}/catalog/${archived ? "archive" : "restore"}`, "POST", {});
      if (!current()) return;
      if (archived && activeProject.current === id) clear();
      const catalog = await listProjects();
      if (current()) setProjects(catalog);
    }, archived ? "Перемещаем резюме в архив" : "Восстанавливаем резюме");
  }
  async function projectLifecycle(id: string, kind: "archive" | "delete") {
    return action(async current => {
      if (activeProject.current !== id) return;
      if (kind === "archive") await leave(current);
      if (!current()) return;
      clear();
      const catalog = await listProjects();
      if (current()) setProjects(catalog);
    });
  }
  useEffect(() => {
    const owner = {};
    lifetime.current = owner;
    let alive = true;
    const id = new URLSearchParams(location.search).get("project");
    const capture = id ? reads.current.beginSelection(id) : null;
    if (id && capture) void load(id, capture).then(result => {
      if (alive && result && reads.current.selectionCurrent(capture)) {
        setWriter(result.connection); select(result.next, result.available, capture); setProjects(result.catalog);
      }
    }).catch(error => { if (alive && reads.current.selectionCurrent(capture)) setError(label(error)); }).finally(() => {
      if (alive) setLoading(false);
      reads.current.cancelSelection(capture);
    });
    void listProjects().then(next => { if (alive) setProjects(next); }).catch(error => { if (alive) setError(label(error)); });
    return () => {
      alive = false;
      if (lifetime.current === owner) { lifetime.current = null; acting.current = null; reads.current.clear(); }
    };
  }, [adopt]);
  const generation = response?.generation;
  const creating = generation !== null && generation !== undefined && ["queued", "running"].includes(generation.status);
  useEffect(() => {
    if (!response || !generation || !["queued", "running"].includes(generation.status)) return;
    let alive = true, polling = false;
    const timer = setInterval(() => {
      if (polling) return;
      const capture = reads.current.begin("poll");
      if (!capture || capture.projectId !== response.workspace.projectId) return;
      polling = true;
      void projectRequest(`/${response.workspace.projectId}`).then(async next => {
        if (!alive || !reads.current.current("poll", capture)) return;
        if (next.generation?.status === "completed" && next.workspace.project) {
          const connection = await attachExclusiveWriter(next.workspace.projectId);
          if (!alive || !reads.current.current("poll", capture)) return;
          setWriter(connection); adopt(connection?.view.response ?? next, capture);
        } else adopt(next, capture);
        if (next.generation?.status === "completed") {
          const catalog = await listProjects();
          if (alive && reads.current.current("poll", capture)) setProjects(catalog);
        }
      }).catch(error => { if (alive && reads.current.current("poll", capture)) setError(label(error)); }).finally(() => { polling = false; });
    }, 700);
    return () => { alive = false; clearInterval(timer); };
  }, [response?.workspace.projectId, generation?.status, opening, adopt]);
  async function process() {
    await action(async () => {
      let id = response?.workspace.preDraft?.selectedSourceId ? response.workspace.projectId : null;
      if (hasInput(input)) {
        if (prepared.current?.input === input && !response?.workspace.project) id = prepared.current.projectId;
        else {
          const version = reads.current.beginReplacement();
          try {
            const selected = await projectRequest("/input", "POST", importBody(input));
            if (!reads.current.replacementCurrent(version)) return;
            select(selected, false, reads.current.beginSelection(selected.workspace.projectId));
            setAllowTextRewrite(allowTextRewrite); id = selected.workspace.projectId;
            prepared.current = { input, projectId: id };
            const capture = reads.current.opening, catalog = await listProjects();
            if (reads.current.matchesOpening(capture)) setProjects(catalog);
          } finally { reads.current.cancelReplacement(version); }
        }
      }
      if (id) {
        const capture = reads.current.begin("process");
        if (!capture || capture.projectId !== id) return;
        stage("Запускаем обработку резюме");
        try {
          await new FixedOperations(id).submit({ kind: "processing", allowTextRewrite });
          if (!reads.current.current("process", capture)) return;
          const next = await projectRequest(`/${id}`);
          if (reads.current.current("process", capture)) select(next, true);
        }
        catch (error) {
          if (!reads.current.current("process", capture)) return;
          if (error instanceof RichApiFailure && error.code === "JOB_DISABLED") {
            const next = await projectRequest(`/${id}/generation`, "POST", { allowTextRewrite });
            if (reads.current.current("process", capture)) select(next);
          }
          else throw error;
        }
      }
    }, input.kind === "file" ? "Загружаем и читаем файл" : "Читаем исходный текст");
  }
  async function upload(file: File) {
    return action(async current => {
      await leave(current);
      if (!current()) return;
      const body = new FormData(); body.append("file", file);
      const version = reads.current.beginReplacement();
      try {
        const imported = await projectRequest("/archive", "POST", body);
        if (!reads.current.replacementCurrent(version)) return;
        const connection = imported.workspace.project ? await attachExclusiveWriter(imported.workspace.projectId) : null;
        if (!reads.current.replacementCurrent(version)) return;
        setWriter(connection); select(connection?.view.response ?? imported, connection !== null,
          reads.current.beginSelection(imported.workspace.projectId));
        prepared.current = null; setInput({ kind: "text", text: "" }); setSettings(false);
        const capture = reads.current.opening, catalog = await listProjects();
        if (reads.current.matchesOpening(capture)) setProjects(catalog);
      } finally { reads.current.cancelReplacement(version); }
    }, "Открываем файл проекта");
  }
  async function exportFile(kind: "export" | "archive", filename?: string | ((current: RichProjectResponse) => string)) {
    return action(async () => {
      const capture = reads.current.begin(kind);
      if (!capture) throw new Error("Откройте резюме перед сохранением файла.");
      const current = editor.current ? await editor.current.flush() : response;
      if (!current) throw new Error("Откройте резюме перед сохранением файла.");
      if (!reads.current.current(kind, capture) || current.workspace.projectId !== capture.projectId) return;
      stage(kind === "export" ? "Создаём документ DOCX" : "Собираем файл проекта");
      const blob = await download(current.workspace.projectId, kind, current.workspace);
      if (!reads.current.current(kind, capture)) return;
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = typeof filename === "function" ? filename(current) : filename ?? (kind === "export" ? "resume.docx" : "project.foldcv");
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "Сохраняем изменения перед скачиванием");
  }
  return { response, writer, background, openingEpoch: opening?.selectionEpoch ?? 0, projects, input, setInput, textDraft, allowTextRewrite, setAllowTextRewrite, error, status, setStatus, busy, operation, loading, settings, setSettings,
    editor, assistant, acknowledge, action, fresh, open, remove, archive, projectLifecycle, process, upload, exportFile, dismissError };
}
