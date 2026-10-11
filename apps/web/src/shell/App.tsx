import * as Tabs from "@radix-ui/react-tabs";
import { useEffect, useReducer, useRef, useState } from "react";
import type { Block, Facts } from "../contracts/generated/project";
import { draftFor, editableFactValue, editorReducer, hasUnappliedDraft, initialEditorState, selectedBlock } from "../editor/state";
import type { Panel } from "../editor/state";
import type { Action, EditorState } from "../editor/state";
import type { PrepareRequest } from "../contracts/generated/prepare_request";
import { PreviewWorkflow } from "../preview/workflow";
import type { PreviewState } from "../preview/workflow";
import { exportReadiness } from "../preview/readiness";
import { ImportPanel } from "../import/ImportPanel";
import { ImportWorkflow } from "../import/workflow";
import type { ImportState } from "../import/workflow";
import { ConnectionPanel } from "../connection/ConnectionPanel";
import { FactPanel } from "../facts/FactPanel";
import { FactWorkflow } from "../facts/workflow";
import type { FactView } from "../facts/workflow";
import { adaptWorking } from "../facts/working";
import { adaptDraftedWorking } from "../facts/working";
import { emptyManualInput } from "../facts/working";
import type { ManualInput, WorkingDraft } from "../facts/working";
import { WorkingSources } from "../facts/WorkingSources";
import { DraftWorkflow } from "../facts/draftWorkflow";
import type { DraftView } from "../facts/draftWorkflow";
import type { FactSheet } from "../contracts/generated/fact_sheet";
import type { DraftResult } from "../contracts/generated/draft_result";
import { RewriteWorkflow, currentRewriteDependencyHash } from "../editor/rewriteWorkflow";
import type { RewriteView } from "../editor/rewriteWorkflow";
import catalog from "../../../../contracts/technology-catalog.json" with { type: "json" };
import { control, field, primary } from "../editor/styles";
import { StructuredFields } from "../editor/StructuredFields";
import { RewriteControls } from "../editor/RewriteControls";
import { CoveragePanel } from "../editor/CoveragePanel";
import { coverageReview, verifyWorkingSources } from "../editor/coverage";
import { fetchTrustedTemplateAssets, openProject, saveProject } from "../project/archive";
import type { OpenedArchive } from "../project/archive";
import type { LegacyV2 } from "../project/archive";

type ThemeMode = "light" | "dark" | "system";
const THEME_KEY = "foldcv-theme";
const titles: Record<Block["kind"], string> = {
  profile: "О себе", job_prose: "Последний проект", contact: "Контакты", focus: "Фокус технологий",
  education: "Образование", skills: "Навыки", early_career: "Ранний опыт",
};

function savedMode(): ThemeMode {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}
function isThemeMode(value: string): value is ThemeMode { return value === "light" || value === "dark" || value === "system"; }
function isPanel(value: string): value is Panel { return value === "preview" || value === "sources" || value === "checks"; }
function factText(fact: Facts[number]): string {
  if (fact.kind === "text") return fact.value.text;
  if (fact.kind === "technology") return fact.value.display;
  if (fact.kind === "metric") return `${fact.value.comparator === "at_most" ? "До " : ""}${fact.value.number} ${fact.value.unit}`;
  if (fact.kind === "leadership") return fact.value.action;
  return String(fact.value.year);
}

