import { errorMessage } from "../errors/messages";
import { useCallback, useEffect, useRef, useState } from "react";
import type { TemplateEditorHandle } from "../rich/TemplateEditor";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { AssistantHandle } from "../assistant/Drawer";
import { importBody } from "../rich/import-source";
import { catalogFlag, createProject, deleteProject, listProjects, openFoldcv, projectTasks, resumeImport, startImport,
  type ImportOptions, type ProjectList } from "../projects/api";
import { ProjectApiFailure, type ProjectEditorConnection } from "../rich/v7-connection";
import { openEditor } from "./open-editor";
import { WorkspaceReads, type ReadCapture } from "./read-capture";
import type { ImportEntry } from "./import/progress";
import { ImportTracker } from "./import/tracker";

function label(error: unknown): string { return errorMessage(error); }
export type TemplateOpening = { response: TemplateProjectResponseV1; connection: ProjectEditorConnection };
export function useResumeWorkspace() {
  const [template, setTemplate] = useState<TemplateOpening | null>(null);
  const [projects, setProjects] = useState<ProjectList | null>(null);
  const [error, setError] = useState("");
  const dismissError = useCallback(() => setError(""), []);
  const [status, setStatus] = useState("Сохранено");
  const [busy, setBusy] = useState(false);
  // Imports run beside every other action (feedback item 20); the tracker follows each project's task.
  const [imports, setImports] = useState<ReadonlyMap<string, ImportEntry>>(() => new Map());
  const tracker = useRef<ImportTracker | null>(null);
  const [operation, setOperation] = useState<{ label: string; startedAt: number } | null>(null);
  function stage(label: string) {
    setOperation(current => ({ label, startedAt: current?.startedAt ?? Date.now() }));
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
    // A pre-draft may be importing already (another tab session, a reload): follow its running task.
    const tasks = connection.response.workspace.project ? [] : await projectTasks(id);
    return { connection, catalog, running: tasks.find(task => task.kind === "import" && task.state === "running") ?? null };
  }
  function show(result: NonNullable<Awaited<ReturnType<typeof load>>>, capture: ReadCapture) {
    selectTemplate(result.connection, capture);
    setProjects(result.catalog);
    const { workspace } = result.connection.response;
    if (result.running && tracker.current?.get(workspace.projectId)?.task.id !== result.running.id)
      tracker.current?.track(workspace.projectId, result.running, workspace.title);
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
    history.replaceState(null, "", location.pathname);
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
      // A shown pre-draft is read again: its import may have published it meanwhile.
      if (activeProject.current === id && template?.response.workspace.project) { await templateEditor.current?.resume(); if (current()) setSettings(false); return; }
      await leave(current);
      if (!current()) return;
      const capture = reads.current.beginSelection(id);
      try {
        const result = await load(id, capture);
        if (result && reads.current.selectionCurrent(capture)) {
          show(result, capture);
          setStatus("Сохранено"); setSettings(false);
        }
      } finally { reads.current.cancelSelection(capture); }
    }, "Открываем резюме");
  }
  async function remove(id: string) {
    return action(async current => {
      if (activeProject.current === id) await leave(current);
      if (!current()) return;
      // The service refuses to delete a project whose import still runs.
      await tracker.current?.stop(id);
      const incomplete = (await deleteProject(id)).cleanupStatus === "cleanup_incomplete";
      tracker.current?.dismiss(id);
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
  // The tracker outlives renders; its callback reads the latest closures through this ref.
  const finished = useRef<(entry: ImportEntry) => void>(() => {});
  finished.current = entry => {
    void listProjects().then(next => { if (lifetime.current) setProjects(next); }).catch(() => {});
    if (entry.task.state === "succeeded" && activeProject.current === entry.projectId) void reopenImported(entry.projectId);
  };
  useEffect(() => {
    const owner = {};
    lifetime.current = owner;
    let alive = true;
    const following = new ImportTracker(setImports, entry => finished.current(entry));
    tracker.current = following;
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
      following.close();
      if (tracker.current === following) tracker.current = null;
      if (lifetime.current === owner) { lifetime.current = null; acting.current = null; reads.current.clear(); }
    };
  }, [adoptTemplate]);
  /** Open the project again after its import published it; the import screen keeps an Open button if this is refused. */
  async function reopenImported(id: string) {
    return action(async () => {
      const capture = reads.current.beginSelection(id);
      try {
        const result = await load(id, capture);
        if (result && reads.current.selectionCurrent(capture)) show(result, capture);
      } finally { reads.current.cancelSelection(capture); }
    }, "Открываем резюме");
  }
  async function resumeTemplate() {
    const workspace = template?.response.workspace;
    const operation = workspace?.preDraft?.templateOperations.at(-1);
    if (!workspace) return false;
    return action(async () => {
      const tasks = await projectTasks(workspace.projectId);
      const running = tasks.find(task => task.kind === "import" && task.state === "running");
      const task = running ?? (operation ? await resumeImport(workspace.projectId, operation.id)
        : await startImport(workspace.projectId, { clientRequestId: crypto.randomUUID(), allowTextRewrite: true, effort: null }));
      tracker.current?.track(workspace.projectId, task, workspace.title);
    }, "Продолжаем импорт");
  }
  /** The file becomes a V7 pre-draft and its import starts; the action ends there, so other resumes, Settings and more
   * imports stay available while the tracker follows this one. */
  async function process(file: File, options: ImportOptions) {
    await action(async current => {
      const version = reads.current.beginReplacement();
      let id: string;
      try {
        const created = await createProject(importBody({ kind: "file", file }));
        if (!reads.current.replacementCurrent(version)) return;
        id = created.workspace.projectId;
      } finally { reads.current.cancelReplacement(version); }
      const catalog = await listProjects();
      if (current()) setProjects(catalog);
      stage("Запускаем импорт");
      let refused: unknown = null;
      try { tracker.current?.track(id, await startImport(id, { clientRequestId: crypto.randomUUID(), ...options }), file.name, options); }
      catch (error) { refused = error; }
      if (!current()) return;
      // The new resume opens either way: its import screen, or the pre-draft with «Продолжить импорт».
      const capture = reads.current.beginSelection(id);
      try {
        const result = await load(id, capture);
        if (result && reads.current.selectionCurrent(capture)) { show(result, capture); setSettings(false); }
      } finally { reads.current.cancelSelection(capture); }
      if (refused) throw refused;
    }, "Загружаем и читаем файл");
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
        setSettings(false);
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
  const importActions = {
    stop: (id: string) => void tracker.current?.stop(id), retry: (id: string) => void tracker.current?.retry(id),
    dismiss: (id: string) => tracker.current?.dismiss(id), reopen: (id: string) => void reopenImported(id),
  };
  return { template, templateEditor, acknowledgeTemplate, openingEpoch: opening?.selectionEpoch ?? 0, projects,
    error, status, setStatus, busy, operation, imports, importActions, resumeTemplate, loading, settings, setSettings,
    assistant, action, fresh, open, remove, archive, projectLifecycle, process, upload, exportFile, renameTemplate, dismissError };
}
