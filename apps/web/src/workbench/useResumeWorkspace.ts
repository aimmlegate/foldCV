import { errorMessage } from "../errors/messages";
import { useCallback, useEffect, useRef, useState } from "react";
import type { TemplateEditorHandle } from "../rich/TemplateEditor";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { AssistantHandle } from "../assistant/Drawer";
import { hasInput, importBody, type ResumeInput } from "../rich/import-source";
import { cancelImport, catalogFlag, createProject, deleteProject, listProjects, openFoldcv, projectTasks, resumeImport, startImport,
  type ProjectList, type ProjectTask } from "../projects/api";
import { IMPORT_WAIT_MS } from "../projects/import-wait";
import { ProjectApiFailure, type ProjectEditorConnection } from "../rich/v7-connection";
import { openEditor } from "./open-editor";
import { WorkspaceReads, type ReadCapture } from "./read-capture";

function label(error: unknown): string { return errorMessage(error); }
export type TemplateOpening = { response: TemplateProjectResponseV1; connection: ProjectEditorConnection };
export function useResumeWorkspace() {
  const [template, setTemplate] = useState<TemplateOpening | null>(null);
  const [projects, setProjects] = useState<ProjectList | null>(null);
  const [input, storeInput] = useState<ResumeInput>({ kind: "text", text: "" });
  const [textDraft, setTextDraft] = useState("");
  const [allowTextRewrite, setAllowTextRewrite] = useState(true);
  function setInput(next: ResumeInput) { storeInput(next); if (next.kind === "text") setTextDraft(next.text); }
  const [error, setError] = useState("");
  const dismissError = useCallback(() => setError(""), []);
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  const [importTask, setImportTask] = useState<ProjectTask | null>(null);
  const [operation, setOperation] = useState<{ label: string; startedAt: number; cancel?: () => Promise<void> } | null>(null);
  function stage(label: string, cancel?: () => Promise<void>) {
    setOperation(current => {
      const next = cancel ?? current?.cancel;
      const startedAt = current?.startedAt ?? Date.now();
      return next ? { label, startedAt, cancel: next } : { label, startedAt };
    });
  }
  const [loading, setLoading] = useState(() => new URLSearchParams(location.search).has("project"));
  const [settings, setSettings] = useState(false);
  const templateEditor = useRef<TemplateEditorHandle>(null);
  const assistant = useRef<AssistantHandle>(null);
  const reads = useRef(new WorkspaceReads());
  const [opening, setOpening] = useState<ReadCapture | null>(null);
  const lifetime = useRef<object | null>(null), acting = useRef<object | null>(null);
  const activeProject = useRef<string | null>(null);
  const adoptTemplate = useCallback((next: TemplateProjectResponseV1, capture: ReadCapture | null, connection?: ProjectEditorConnection) => {
    if (!reads.current.matchesOpening(capture) || next.workspace.projectId !== capture?.projectId
      || next.workspace.projectId !== activeProject.current) return;
    setTemplate(current => {
      const kept = connection ?? current?.connection;
      return kept ? { response: next, connection: kept } : current;
    });
    if (next.identity) setProjects(current => current ? { ...current, entries: current.entries.map(entry => entry.projectId === next.workspace.projectId
      ? { ...entry, title: next.identity?.title ?? entry.title, subtitle: next.identity?.subtitle ?? "" } : entry) } : current);
    const url = new URL(location.href); url.searchParams.set("project", next.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }, []);
  const acknowledgeTemplate = useCallback((next: TemplateProjectResponseV1) => adoptTemplate(next, opening), [adoptTemplate, opening]);
  function selectTemplate(connection: ProjectEditorConnection, loaded: ReadCapture) {
    const next = connection.response;
    if (loaded.projectId !== next.workspace.projectId) throw new ProjectApiFailure("INVALID_RESULT");
    if (!reads.current.adoptSelection(loaded)) return;
    setOpening(loaded); activeProject.current = next.workspace.projectId; adoptTemplate(next, loaded, connection);
  }
  async function load(id: string, capture: ReadCapture) {
    const connection = await openEditor(id);
    if (!reads.current.selectionCurrent(capture)) return null;
    if (connection.response.workspace.projectId !== id) throw new ProjectApiFailure("INVALID_RESULT");
    const catalog = await listProjects();
    return { connection, catalog };
  }
  function show(result: NonNullable<Awaited<ReturnType<typeof load>>>, capture: ReadCapture) {
    selectTemplate(result.connection, capture);
    setProjects(result.catalog);
  }
  async function leave(current: () => boolean) {
    const previousEditor = templateEditor.current, previousAssistant = assistant.current;
    if (!previousEditor?.background) await previousAssistant?.stop();
    if (current()) await previousEditor?.navigate();
  }
  async function action(work: (current: () => boolean) => Promise<void>, labelText = "Сохраняем последние изменения"): Promise<boolean> {
    const owner = lifetime.current;
    if (!owner || acting.current) return false;
    const current = () => lifetime.current === owner, operation = {};
    const previousEditor = templateEditor.current, previousProject = activeProject.current;
    acting.current = operation; setBusy(true); setOperation({ label: labelText, startedAt: Date.now() }); setError("");
    try { await work(current); return current(); } catch (error) {
      if (!current()) return false;
      let message = label(error);
      if (!settings && previousEditor?.background && templateEditor.current === previousEditor && activeProject.current === previousProject) {
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
    reads.current.clear(); setOpening(null); activeProject.current = null; setTemplate(null); setStatus("Сохранено");
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
      if (activeProject.current === id && template) { await templateEditor.current?.resume(); if (current()) setSettings(false); return; }
      await leave(current);
      if (!current()) return;
      const capture = reads.current.beginSelection(id);
      try {
        const result = await load(id, capture);
        if (result && reads.current.selectionCurrent(capture)) {
          show(result, capture);
          setStatus("Сохранено");
          setInput({ kind: "text", text: "" }); setSettings(false);
        }
      } finally { reads.current.cancelSelection(capture); }
    }, "Открываем резюме");
  }
  async function remove(id: string) {
    return action(async current => {
      if (activeProject.current === id) await leave(current);
      if (!current()) return;
      const incomplete = (await deleteProject(id)).cleanupStatus === "cleanup_incomplete";
      if (!current()) return;
      if (template?.response.workspace.projectId === id) clear();
      const catalog = await listProjects();
      if (!current()) return;
      setProjects(catalog);
      if (incomplete) throw new ProjectApiFailure("PROJECT_CLEANUP_INCOMPLETE");
    }, "Удаляем резюме");
  }
  async function archive(id: string, archived: boolean) {
    return action(async current => {
      if (archived && activeProject.current === id) await leave(current);
      if (!current()) return;
      await catalogFlag(id, archived);
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
      if (alive && result && reads.current.selectionCurrent(capture)) show(result, capture);
    }).catch(error => { if (alive && reads.current.selectionCurrent(capture)) setError(label(error)); }).finally(() => {
      if (alive) setLoading(false);
      reads.current.cancelSelection(capture);
    });
    void listProjects().then(next => { if (alive) setProjects(next); }).catch(error => { if (alive) setError(label(error)); });
    return () => {
      alive = false;
      if (lifetime.current === owner) { lifetime.current = null; acting.current = null; reads.current.clear(); }
    };
  }, [adoptTemplate]);
  async function finishTemplateImport(id: string, first: ProjectTask, current: () => boolean, startedAt = Date.now()) {
    let task = first;
    let operationId: string | null = null, stopped = false;
    const stop = async () => {
      try { await cancelImport(id, task.id); stopped = true; }
      catch (error) { if (current()) setError(label(error)); }
    };
    stage("Запускаем импорт", stop);
    setImportTask(task);
    while (task.state === "running") {
      if (!current() || stopped) return;
      const policySeconds = task.detail["processingSeconds"];
      const wait = typeof policySeconds === "number" ? policySeconds * 1000 + 223000 : IMPORT_WAIT_MS;
      if (Date.now() - startedAt > wait) throw new ProjectApiFailure("PROCESS_TIMEOUT");
      const named = task.detail["operationId"];
      if (typeof named === "string" && named) operationId = named;
      stage(task.stage === "processing" ? "Импортируем по шаблону" : "Запускаем импорт", stop);
      await new Promise(resolve => setTimeout(resolve, 1000));
      if (!current() || stopped) return;
      const tasks = await projectTasks(id);
      const next = tasks.find(item => item.id === task.id);
      if (!next) {
        if (!operationId) throw new ProjectApiFailure("PROCESS_FAILED");
        task = await resumeImport(id, operationId);
        continue;
      }
      task = next;
      setImportTask(task);
    }
    if (!current() || stopped) return;
    if (task.state === "cancelled") throw new ProjectApiFailure("CANCELLED");
    if (task.state !== "succeeded") throw new ProjectApiFailure(task.error ?? "PROCESS_FAILED");
    if (!current()) return;
    const capture = reads.current.beginSelection(id);
    try {
      const result = await load(id, capture);
      if (result && reads.current.selectionCurrent(capture)) {
        show(result, capture); setInput({ kind: "text", text: "" });
      }
    } finally { reads.current.cancelSelection(capture); }
  }
  async function resumeTemplate() {
    const workspace = template?.response.workspace;
    const operation = workspace?.preDraft?.templateOperations.at(-1);
    if (!workspace) return false;
    return action(async current => {
      const tasks = await projectTasks(workspace.projectId);
      const running = tasks.find(task => task.kind === "import" && task.state === "running");
      const task = running ?? (operation ? await resumeImport(workspace.projectId, operation.id)
        : await startImport(workspace.projectId, { clientRequestId: crypto.randomUUID(), allowTextRewrite }));
      await finishTemplateImport(workspace.projectId, task, current);
    }, "Продолжаем импорт");
  }
  /** The pasted text or file becomes a V7 pre-draft; one import task fills it and the result opens in the editor. */
  async function process() {
    await action(async current => {
      if (!hasInput(input)) return;
      const version = reads.current.beginReplacement();
      let id: string;
      try {
        const created = await createProject(importBody(input));
        if (!reads.current.replacementCurrent(version)) return;
        id = created.workspace.projectId;
      } finally { reads.current.cancelReplacement(version); }
      const catalog = await listProjects();
      if (current()) setProjects(catalog);
      const startedAt = Date.now();
      const task = await startImport(id, { clientRequestId: crypto.randomUUID(), allowTextRewrite });
      const url = new URL(location.href); url.searchParams.set("project", id); history.replaceState(null, "", url.pathname + url.search);
      await finishTemplateImport(id, task, current, startedAt);
    }, input.kind === "file" ? "Загружаем и читаем файл" : "Читаем исходный текст");
  }
  async function upload(file: File) {
    return action(async current => {
      await leave(current);
      if (!current()) return;
      const version = reads.current.beginReplacement();
      try {
        const opened = await openFoldcv(file);
        if (!reads.current.replacementCurrent(version)) return;
        const connection = await openEditor(opened.workspace.projectId);
        if (!reads.current.replacementCurrent(version)) return;
        selectTemplate(connection, reads.current.beginSelection(opened.workspace.projectId));
        setInput({ kind: "text", text: "" }); setSettings(false);
        const capture = reads.current.opening, catalog = await listProjects();
        if (reads.current.matchesOpening(capture)) setProjects(catalog);
      } finally { reads.current.cancelReplacement(version); }
    }, "Открываем файл проекта");
  }
  async function exportFile(kind: "export" | "archive", filename?: string | ((current: TemplateProjectResponseV1) => string)) {
    const deliver = (blob: Blob, name: string) => {
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = name;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    const fallback = kind === "export" ? "resume.docx" : "project.foldcv";
    return action(async () => {
      const capture = reads.current.begin(kind);
      if (!capture) throw new Error("Откройте резюме перед сохранением файла.");
      await templateEditor.current?.flush();
      const connection = template?.connection;
      const current = connection?.response ?? template?.response;
      if (!current || !connection) throw new Error("Откройте резюме перед сохранением файла.");
      if (!reads.current.current(kind, capture) || current.workspace.projectId !== capture.projectId) return;
      stage(kind === "export" ? "Создаём документ DOCX" : "Собираем файл проекта");
      let blob: Blob;
      // The editor token and the flushed revision go with the file. Refresh adopts the commit.
      try { blob = kind === "export" ? (await connection.exportDocx()).blob : await connection.saveFoldcv(); }
      finally { if (reads.current.current(kind, capture)) await templateEditor.current?.refresh(); }
      if (reads.current.current(kind, capture)) deliver(blob, typeof filename === "function" ? filename(current) : filename ?? fallback);
    }, "Сохраняем изменения перед скачиванием");
  }
  async function renameTemplate(title: string) {
    const next = title.trim();
    if (!next) return false;
    return action(async current => {
      const connection = template?.connection;
      if (!connection) return;
      await templateEditor.current?.flush();
      if (!current()) return;
      await connection.rename(next);
      if (!current()) return;
      await templateEditor.current?.refresh();
    }, "Переименовываем резюме");
  }
  return { template, templateEditor, acknowledgeTemplate, openingEpoch: opening?.selectionEpoch ?? 0, projects, input, setInput, textDraft,
    allowTextRewrite, setAllowTextRewrite, error, status, setStatus, busy, operation, importTask, resumeTemplate, loading, settings, setSettings,
    assistant, action, fresh, open, remove, archive, projectLifecycle, process, upload, exportFile, renameTemplate, dismissError };
}