export function App() {
  const [mode, setMode] = useState<ThemeMode>(savedMode);
  const [state, dispatch] = useReducer(editorReducer, initialEditorState);
  const stateRef = useRef<EditorState>(initialEditorState);
  const [preview, setPreview] = useState<PreviewState>({ status: "empty", artifact: null, error: null });
  const [importState, setImportState] = useState<ImportState>({ entries: [], selectedId: null, pending: false, error: null });
  const importWorkflowRef = useRef<ImportWorkflow | null>(null);
  if (!importWorkflowRef.current) importWorkflowRef.current = new ImportWorkflow(setImportState);
  const importWorkflow = importWorkflowRef.current;
  const [factView, setFactView] = useState<FactView>({ sheet: null, pending: false, stale: false, error: null });
  const factWorkflowRef = useRef<FactWorkflow | null>(null);
  if (!factWorkflowRef.current) factWorkflowRef.current = new FactWorkflow(setFactView);
  const factWorkflow = factWorkflowRef.current;
  useEffect(() => { factWorkflow.sourcesChanged(importState.entries); }, [factWorkflow, importState.entries]);
  const [draftReady, setDraftReady] = useState(false);
  const [draftView, setDraftView] = useState<DraftView>({ pending: false, stage: "idle", completed: 0, error: null });
  const draftWorkflowRef = useRef<DraftWorkflow | null>(null);
  if (!draftWorkflowRef.current) draftWorkflowRef.current = new DraftWorkflow(setDraftView, openGenerated);
  const draftWorkflow = draftWorkflowRef.current;
  const [rewriteReady, setRewriteReady] = useState(false);
  const [rewriteView, setRewriteView] = useState<RewriteView>({ pending: false, error: null, completed: 0 });
  const [rewriteInstruction, setRewriteInstruction] = useState("");
  const [focusedUnit, setFocusedUnit] = useState<string | null>(null);
  const rewriteWorkflowRef = useRef<RewriteWorkflow | null>(null);
  if (!rewriteWorkflowRef.current) rewriteWorkflowRef.current = new RewriteWorkflow(setRewriteView,
    (result) => send({ type: "rewriteProposed", result }),
    (result, loadId) => send({ type: "rewritePreflight", result, loadId }));
  const rewriteWorkflow = rewriteWorkflowRef.current;
  useEffect(() => {
    const abort = new AbortController();
    void fetch("/v1/capabilities", { credentials: "same-origin", cache: "no-store", signal: abort.signal })
      .then((response) => response.ok && response.headers.get("content-type")?.startsWith("application/json") ?
        response.json() as Promise<unknown> : null)
      .then((value) => { if (!abort.signal.aborted && typeof value === "object" && value !== null) {
        if ("generationReady" in value && value.generationReady === true) setDraftReady(true);
        if ("rewriteReady" in value && value.rewriteReady === true) setRewriteReady(true);
      } })
      .catch(() => undefined);
    return () => abort.abort();
  }, []);
  useEffect(() => { draftWorkflow.cancel(); }, [draftWorkflow, importState.entries, factView.sheet]);
  const [closeProjectPrompt, setCloseProjectPrompt] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [manualForm, setManualForm] = useState<ManualInput>(emptyManualInput);
  const manualRef = useRef<ManualInput>(emptyManualInput);
  const [assertionDraft, setAssertionDraft] = useState("");
  const [factEdits, setFactEdits] = useState<Record<string, string>>({});
  const [archiveEpoch, setArchiveEpoch] = useState(0);
  const projectOriginals = useRef<Record<string, Uint8Array>>({});
  const archivedTemplateAssets = useRef<Map<string, Uint8Array> | null>(null);
  const [legacy, setLegacy] = useState<LegacyV2 | null>(null);
  const openingEpoch = useRef(0);
  const [replacement, setReplacement] = useState<OpenedArchive | null>(null);
  const workflowRef = useRef<PreviewWorkflow | null>(null);
  if (!workflowRef.current) workflowRef.current = new PreviewWorkflow(setPreview, (artifact, kind) => {
    const current = stateRef.current;
    if (!current.project || !current.presentation || !exportReadiness(current).allowed ||
        !workflow.matches({ project: current.project, presentation: current.presentation }, artifact)) return;
    const bytes = kind === "pdf" ? artifact.pdf : artifact.docx;
    const url = URL.createObjectURL(new Blob([Uint8Array.from(bytes)],
      { type: kind === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = kind === "pdf" ? "resume.pdf" : "resume.docx";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  });
  const workflow = workflowRef.current;
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!preview.artifact) { setPdfUrl(null); return; }
    const url = URL.createObjectURL(new Blob([Uint8Array.from(preview.artifact.pdf)], { type: "application/pdf" }));
    setPdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [preview.artifact]);
  function send(action: Action) {
    const previous = stateRef.current;
    const next = editorReducer(previous, action);
    stateRef.current = next;
    if (next.project !== previous.project || next.presentation !== previous.presentation ||
        action.type === "draft" || action.type === "factDraft" || action.type === "presentationDraft" ||
        action.type === "structuredDraft")
      rewriteWorkflow.cancel();
    const invalidated = next.project !== previous.project || next.presentation !== previous.presentation ||
        action.type === "draft" || action.type === "factDraft" || action.type === "presentationDraft" ||
        action.type === "structuredDraft" || action.type === "structuredCancel" ||
        action.type === "cancel" || action.type === "cancelFact" || action.type === "presentationCancel";
    if (invalidated) {
      workflow.invalidate();
      if (!hasUnappliedDraft(next) && next.project && next.presentation)
        workflow.restore({ project: next.project, presentation: next.presentation });
    }
    dispatch(action);
  }
  const currentSources = state.working?.sources;
  useEffect(() => {
    if (!currentSources || !state.loadId) return;
    const loadId = state.loadId;
    let current = true;
    void verifyWorkingSources(currentSources).then((proof) => {
      if (current) send({ type: "sourceIntegrity", loadId, sources: currentSources, proof });
    }).catch(() => {
      if (current) send({ type: "sourceIntegrity", loadId, sources: currentSources,
        proof: { valid: false, matches: () => false } });
    });
    return () => { current = false; };
  }, [currentSources, state.loadId]);
  function refreshPreview(exportKind?: "pdf" | "docx") {
    const current = stateRef.current;
    if (!current.project || !current.presentation) return;
    if (exportKind && !exportReadiness(current).allowed) return;
    if (exportReadiness(current).pendingInput) {
      setPreview({ status: "error", artifact: preview.artifact,
        error: "Сначала примените или отмените введённые правки." });
      return;
    }
    const input: PrepareRequest = { project: current.project, presentation: current.presentation };
    workflow.request(input, exportKind);
  }
  async function saveArchive(): Promise<void> {
    try {
      const captured = { editor: stateRef.current, imports: importWorkflow.snapshot(),
        projectOriginals: projectOriginals.current, legacy,
        facts: factWorkflow.snapshot(), manualForm: manualRef.current, assertionDraft, factEdits,
        rewriteInstruction, render: workflow.ready };
      const fetched = captured.editor.project?.template ? await fetchTrustedTemplateAssets() : null;
      const trustedAssets = fetched ?? archivedTemplateAssets.current;
      const bytes = await saveProject({ ...captured, trustedAssets });
      const url = URL.createObjectURL(new Blob([Uint8Array.from(bytes)], { type: "application/zip" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "resume.cvproject";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
      setSaveMessage(!captured.editor.project?.template || trustedAssets ?
        "Проект подготовлен к скачиванию. Проверьте файл в загрузках браузера." :
        "Проект подготовлен к скачиванию без файлов шаблона. Проверьте файл в загрузках браузера.");
    } catch { setSaveMessage("Не удалось подготовить архив. Проверьте исходные файлы и повторите сохранение."); }
  }
  function installArchive(opened: OpenedArchive): void {
    openingEpoch.current += 1;
    draftWorkflow.cancel(); rewriteWorkflow.cancel(); workflow.resetArchive();
    importWorkflow.restore(opened.imports.state, opened.imports.originals);
    factWorkflow.restore(opened.facts, importWorkflow.state.entries);
    projectOriginals.current = opened.projectOriginals;
    archivedTemplateAssets.current = opened.trustedAssets;
    setLegacy(opened.legacy);
    manualRef.current = opened.manualForm;
    setManualForm(opened.manualForm);
    setAssertionDraft(opened.assertionDraft);
    setFactEdits(opened.factEdits);
    setRewriteInstruction(opened.rewriteInstruction);
    setArchiveEpoch((epoch) => epoch + 1);
    send({ type: "restoreArchive", state: opened.editor });
    setReplacement(null);
    setOpenError(opened.migration);
    setSaveMessage(null);
  }
  function clearArchiveOwners(): void {
    projectOriginals.current = {};
    archivedTemplateAssets.current = null;
    setLegacy(null);
    manualRef.current = emptyManualInput;
    setManualForm(emptyManualInput);
    setAssertionDraft("");
    setFactEdits({});
    setRewriteInstruction("");
    setArchiveEpoch((epoch) => epoch + 1);
  }
  async function chooseArchive(file: File | undefined): Promise<void> {
    if (!file) return;
    const epoch = ++openingEpoch.current;
    setOpenError(null);
    try {
      if (file.size > 64 * 1024 * 1024) throw new Error("ARCHIVE_TOO_LARGE");
      const opened = await openProject(new Uint8Array(await file.arrayBuffer()));
      if (epoch !== openingEpoch.current) return;
      if (stateRef.current.project || legacy || importWorkflow.state.entries.length || stateRef.current.sourceText.trim() ||
          JSON.stringify(manualRef.current) !== JSON.stringify(emptyManualInput) || factWorkflow.view.sheet ||
          assertionDraft.trim() || Object.keys(factEdits).length ||
          Object.keys(stateRef.current.presentationDrafts).length || Object.keys(stateRef.current.structuredDrafts).length ||
          Object.keys(stateRef.current.drafts).length || Object.keys(stateRef.current.factDrafts).length ||
          rewriteInstruction.trim()) setReplacement(opened);
      else installArchive(opened);
    } catch (error) {
      if (epoch === openingEpoch.current) setOpenError(error instanceof Error && error.message === "ARCHIVE_TOO_LARGE" ?
        "Архив больше 64 МБ. Выберите меньший .cvproject; текущий проект сохранён." :
        "Архив не открыт: он повреждён, неполон или имеет неподдерживаемую версию. Выберите другой .cvproject; текущий проект сохранён.");
    }
  }
  const project = state.project;
  const isExample = project?.projectId === "project_synthetic";
  const block = selectedBlock(state);
  const readiness = exportReadiness(state);
  const unapplied = readiness.pendingInput;
  const canExport = preview.status === "ready" && workflow.ready !== null && Boolean(project && state.presentation) &&
    readiness.allowed && workflow.matches({ project: project!, presentation: state.presentation! }, workflow.ready);
  const unsaved = state.dirty || unapplied || importState.entries.length > 0 || legacy !== null ||
    JSON.stringify(manualForm) !== JSON.stringify(emptyManualInput) || assertionDraft.trim().length > 0 ||
    Object.keys(factEdits).length > 0 || rewriteInstruction.trim().length > 0;
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => { document.documentElement.dataset.theme = mode === "system" ? (media.matches ? "dark" : "light") : mode; };
    apply(); media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);
  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);
  function changeTheme(next: ThemeMode) {
    if (next === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, next);
    setMode(next);
  }
  function openImported(manual: ManualInput) {
    try {
      if (stateRef.current.project) throw new Error("Закройте текущий проект перед открытием импорта.");
      const sources = importState.entries.map((entry) => {
        const originalBytes = importWorkflow.original(entry.result.sourceId);
        if (!originalBytes) throw new Error("Не найдены байты оригинального источника.");
        return { entry: structuredClone(entry), originalBytes };
      });
      const currentSheet = factWorkflow.sheetForManual(importState.entries);
      const working: WorkingDraft = { transportVersion: 1, sources,
        sheet: structuredClone(currentSheet), priorSheet: factWorkflow.view.sheet === currentSheet ? null :
          factWorkflow.view.sheet ? structuredClone(factWorkflow.view.sheet) : null,
        sourceReviewStale: factView.stale, manual: structuredClone(manual), draft: null };
      const adapted = adaptWorking(working);
      send({ type: "loadImported", loadId: crypto.randomUUID(), ...adapted, working });
      setOpenError(null);
    } catch (error) { setOpenError(error instanceof Error ? error.message : "Не удалось открыть черновик."); }
  }
  function openGenerated(sheet: FactSheet, draft: DraftResult, manual: ManualInput) {
    if (stateRef.current.project) throw new Error("Закройте текущий проект перед открытием импорта.");
    const sources = importWorkflow.state.entries.map((entry) => {
      const originalBytes = importWorkflow.original(entry.result.sourceId);
      if (!originalBytes) throw new Error("Не найдены байты оригинального источника.");
      return { entry: structuredClone(entry), originalBytes };
    });
    const working: WorkingDraft = { transportVersion: 1, sources, sheet: structuredClone(sheet),
      priorSheet: factWorkflow.view.sheet ? structuredClone(factWorkflow.view.sheet) : null,
      sourceReviewStale: false, manual: structuredClone(manual), draft: structuredClone(draft) };
    const adapted = adaptDraftedWorking(working);
    send({ type: "loadImported", loadId: crypto.randomUUID(), ...adapted, working });
    setOpenError(null);
  }
  function draftImported(manual: ManualInput, isManualCurrent: () => boolean) {
    if (!draftReady || stateRef.current.project) return;
    const entries = importWorkflow.state.entries;
    const accepted = factWorkflow.view.sheet;
    const snapshot = JSON.stringify({ entries, accepted });
    void draftWorkflow.run(entries, accepted, manual, () => isManualCurrent() && !stateRef.current.project &&
      JSON.stringify({ entries: importWorkflow.state.entries, accepted: factWorkflow.view.sheet }) === snapshot);
  }
  function rewriteBlock() {
    const current = stateRef.current;
    const target = selectedBlock(current);
    if (!target || !rewriteReady) return;
    const project = current.project;
    void rewriteWorkflow.run(current, target, rewriteInstruction, () =>
      stateRef.current.project === project && stateRef.current.project?.revision === project?.revision &&
      stateRef.current.project?.views.find((item) => item.id === target.id)?.revision === target.revision &&
      stateRef.current.drafts[target.id] === current.drafts[target.id]);
  }
  function reconcileBlock() {
    const current = stateRef.current;
    const target = selectedBlock(current);
    if (!target || !current.project) return;
    const baseRevision = current.project.revision;
    void currentRewriteDependencyHash(current, target).then((dependencyHash) =>
      send({ type: "reconcile", id: target.id, projectId: current.project!.projectId,
        loadId: current.loadId!, baseRevision,
        blockRevision: target.revision, dependencyHash }));
  }
  function openSource(sourceId: string, unitId: string) {
    setFocusedUnit(unitId.startsWith(`view_${sourceId}_`) ? unitId : `view_${sourceId}_${unitId}`);
    send({ type: "panel", panel: "sources" });
    window.requestAnimationFrame(() => document.getElementById(`source-${sourceId}-${unitId}`)?.scrollIntoView({ block: "nearest" }));
  }
  const coverage = readiness.review;
  const reviewCount = (project?.review.decisions.filter((decision) => decision.disposition === "unresolved").length ?? 0) +
    state.workingIssues.length + (coverage?.blockers.length ?? 0) +
    (coverage?.warnings.filter((issue) => !issue.acknowledged).length ?? 0);
  const staleCount = project?.views.filter((view) => view.status === "stale").length ?? 0;
  const isReviewed = Boolean(block && project?.review.decisions.some((decision) => decision.targetKind === "block" && decision.targetId === block.id && decision.targetRevision === block.revision));
  const relatedFacts = block ? project?.facts.filter((fact) => block.state.factIds.includes(fact.id) ||
    (block.kind === "skills" || block.kind === "focus") && fact.kind === "technology" && fact.jobId === null) ?? [] : [];
  const correctedUnits = new Set(state.working && block ? Object.entries(state.working.sheet.userCorrections ?? {})
    .filter(([, userId]) => block.state.factIds.includes(userId))
    .flatMap(([sourceId]) => state.working!.sheet.facts.find((fact) => fact.id === sourceId)?.evidence.map((evidence) =>
      `view_${evidence.sourceId}_${evidence.unitId}`) ?? []) : []);
  const relatedUnits = block ? project?.sources.flatMap((source) => source.units.filter((unit) =>
    correctedUnits.has(unit.id) || unit.representedFactIds.some((id) => block.state.factIds.includes(id)))) ?? [] : [];
  const focusedSource = !state.working && focusedUnit ? project?.sources.flatMap((source) =>
    source.units.filter((unit) => unit.id === focusedUnit ||
      `view_${source.id}_${unit.id}` === focusedUnit).map((unit) => ({ source, unit })))[0] : undefined;
  function blockTitle(item: Block): string {
    if (item.kind !== "job_prose") return titles[item.kind];
    const jobId = Object.entries(state.presentation?.jobProseBlocks ?? {}).find(([, blockId]) => blockId === item.id)?.[0];
    const employer = project?.employment.find((job) => job.id === jobId)?.employer;
    return employer ? `Проект: ${employer}` : "Проект без привязки";
  }
  function issueLabel(issue: NonNullable<typeof coverage>["warnings"][number]): string {
    const target = project?.views.find((item) => item.id === issue.blockId);
    const indexForJob = (id: string): string => {
      const index = project?.employment.findIndex((item) => item.id === id) ?? -1;
      return index < 0 ? "Раздел работы" : `Работа ${index + 1}`;
    };
    if (target) {
      if (target.kind !== "job_prose") return titles[target.kind];
      const jobId = Object.entries(state.presentation?.jobProseBlocks ?? {})
        .find(([, blockId]) => blockId === target.id)?.[0];
      return jobId ? indexForJob(jobId) : "Раздел работы";
    }
    const job = project?.employment.find((item) => item.id === issue.jobId ||
      item.id === project.facts.find((fact) => fact.id === issue.factId)?.jobId);
    if (job) return indexForJob(job.id);
    const fact = project?.facts.find((item) => item.id === issue.factId);
    if (issue.code === "TEXT_MEANING" && fact?.kind === "text" && fact.jobId === null) {
      if (fact.value.text.trim() === state.presentation?.name.trim()) return "Имя кандидата";
      if (fact.value.text.trim() === state.presentation?.title.trim()) return "Должность";
    }
    if (fact) return fact.kind === "metric" ? "Метрика" : fact.kind === "leadership" ? "Руководство" :
      fact.kind === "technology" ? "Навык" : "Факт";
    return issue.sourceId ? "Исходный фрагмент" : "Документ";
  }
  return <div className="min-h-screen bg-surface text-content">
    <header className="flex flex-wrap items-center gap-4 border-b border-outline bg-panel px-6 py-4">
      <div className="font-bold leading-tight">FoldCV<small className="block text-xs font-normal tracking-wide text-muted">ЛОКАЛЬНЫЙ РЕДАКТОР РЕЗЮМЕ</small></div>
      <span className="rounded bg-soft px-2 py-1 text-xs text-accent">На вашем компьютере</span>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <span aria-live="polite" className="text-sm text-muted">{unsaved ? `Есть несохранённые изменения${unapplied ? " · ввод не применён" : ""}` : "Новый проект"}</span>
        <button type="button" onClick={() => void saveArchive()} className={control}>Сохранить проект</button>
        <label className={control}>Открыть .cvproject<input aria-label="Открыть .cvproject" className="sr-only" type="file" accept=".cvproject,application/zip" onChange={(event) => {
          void chooseArchive(event.target.files?.[0]); event.target.value = "";
        }} /></label>
        <label className="flex items-center gap-2 text-sm">Тема <select aria-label="Тема" className={field} value={mode} onChange={(event) => { if (isThemeMode(event.target.value)) changeTheme(event.target.value); }}><option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option></select></label>
      </div>
    </header>
    {saveMessage && <p role="status" className="border-b border-outline px-6 py-2 text-sm">{saveMessage}</p>}
    {openError && <p role="alert" className="border-b border-outline px-6 py-2 text-sm text-danger">{openError}</p>}
    {replacement && <div role="dialog" aria-label="Заменить текущий проект" className="border-b border-outline bg-panel px-6 py-3 text-sm">
      <p>Открыть выбранный проект и заменить текущие данные в памяти?</p>
      <div className="mt-2 flex gap-2"><button type="button" className={primary} onClick={() => installArchive(replacement)}>Заменить проект</button>
        <button type="button" className={control} onClick={() => setReplacement(null)}>Оставить текущий</button></div></div>}
    <p className="border-b border-outline px-6 py-2 text-xs text-muted">Локальный импорт по выбору файла · вымышленный пример отдельно · обновление PDF по кнопке</p>
    <nav aria-label="Этапы работы" className="flex flex-wrap gap-2 border-b border-outline px-6 py-3">
      {(["import", "editor", "export"] as const).map((stage, index) => <button key={stage} type="button" disabled={stage !== "import" && !project} aria-current={state.stage === stage ? "step" : undefined} onClick={() => send({ type: "stage", stage })} className={state.stage === stage ? primary : control}>{index + 1}. {stage === "import" ? "Загрузка" : stage === "editor" ? "Редактор" : "Выгрузка"}</button>)}
    </nav>
    <aside className="mx-auto max-w-5xl px-6 pt-4"><div className="ml-auto max-w-md"><ConnectionPanel /></div></aside>
    {state.stage === "import" && <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-2 text-2xl font-semibold">Из исходника — в готовое резюме</h1>
      <p className="mb-6 text-muted">Выберите исходник для локального извлечения и проверки. Вымышленный пример открывает отдельный редактор.</p>
      {legacy && <section className="mb-5 rounded border border-outline bg-panel p-4">
        <h2 className="font-semibold">Экспериментальный архив v2</h2>
        <p className="mt-1 text-sm">Старый исходник, фрагменты и решения сохранены. Извлечение по кнопке выполняется локально без генерации текста.</p>
        <button type="button" className={`${control} mt-3`} onClick={() => void importWorkflow.file(
          new File([Uint8Array.from(legacy.originalBytes)], legacy.originalName))}>Проверить исходный файл локально</button>
        <details className="mt-3"><summary>Показать старые фрагменты и решения</summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify({
            units: legacy.archive.units, classifications: legacy.archive.classifications,
            jobs: legacy.archive.jobs, global_technologies: legacy.archive.global_technologies }, null, 2)}</pre></details>
      </section>}
      <div>
        {!project ? <ImportPanel state={importState} workflow={importWorkflow} text={state.sourceText}
          onText={(text) => send({ type: "sourceText", text })} exampleDisabled={importState.entries.length > 0 || importState.pending}
          onExample={() => { importWorkflow.clear(); factWorkflow.clear(); clearArchiveOwners();
            send({ type: "loadExample", loadId: crypto.randomUUID() }); }} />
          : <section className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 text-lg font-semibold">{state.working ? "Открыт черновик" : isExample ? "Открыт вымышленный пример" : "Открыт проект из архива"}</h2>
            <p className="text-sm text-muted">Новый импорт доступен после явного закрытия текущего проекта. Текущие правки не будут перенесены.</p>
            {!closeProjectPrompt ? <button type="button" className={`${control} mt-4`} onClick={() => setCloseProjectPrompt(true)}>{isExample ? "Закрыть пример и перейти к импорту" : "Закрыть проект и перейти к импорту"}</button>
              : <div className="mt-4 space-y-2"><p role="alert" className="text-sm text-danger">Несохранённые правки {isExample ? "примера" : "проекта"} будут удалены.</p>
                <div className="flex gap-2"><button type="button" className={control} onClick={() => { importWorkflow.clear(); factWorkflow.clear(); clearArchiveOwners();
                  send({ type: "resetProject" }); setCloseProjectPrompt(false); }}>Подтвердить закрытие</button>
                  <button type="button" className={control} onClick={() => setCloseProjectPrompt(false)}>{isExample ? "Оставить пример" : "Оставить проект"}</button></div></div>}
          </section>}
      </div>
      {!project && importState.entries.length > 0 && <><FactPanel key={archiveEpoch} view={factView} workflow={factWorkflow} sources={importState.entries}
        onOpen={(manual) => { draftWorkflow.cancel(); openImported(manual); }}
        onDraft={draftReady ? draftImported : undefined} draftView={draftView}
        onCancelDraft={() => draftWorkflow.cancel()} onManualChange={() => draftWorkflow.cancel()}
        initialManual={manualForm} onManualInput={(value) => { manualRef.current = value; setManualForm(value); }}
        initialAssertion={assertionDraft} initialEdits={factEdits}
        onLocalDraft={(assertion, edits) => { setAssertionDraft(assertion); setFactEdits(edits); }} />
        {openError && <p role="alert" className="mt-3 text-danger">{openError}</p>}</>}
    </main>}
    {state.stage === "editor" && project && !state.presentation && <section className="mx-auto max-w-5xl p-6">
      <h2 className="text-lg font-semibold">Данные для архива v3</h2>
      <p className="mt-2 text-sm text-muted">В старом архиве нет имени, должности и привязки разделов к работам. Укажите их для локальной сборки PDF и DOCX.</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2"><label>Имя кандидата<input className={field} value={state.presentationDrafts.name ?? ""}
        onChange={(event) => send({ type: "presentationDraft", field: "name", text: event.target.value })} /></label>
        <label>Должность<input className={field} value={state.presentationDrafts.title ?? ""}
          onChange={(event) => send({ type: "presentationDraft", field: "title", text: event.target.value })} /></label>
        <label>Язык<select className={field} value={state.structuredDrafts["migration:language"] ?? ""}
          onChange={(event) => send({ type: "structuredDraft", key: "migration:language", text: event.target.value })}>
          <option value="">Выберите язык</option><option value="ru">Русский</option><option value="en">English</option>
          <option value="mixed">Смешанный</option></select></label></div>
      {project.employment.map((job) => <label key={job.id} className="mt-3 block">{job.employer} · {job.role}
        <select className={field} value={state.structuredDrafts[`migration:job:${job.id}`] ?? ""}
          onChange={(event) => send({ type: "structuredDraft", key: `migration:job:${job.id}`, text: event.target.value })}>
          <option value="">Выберите раздел работы</option>{project.views.filter((item) => item.kind === "job_prose").map((item) =>
            <option key={item.id} value={item.id}>{item.state.text.slice(0, 100) || item.id}</option>)}</select></label>)}
      {state.errors.migration && <p role="alert" className="mt-2 text-danger">{state.errors.migration}</p>}
      <button type="button" className={`${primary} mt-4`} onClick={() => {
        const value = state.structuredDrafts["migration:language"];
        if (value === "ru" || value === "en" || value === "mixed") send({ type: "presentationMigrate", language: value });
      }}>Применить данные</button>
    </section>}
    {state.stage === "editor" && project && block && <main className="grid min-w-0 xl:grid-cols-[200px_minmax(320px,1fr)_minmax(350px,1fr)]">
      <aside className="border-b border-outline p-4 xl:border-b-0 xl:border-r"><h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Разделы резюме</h2>
        <div className="flex flex-wrap gap-1 xl:block">{project.views.map((item) => <button type="button" key={item.id} onClick={() => send({ type: "select", id: item.id })} aria-current={item.id === block.id ? "true" : undefined} className={`w-full rounded px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-accent ${item.id === block.id ? "bg-soft text-accent" : "hover:bg-soft"}`}>{blockTitle(item)}<small className="block text-xs text-muted">{!item.visible ? "Скрыт" : item.status === "stale" ? "Нужно проверить" : item.status === "proposed" ? "Предложено · требует проверки" : "Готово к проверке"}</small></button>)}</div>
        <div className="mt-5 border-t border-outline pt-4 text-sm"><strong>Проверка</strong><p className="mt-1 text-muted">{reviewCount} пунктов проверки · {staleCount} устаревших блоков</p></div>
      </aside>
      <section aria-label="Редактор блока" className="min-w-0 border-b border-outline bg-panel p-5 xl:border-b-0 xl:border-r xl:p-7">
        <p className="mb-1 text-xs uppercase tracking-wide text-muted">{state.working?.draft ? "Черновик из импорта · предложение требует проверки" : state.working ? "Дословный черновик из импорта" : isExample ? "Вымышленный пример" : "Проект из архива"} · редакция {project.revision}</p>
        {state.presentation && <div className="mb-5 grid gap-3 rounded border border-outline p-3 sm:grid-cols-2">
          {(["name", "title"] as const).map((key) => <div key={key}><label htmlFor={`candidate-${key}`} className="mb-1 block text-sm font-semibold">{key === "name" ? "Имя кандидата" : "Должность"}</label>
            <input id={`candidate-${key}`} className={field} aria-invalid={Boolean(state.errors[key])} value={state.presentationDrafts[key] ?? state.presentation?.[key] ?? ""} onChange={(event) => send({ type: "presentationDraft", field: key, text: event.target.value })} />
            {state.errors[key] && <p role="alert" className="text-sm text-danger">{state.errors[key]}</p>}
            <div className="mt-1 flex gap-2"><button type="button" className={control} onClick={() => send({ type: "presentationApply", field: key })}>Применить {key === "name" ? "имя" : "должность"}</button><button type="button" className={control} onClick={() => send({ type: "presentationCancel", field: key })}>Отменить {key === "name" ? "имя" : "должность"}</button></div>
          </div>)}
          <label className="text-sm">Язык исходника<select className={field} value={state.presentation.sourceLanguage} onChange={(event) => { const value = event.target.value; if (value === "ru" || value === "en" || value === "mixed") send({ type: "presentationLanguage", language: value }); }}><option value="ru">Русский</option><option value="en">Английский</option><option value="mixed">Смешанный</option></select></label>
          <button type="button" disabled={!state.presentationUndo} className={control} onClick={() => send({ type: "presentationUndo" })}>Отменить данные кандидата</button>
        </div>}
        <StructuredFields state={state} send={send} />
        <div className="flex flex-wrap items-start justify-between gap-2"><h1 className="text-2xl font-semibold">{blockTitle(block)}</h1><span className="rounded bg-soft px-2 py-1 text-xs text-accent">{block.state.locked ? "Правка закреплена" : "Черновик"}</span></div>
        <div className="my-5 flex flex-wrap gap-2"><button type="button" onClick={() => send({ type: "lock", id: block.id })} className={control}>{block.state.locked ? "Снять закрепление" : "Закрепить"}</button><button type="button" onClick={() => send({ type: "visible", id: block.id })} className={control}>{block.visible ? "Скрыть раздел" : "Показать раздел"}</button><button type="button" disabled={!state.undo[block.id]} onClick={() => send({ type: "undo", id: block.id })} className={control}>Отменить правку</button></div>
        <RewriteControls state={state} block={block} view={rewriteView} ready={rewriteReady}
          instruction={rewriteInstruction} onInstruction={(value) => { setRewriteInstruction(value); rewriteWorkflow.cancel(); }}
          onRequest={rewriteBlock} onCancel={() => rewriteWorkflow.cancel()} unapplied={unapplied} send={send} />
        <label htmlFor="block-text" className="mb-2 block font-semibold">Текст блока</label><textarea id="block-text" disabled={!["profile", "job_prose", "education"].includes(block.kind)} aria-invalid={Boolean(state.errors[block.id])} aria-describedby={state.errors[block.id] ? "block-error" : undefined} className={`${field} min-h-44`} value={draftFor(state, block)} onChange={(event) => send({ type: "draft", id: block.id, text: event.target.value })} />
        {!["profile", "job_prose", "education"].includes(block.kind) && <p className="mt-1 text-sm text-muted">Этот раздел собирается из фактов и каталога. Редактирование текста пока недоступно.</p>}
        {state.errors[block.id] && <p id="block-error" role="alert" className="mt-1 text-sm text-danger">{state.errors[block.id]}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2"><button type="button" disabled={!["profile", "job_prose", "education"].includes(block.kind)} className={primary} onClick={() => send({ type: "apply", id: block.id })}>Применить правку</button><button type="button" disabled={!["profile", "job_prose", "education"].includes(block.kind)} className={control} onClick={() => send({ type: "cancel", id: block.id })}>Отменить ввод</button><span className="text-xs text-muted">{draftFor(state, block) !== block.state.text ? "Ввод не применён" : "Текст принят"}</span></div>
        {block.status === "stale" && <div className="mt-4 border-l-4 border-danger bg-soft p-3 text-sm"><p role="alert">Связанный факт изменён. Проверьте этот блок перед использованием.</p>
          <button type="button" className={`${control} mt-2`} disabled={draftFor(state, block) !== block.state.text}
            onClick={reconcileBlock}>Проверил факты, оставить текст</button></div>}
        <div className="mt-6 border-t border-outline pt-4"><h2 className="mb-2 font-semibold">На чём основан блок</h2>
          {relatedFacts.length === 0 ? <p className="text-sm text-muted">Связанные факты пока не указаны.</p> : relatedFacts.map((fact) => { const editable = editableFactValue(fact); return <div key={fact.id} className="mb-3 rounded border border-outline p-3 text-sm"><strong className="block">{fact.id}</strong><span className="text-muted">{factText(fact)} · {fact.origin === "user" ? "внесено пользователем" : "связано с исходником"}</span>{fact.kind === "technology" && <div className="mt-2"><label htmlFor={`fact-${fact.id}`} className="mb-1 block">Технология из каталога</label>
            <select id={`fact-${fact.id}`} className={field} value={state.factDrafts[fact.id] ?? fact.value.canonicalId}
              onChange={(event) => send({ type: "factDraft", id: fact.id, text: event.target.value })}>
              {!catalog.entries.some((item) => item.canonicalId === fact.value.canonicalId) && <option value={fact.value.canonicalId}>{fact.value.display}</option>}
              {catalog.entries.map((item) => <option key={item.canonicalId} value={item.canonicalId}>{item.aliases[0] ?? item.canonicalId}</option>)}
            </select>{state.errors[fact.id] && <p role="alert" className="mt-1 text-danger">{state.errors[fact.id]}</p>}
            <div className="mt-2 flex gap-2"><button type="button" className={control} onClick={() => send({ type: "fact", id: fact.id,
              value: state.factDrafts[fact.id] ?? fact.value.canonicalId })}>Применить технологию</button>
              <button type="button" className={control} onClick={() => send({ type: "cancelFact", id: fact.id })}>Отменить ввод</button></div></div>}
            {fact.kind !== "technology" && editable !== null && <div className="mt-2"><label htmlFor={`fact-${fact.id}`} className="mb-1 block">{state.working && fact.origin === "source" ? "Ваше исправление текстом" : "Значение факта"}</label><input id={`fact-${fact.id}`} className={field} value={state.factDrafts[fact.id] ?? editable} onChange={(event) => send({ type: "factDraft", id: fact.id, text: event.target.value })} />{state.working && fact.origin === "source" && <p className="mt-1 text-xs text-muted">Исходный факт сохранится; исправление будет вашим текстовым утверждением.</p>}{state.errors[fact.id] && <p role="alert" className="mt-1 text-danger">{state.errors[fact.id]}</p>}<div className="mt-2 flex gap-2"><button type="button" className={control} onClick={() => send({ type: "fact", id: fact.id, value: state.factDrafts[fact.id] ?? editable })}>Применить факт</button><button type="button" className={control} onClick={() => send({ type: "cancelFact", id: fact.id })}>Отменить ввод факта</button></div></div>}</div>; })}
          <button type="button" className={control} onClick={() => send({ type: "panel", panel: "sources" })}>Показать источники</button>
        </div>
        <div className="mt-6 border-t border-outline pt-4"><button type="button" className={control} disabled={block.status === "stale"} onClick={() => send({ type: "review", id: block.id })}>{isReviewed ? "Снять отметку проверки" : "Отметить блок проверенным"}</button></div>
      </section>
      <aside className="min-w-0 bg-soft p-5"><Tabs.Root value={state.panel} onValueChange={(value) => { if (isPanel(value)) send({ type: "panel", panel: value }); }}><Tabs.List aria-label="Панель просмотра" className="mb-3 flex flex-wrap gap-2">{(["preview", "sources", "checks"] as const).map((panel) => <Tabs.Trigger key={panel} value={panel} className={`${control} data-[state=active]:border-accent data-[state=active]:text-accent`}>{panel === "preview" ? "Превью" : panel === "sources" ? "Источники" : "Проверки"}</Tabs.Trigger>)}</Tabs.List>
        <Tabs.Content value="preview" className="rounded border border-outline bg-panel p-5"><div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm"><span>{preview.status === "ready" ? `PDF готов · редакция ${preview.artifact?.request.baseRevision}` : preview.artifact ? `PDF устарел · редакция ${preview.artifact.request.baseRevision}${preview.status === "rendering" ? " · сборка новой версии…" : ""}` : preview.status === "rendering" ? "Сборка PDF…" : "PDF ещё не собран"}</span><button type="button" className={primary} onClick={() => refreshPreview()}>Обновить PDF</button></div>
          {unapplied && <p role="status" className="mb-2 text-sm text-danger">Есть неприменённый ввод. Примените или отмените его перед обновлением PDF.</p>}
          {preview.error && <p role="alert" className="mb-2 text-sm text-danger">{preview.error}</p>}
          {pdfUrl ? <iframe title="Превью PDF" src={pdfUrl} className="h-[65vh] min-h-96 w-full border border-outline bg-surface" /> : <p className="py-12 text-center text-muted">Нажмите «Обновить PDF», чтобы увидеть документ.</p>}
        </Tabs.Content>
        <Tabs.Content value="sources" className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 font-semibold">Связанные фрагменты исходника</h2>
          {focusedSource && <blockquote id={`source-${focusedSource.source.id}-${focusedSource.unit.id}`}
            className="mb-3 whitespace-pre-wrap break-words border-l-2 border-accent bg-surface p-3 text-sm">
            {focusedSource.source.overlays.find((item) => item.unitId === focusedSource.unit.id)?.text ?? focusedSource.unit.text}
          </blockquote>}
          {relatedUnits.length ? relatedUnits.filter((unit) => unit !== focusedSource?.unit).map((unit) =>
            <blockquote key={unit.id} className="mb-3 whitespace-pre-wrap break-words border-l-2 border-outline bg-surface p-3 text-sm">{unit.text}</blockquote>) :
            !focusedSource && <p className="text-sm text-muted">Для этого раздела нет связанного фрагмента.</p>}
          {state.working && <WorkingSources working={state.working} focusedUnit={focusedUnit} />}
          <p className="mt-4 text-xs text-muted">Исходный текст неизменен; правки фактов хранятся отдельно в памяти вкладки.</p></Tabs.Content>
        <Tabs.Content value="checks" className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 font-semibold">Проверки</h2><ul className="list-disc space-y-2 pl-5 text-sm"><li>{reviewCount} пунктов проверки</li><li>{staleCount} блоков требуют повторной проверки</li><li>{isReviewed ? "Выбранный блок отмечен проверенным" : "Выбранный блок ещё не отмечен проверенным"}</li>{state.workingIssues.map((issue, index) => <li key={index}>{issue}</li>)}</ul><CoveragePanel state={state} send={send} openSource={openSource} /><p className="mt-4 text-xs text-muted">Дословный черновик требует проверки смысла. Связь с источником не доказывает точность формулировки.</p></Tabs.Content>
      </Tabs.Root></aside>
    </main>}
    {state.stage === "export" && <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-2 text-2xl font-semibold">Документы и проект для следующего раза</h1>
      <p className="mb-5 text-muted">PDF и DOCX скачиваются из одной проверенной сборки. Проект сохраняется отдельно по кнопке.</p>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">PDF</h2>
          <button type="button" disabled={!readiness.allowed} onClick={() => refreshPreview("pdf")}
            className={`${control} mt-4`}>{canExport ? "Скачать PDF" : "Собрать и скачать PDF"}</button></div>
        <div className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">DOCX</h2>
          <button type="button" disabled={!readiness.allowed} onClick={() => refreshPreview("docx")}
            className={`${control} mt-4`}>{canExport ? "Скачать DOCX" : "Собрать и скачать DOCX"}</button></div>
        <div className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">Проект .cvproject</h2>
          <button type="button" onClick={() => void saveArchive()} className={`${control} mt-4`}>Скачать проект</button></div>
      </div>
      <div aria-live="polite" aria-busy={preview.status === "rendering"} className="mt-4 text-sm">
        {preview.status === "rendering" && <p role="status">Сборка документов…</p>}
        {preview.error && <p role="alert" className="text-danger">{preview.error}</p>}
      </div>
      {readiness.pendingInput && <p role="alert" className="mt-4 text-sm text-danger">Есть неприменённый ввод. Примените или отмените его перед выгрузкой документов.</p>}
      {(readiness.blockers.length > 0 || readiness.unacknowledged.length > 0) &&
        <section className="mt-5 rounded border border-outline bg-panel p-4 text-sm">
          <h2 className="font-semibold">Перед выгрузкой документов</h2>
          <p className="mt-1">{readiness.blockers.length} препятствий · {readiness.unacknowledged.length} предупреждений ждут проверки.</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {[...readiness.blockers, ...readiness.unacknowledged].slice(0, 6).map((issue) =>
              <li key={issue.id}>{issueLabel(issue)}: {issue.message}</li>)}
          </ul>
          {readiness.blockers.length + readiness.unacknowledged.length > 6 &&
            <p className="mt-2 text-muted">Ещё {readiness.blockers.length + readiness.unacknowledged.length - 6} пунктов в проверках.</p>}
          <button type="button" className={`${control} mt-3`} onClick={() => {
            send({ type: "stage", stage: "editor" }); send({ type: "panel", panel: "checks" });
          }}>Открыть проверки</button>
        </section>}
      {coverage?.warnings.some((issue) => issue.acknowledged) &&
        <details className="mt-5 rounded border border-outline bg-panel p-4 text-sm">
          <summary className="cursor-pointer font-semibold">Оставшиеся признанные неоднозначности · {coverage.warnings.filter((issue) => issue.acknowledged).length}</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">{coverage.warnings.filter((issue) => issue.acknowledged).map((issue) =>
            <li key={issue.id}>{issueLabel(issue)}: {issue.message}</li>)}</ul>
        </details>}
      {project && <p className="mt-5 text-sm text-muted">Редакция {project.revision} · {canExport ? "PDF готов" : "актуального PDF нет"} · {reviewCount} пунктов проверки</p>}
    </main>}
    <footer className="flex flex-wrap gap-5 border-t border-outline bg-panel px-6 py-3 text-xs text-muted"><span>Проект в памяти вкладки</span><span>Завершённых текстовых операций в этой сессии: {draftView.completed + rewriteView.completed}</span><span>Ручное редактирование: 0 запросов</span></footer>
  </div>;
}
