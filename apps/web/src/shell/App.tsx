import * as Tabs from "@radix-ui/react-tabs";
import { useEffect, useReducer, useRef, useState } from "react";
import type { Block, Facts } from "../contracts/generated/project";
import { draftFor, editableFactValue, editorReducer, hasUnappliedDraft, initialEditorState, selectedBlock } from "../editor/state";
import type { Panel } from "../editor/state";
import type { Action, EditorState } from "../editor/state";
import type { PrepareRequest } from "../contracts/generated/prepare_request";
import { PreviewWorkflow } from "../preview/workflow";
import type { PreviewState } from "../preview/workflow";
import { ImportPanel } from "../import/ImportPanel";
import { ImportWorkflow } from "../import/workflow";
import type { ImportState } from "../import/workflow";
import { ConnectionPanel } from "../connection/ConnectionPanel";

type ThemeMode = "light" | "dark" | "system";
const THEME_KEY = "foldcv-theme";
const control = "rounded border border-outline bg-panel px-3 py-2 text-content hover:bg-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50";
const primary = "rounded border border-accent bg-accent px-3 py-2 text-accent-contrast focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50";
const field = "w-full rounded border border-outline bg-surface p-3 text-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
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
  const [closeProjectPrompt, setCloseProjectPrompt] = useState(false);
  const workflowRef = useRef<PreviewWorkflow | null>(null);
  if (!workflowRef.current) workflowRef.current = new PreviewWorkflow(setPreview, (artifact, kind) => {
    const current = stateRef.current;
    if (!current.project || hasUnappliedDraft(current) || artifact.request.baseRevision !== current.project.revision) return;
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
    const invalidated = next.project !== previous.project || next.presentation !== previous.presentation ||
        action.type === "draft" || action.type === "factDraft" || action.type === "presentationDraft" ||
        action.type === "cancel" || action.type === "cancelFact" || action.type === "presentationCancel";
    if (invalidated) {
      workflow.invalidate();
      if (!hasUnappliedDraft(next) && next.project && next.presentation)
        workflow.restore({ project: next.project, presentation: next.presentation });
    }
    dispatch(action);
  }
  function refreshPreview(exportKind?: "pdf" | "docx") {
    const current = stateRef.current;
    if (!current.project || !current.presentation) return;
    if (hasUnappliedDraft(current)) {
      setPreview({ status: "error", artifact: preview.artifact,
        error: "Сначала примените или отмените введённые правки." });
      return;
    }
    const input: PrepareRequest = { project: current.project, presentation: current.presentation };
    workflow.request(input, exportKind);
  }
  const project = state.project;
  const block = selectedBlock(state);
  const unapplied = hasUnappliedDraft(state);
  const canExport = preview.status === "ready" && workflow.ready !== null && !unapplied &&
    workflow.ready.request.baseRevision === project?.revision;
  const unsaved = state.dirty || unapplied || importState.entries.length > 0;
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
  const reviewCount = project?.review.decisions.filter((decision) => decision.disposition === "unresolved").length ?? 0;
  const staleCount = project?.views.filter((view) => view.status === "stale").length ?? 0;
  const isReviewed = Boolean(block && project?.review.decisions.some((decision) => decision.targetKind === "block" && decision.targetId === block.id && decision.targetRevision === block.revision));
  const relatedFacts = block ? project?.facts.filter((fact) => block.state.factIds.includes(fact.id)) ?? [] : [];
  const relatedUnits = block ? project?.sources.flatMap((source) => source.units.filter((unit) => unit.representedFactIds.some((id) => block.state.factIds.includes(id)))) ?? [] : [];
  function blockTitle(item: Block): string {
    if (item.kind !== "job_prose") return titles[item.kind];
    const jobId = Object.entries(state.presentation?.jobProseBlocks ?? {}).find(([, blockId]) => blockId === item.id)?.[0];
    const employer = project?.employment.find((job) => job.id === jobId)?.employer;
    return employer ? `Проект: ${employer}` : "Проект без привязки";
  }
  return <div className="min-h-screen bg-surface text-content">
    <header className="flex flex-wrap items-center gap-4 border-b border-outline bg-panel px-6 py-4">
      <div className="font-bold leading-tight">FoldCV<small className="block text-xs font-normal tracking-wide text-muted">ЛОКАЛЬНЫЙ РЕДАКТОР РЕЗЮМЕ</small></div>
      <span className="rounded bg-soft px-2 py-1 text-xs text-accent">На вашем компьютере</span>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <span aria-live="polite" className="text-sm text-muted">{unsaved ? `Есть несохранённые изменения${unapplied ? " · ввод не применён" : ""}` : "Новый проект"}</span>
        <button type="button" disabled title="Сохранение проекта появится позже" className={control}>Сохранить проект</button>
        <label className="flex items-center gap-2 text-sm">Тема <select aria-label="Тема" className={field} value={mode} onChange={(event) => { if (isThemeMode(event.target.value)) changeTheme(event.target.value); }}><option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option></select></label>
      </div>
    </header>
    <p className="border-b border-outline px-6 py-2 text-xs text-muted">Локальный импорт по выбору файла · вымышленный пример отдельно · обновление PDF по кнопке</p>
    <nav aria-label="Этапы работы" className="flex flex-wrap gap-2 border-b border-outline px-6 py-3">
      {(["import", "editor", "export"] as const).map((stage, index) => <button key={stage} type="button" disabled={stage !== "import" && !project} aria-current={state.stage === stage ? "step" : undefined} onClick={() => send({ type: "stage", stage })} className={state.stage === stage ? primary : control}>{index + 1}. {stage === "import" ? "Загрузка" : stage === "editor" ? "Редактор" : "Выгрузка"}</button>)}
    </nav>
    <aside className="mx-auto max-w-5xl px-6 pt-4"><div className="ml-auto max-w-md"><ConnectionPanel /></div></aside>
    {state.stage === "import" && <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-2 text-2xl font-semibold">Из исходника — в готовое резюме</h1>
      <p className="mb-6 text-muted">Выберите исходник для локального извлечения и проверки. Вымышленный пример открывает отдельный редактор.</p>
      <div>
        {!project ? <ImportPanel state={importState} workflow={importWorkflow} text={state.sourceText}
          onText={(text) => send({ type: "sourceText", text })} exampleDisabled={importState.entries.length > 0 || importState.pending}
          onExample={() => { importWorkflow.clear(); send({ type: "loadExample" }); }} />
          : <section className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 text-lg font-semibold">Открыт вымышленный пример</h2>
            <p className="text-sm text-muted">Импорт отдельного источника доступен после закрытия примера. Текущие правки не будут перенесены.</p>
            {!closeProjectPrompt ? <button type="button" className={`${control} mt-4`} onClick={() => setCloseProjectPrompt(true)}>Закрыть пример и перейти к импорту</button>
              : <div className="mt-4 space-y-2"><p role="alert" className="text-sm text-danger">Несохранённые правки примера будут удалены.</p>
                <div className="flex gap-2"><button type="button" className={control} onClick={() => { importWorkflow.clear(); send({ type: "resetProject" }); setCloseProjectPrompt(false); }}>Подтвердить закрытие</button>
                  <button type="button" className={control} onClick={() => setCloseProjectPrompt(false)}>Оставить пример</button></div></div>}
          </section>}
      </div>
    </main>}
    {state.stage === "editor" && project && block && <main className="grid min-w-0 xl:grid-cols-[200px_minmax(320px,1fr)_minmax(350px,1fr)]">
      <aside className="border-b border-outline p-4 xl:border-b-0 xl:border-r"><h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Разделы резюме</h2>
        <div className="flex flex-wrap gap-1 xl:block">{project.views.map((item) => <button type="button" key={item.id} onClick={() => send({ type: "select", id: item.id })} aria-current={item.id === block.id ? "true" : undefined} className={`w-full rounded px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-accent ${item.id === block.id ? "bg-soft text-accent" : "hover:bg-soft"}`}>{blockTitle(item)}<small className="block text-xs text-muted">{!item.visible ? "Скрыт" : item.status === "stale" ? "Нужно проверить" : "Готово к проверке"}</small></button>)}</div>
        <div className="mt-5 border-t border-outline pt-4 text-sm"><strong>Проверка</strong><p className="mt-1 text-muted">{reviewCount} вопросов · {staleCount} устаревших блоков</p></div>
      </aside>
      <section aria-label="Редактор блока" className="min-w-0 border-b border-outline bg-panel p-5 xl:border-b-0 xl:border-r xl:p-7">
        <p className="mb-1 text-xs uppercase tracking-wide text-muted">Вымышленный пример · редакция {project.revision}</p>
        {state.presentation && <div className="mb-5 grid gap-3 rounded border border-outline p-3 sm:grid-cols-2">
          {(["name", "title"] as const).map((key) => <div key={key}><label htmlFor={`candidate-${key}`} className="mb-1 block text-sm font-semibold">{key === "name" ? "Имя кандидата" : "Должность"}</label>
            <input id={`candidate-${key}`} className={field} aria-invalid={Boolean(state.errors[key])} value={state.presentationDrafts[key] ?? state.presentation?.[key] ?? ""} onChange={(event) => send({ type: "presentationDraft", field: key, text: event.target.value })} />
            {state.errors[key] && <p role="alert" className="text-sm text-danger">{state.errors[key]}</p>}
            <div className="mt-1 flex gap-2"><button type="button" className={control} onClick={() => send({ type: "presentationApply", field: key })}>Применить {key === "name" ? "имя" : "должность"}</button><button type="button" className={control} onClick={() => send({ type: "presentationCancel", field: key })}>Отменить {key === "name" ? "имя" : "должность"}</button></div>
          </div>)}
          <label className="text-sm">Язык исходника<select className={field} value={state.presentation.sourceLanguage} onChange={(event) => { const value = event.target.value; if (value === "ru" || value === "en" || value === "mixed") send({ type: "presentationLanguage", language: value }); }}><option value="ru">Русский</option><option value="en">Английский</option><option value="mixed">Смешанный</option></select></label>
          <button type="button" disabled={!state.presentationUndo} className={control} onClick={() => send({ type: "presentationUndo" })}>Отменить данные кандидата</button>
        </div>}
        <div className="flex flex-wrap items-start justify-between gap-2"><h1 className="text-2xl font-semibold">{blockTitle(block)}</h1><span className="rounded bg-soft px-2 py-1 text-xs text-accent">{block.state.locked ? "Правка закреплена" : "Черновик"}</span></div>
        <div className="my-5 flex flex-wrap gap-2"><button type="button" disabled title="Генерация блока появится после подключения CLI" className={primary}>Перегенерировать блок</button><button type="button" onClick={() => send({ type: "lock", id: block.id })} className={control}>{block.state.locked ? "Снять закрепление" : "Закрепить"}</button><button type="button" onClick={() => send({ type: "visible", id: block.id })} className={control}>{block.visible ? "Скрыть раздел" : "Показать раздел"}</button><button type="button" disabled={!state.undo[block.id]} onClick={() => send({ type: "undo", id: block.id })} className={control}>Отменить правку</button></div>
        <label htmlFor="block-text" className="mb-2 block font-semibold">Текст блока</label><textarea id="block-text" disabled={!["profile", "job_prose", "education"].includes(block.kind)} aria-invalid={Boolean(state.errors[block.id])} aria-describedby={state.errors[block.id] ? "block-error" : undefined} className={`${field} min-h-44`} value={draftFor(state, block)} onChange={(event) => send({ type: "draft", id: block.id, text: event.target.value })} />
        {!["profile", "job_prose", "education"].includes(block.kind) && <p className="mt-1 text-sm text-muted">Этот раздел собирается из фактов и каталога. Редактирование текста пока недоступно.</p>}
        {state.errors[block.id] && <p id="block-error" role="alert" className="mt-1 text-sm text-danger">{state.errors[block.id]}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2"><button type="button" disabled={!["profile", "job_prose", "education"].includes(block.kind)} className={primary} onClick={() => send({ type: "apply", id: block.id })}>Применить правку</button><button type="button" disabled={!["profile", "job_prose", "education"].includes(block.kind)} className={control} onClick={() => send({ type: "cancel", id: block.id })}>Отменить ввод</button><span className="text-xs text-muted">{draftFor(state, block) !== block.state.text ? "Ввод не применён" : "Текст принят"}</span></div>
        {block.status === "stale" && <p role="alert" className="mt-4 border-l-4 border-danger bg-soft p-3 text-sm">Связанный факт изменён. Проверьте этот блок перед использованием.</p>}
        <div className="mt-6 border-t border-outline pt-4"><h2 className="mb-2 font-semibold">На чём основан блок</h2>
          {relatedFacts.length === 0 ? <p className="text-sm text-muted">Связанные факты пока не указаны.</p> : relatedFacts.map((fact) => { const editable = editableFactValue(fact); return <div key={fact.id} className="mb-3 rounded border border-outline p-3 text-sm"><strong className="block">{fact.id}</strong><span className="text-muted">{factText(fact)} · {fact.origin === "user" ? "внесено пользователем" : "связано с исходником"}</span>{editable !== null && <div className="mt-2"><label htmlFor={`fact-${fact.id}`} className="mb-1 block">Значение факта</label><input id={`fact-${fact.id}`} className={field} value={state.factDrafts[fact.id] ?? editable} onChange={(event) => send({ type: "factDraft", id: fact.id, text: event.target.value })} />{state.errors[fact.id] && <p role="alert" className="mt-1 text-danger">{state.errors[fact.id]}</p>}<div className="mt-2 flex gap-2"><button type="button" className={control} onClick={() => send({ type: "fact", id: fact.id, value: state.factDrafts[fact.id] ?? editable })}>Применить факт</button><button type="button" className={control} onClick={() => send({ type: "cancelFact", id: fact.id })}>Отменить ввод факта</button></div></div>}{fact.kind === "technology" && <p className="mt-2 text-xs text-muted">Изменение технологии будет доступно после подключения выбора из каталога.</p>}</div>; })}
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
        <Tabs.Content value="sources" className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 font-semibold">Связанные фрагменты исходника</h2>{relatedUnits.length ? relatedUnits.map((unit) => <blockquote key={unit.id} className="mb-3 whitespace-pre-wrap break-words border-l-2 border-outline bg-surface p-3 text-sm">{unit.text}</blockquote>) : <p className="text-sm text-muted">Для этого раздела нет связанного фрагмента.</p>}<p className="mt-4 text-xs text-muted">Исходный текст неизменен; правки фактов хранятся отдельно в памяти вкладки.</p></Tabs.Content>
        <Tabs.Content value="checks" className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 font-semibold">Проверки</h2><ul className="list-disc space-y-2 pl-5 text-sm"><li>{reviewCount} нерешённых вопросов в примере</li><li>{staleCount} блоков требуют повторной проверки</li><li>{isReviewed ? "Выбранный блок отмечен проверенным" : "Выбранный блок ещё не отмечен проверенным"}</li></ul><p className="mt-4 text-xs text-muted">Полная проверка покрытия появится позже. Связь с источником не доказывает точность формулировки.</p></Tabs.Content>
      </Tabs.Root></aside>
    </main>}
    {state.stage === "export" && <main className="mx-auto max-w-5xl p-6"><h1 className="mb-2 text-2xl font-semibold">Документы и проект для следующего раза</h1><p className="mb-5 text-muted">PDF и DOCX скачиваются из одной проверенной сборки. Если документ устарел, кнопка обновит превью перед скачиванием. Проект .cvproject появится позже.</p><div className="grid gap-4 md:grid-cols-3"><div className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">PDF</h2><button type="button" disabled={unapplied} onClick={() => refreshPreview("pdf")} className={`${control} mt-4`}>{canExport ? "Скачать PDF" : "Собрать и скачать PDF"}</button></div><div className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">DOCX</h2><button type="button" disabled={unapplied} onClick={() => refreshPreview("docx")} className={`${control} mt-4`}>{canExport ? "Скачать DOCX" : "Собрать и скачать DOCX"}</button></div><div className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">Проект .cvproject</h2><button type="button" disabled className={`${control} mt-4`}>Скачать проект</button></div></div><div aria-live="polite" aria-busy={preview.status === "rendering"} className="mt-4 text-sm">{preview.status === "rendering" && <p role="status">Сборка документов…</p>}{preview.error && <p role="alert" className="text-danger">{preview.error}</p>}</div>{project && <p className="mt-5 text-sm text-muted">Редакция {project.revision} · {canExport ? "PDF готов" : "актуального PDF нет"} · {reviewCount} нерешённых вопросов</p>}</main>}
    <footer className="flex flex-wrap gap-5 border-t border-outline bg-panel px-6 py-3 text-xs text-muted"><span>Проект в памяти вкладки</span><span>Текстовых операций в этой сессии: 0</span><span>Ручное редактирование: 0 запросов</span></footer>
  </div>;
}
