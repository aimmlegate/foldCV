import * as Tabs from "@radix-ui/react-tabs";
import { useEffect, useReducer, useState } from "react";
import type { Block, Facts } from "../contracts/generated/project";
import { draftFor, editableFactValue, editorReducer, hasUnappliedDraft, initialEditorState, renderStale, selectedBlock } from "../editor/state";
import type { Panel } from "../editor/state";

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
  const project = state.project;
  const block = selectedBlock(state);
  const unapplied = hasUnappliedDraft(state);
  const unsaved = state.dirty || unapplied;
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
    <p className="border-b border-outline px-6 py-2 text-xs text-muted">Интерактивный редактор · вымышленные данные загружаются только по кнопке · документы пока недоступны</p>
    <nav aria-label="Этапы работы" className="flex flex-wrap gap-2 border-b border-outline px-6 py-3">
      {(["import", "editor", "export"] as const).map((stage, index) => <button key={stage} type="button" disabled={stage !== "import" && !project} aria-current={state.stage === stage ? "step" : undefined} onClick={() => dispatch({ type: "stage", stage })} className={state.stage === stage ? primary : control}>{index + 1}. {stage === "import" ? "Загрузка" : stage === "editor" ? "Редактор" : "Выгрузка"}</button>)}
    </nav>
    {state.stage === "import" && <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-2 text-2xl font-semibold">Из исходника — в готовое резюме</h1>
      <p className="mb-6 text-muted">Локальный импорт появится позже. Сейчас можно проверить редактирование на вымышленном примере.</p>
      <div className="grid gap-6 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 text-lg font-semibold">Исходное резюме</h2>
          <label htmlFor="source-text" className="mb-2 block">Вставьте текст резюме</label>
          <textarea id="source-text" className={`${field} min-h-44`} value={state.sourceText} onChange={(event) => dispatch({ type: "sourceText", text: event.target.value })} />
          <p className="my-3 text-sm text-muted">Введённый текст пока остаётся только в этой вкладке; обработка недоступна.</p>
          <div className="flex flex-wrap gap-2"><button type="button" disabled className={control}>Обработать текст</button><button type="button" disabled={Boolean(project)} onClick={() => dispatch({ type: "loadExample" })} className={primary}>Загрузить вымышленный пример</button></div>
          {project && <p className="mt-2 text-sm text-muted">Пример уже открыт. Повторная загрузка недоступна, чтобы сохранить текущие правки.</p>}
          <p className="mt-3 text-xs text-muted">Выбор PDF, DOCX и открытие .cvproject появятся после подключения импорта и архива.</p>
        </section>
        <aside className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 text-lg font-semibold">Подключение</h2><p role="status" className="text-sm text-danger">Генерация недоступна: профиль CLI не прошёл проверку безопасности.</p><p className="mt-4 text-sm text-muted">Шаблон: Generic · основной. Проверка подключения появится позже.</p></aside>
      </div>
    </main>}
    {state.stage === "editor" && project && block && <main className="grid min-w-0 xl:grid-cols-[200px_minmax(320px,1fr)_minmax(350px,1fr)]">
      <aside className="border-b border-outline p-4 xl:border-b-0 xl:border-r"><h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Разделы резюме</h2>
        <div className="flex flex-wrap gap-1 xl:block">{project.views.map((item) => <button type="button" key={item.id} onClick={() => dispatch({ type: "select", id: item.id })} aria-current={item.id === block.id ? "true" : undefined} className={`w-full rounded px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-accent ${item.id === block.id ? "bg-soft text-accent" : "hover:bg-soft"}`}>{titles[item.kind]}<small className="block text-xs text-muted">{!item.visible ? "Скрыт" : item.status === "stale" ? "Нужно проверить" : "Готово к проверке"}</small></button>)}</div>
        <div className="mt-5 border-t border-outline pt-4 text-sm"><strong>Проверка</strong><p className="mt-1 text-muted">{reviewCount} вопросов · {staleCount} устаревших блоков</p></div>
      </aside>
      <section aria-label="Редактор блока" className="min-w-0 border-b border-outline bg-panel p-5 xl:border-b-0 xl:border-r xl:p-7">
        <p className="mb-1 text-xs uppercase tracking-wide text-muted">Вымышленный пример · редакция {project.revision}</p>
        <div className="flex flex-wrap items-start justify-between gap-2"><h1 className="text-2xl font-semibold">{titles[block.kind]}</h1><span className="rounded bg-soft px-2 py-1 text-xs text-accent">{block.state.locked ? "Правка закреплена" : "Черновик"}</span></div>
        <div className="my-5 flex flex-wrap gap-2"><button type="button" disabled title="Генерация блока появится после подключения CLI" className={primary}>Перегенерировать блок</button><button type="button" onClick={() => dispatch({ type: "lock", id: block.id })} className={control}>{block.state.locked ? "Снять закрепление" : "Закрепить"}</button><button type="button" onClick={() => dispatch({ type: "visible", id: block.id })} className={control}>{block.visible ? "Скрыть раздел" : "Показать раздел"}</button><button type="button" disabled={!state.undo[block.id]} onClick={() => dispatch({ type: "undo", id: block.id })} className={control}>Отменить правку</button></div>
        <label htmlFor="block-text" className="mb-2 block font-semibold">Текст блока</label><textarea id="block-text" aria-invalid={Boolean(state.errors[block.id])} aria-describedby={state.errors[block.id] ? "block-error" : undefined} className={`${field} min-h-44`} value={draftFor(state, block)} onChange={(event) => dispatch({ type: "draft", id: block.id, text: event.target.value })} />
        {state.errors[block.id] && <p id="block-error" role="alert" className="mt-1 text-sm text-danger">{state.errors[block.id]}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2"><button type="button" className={primary} onClick={() => dispatch({ type: "apply", id: block.id })}>Применить правку</button><button type="button" className={control} onClick={() => dispatch({ type: "cancel", id: block.id })}>Отменить ввод</button><span className="text-xs text-muted">{draftFor(state, block) !== block.state.text ? "Ввод не применён" : "Текст принят"}</span></div>
        {block.status === "stale" && <p role="alert" className="mt-4 border-l-4 border-danger bg-soft p-3 text-sm">Связанный факт изменён. Проверьте этот блок перед использованием.</p>}
        <div className="mt-6 border-t border-outline pt-4"><h2 className="mb-2 font-semibold">На чём основан блок</h2>
          {relatedFacts.length === 0 ? <p className="text-sm text-muted">Связанные факты пока не указаны.</p> : relatedFacts.map((fact) => { const editable = editableFactValue(fact); return <div key={fact.id} className="mb-3 rounded border border-outline p-3 text-sm"><strong className="block">{fact.id}</strong><span className="text-muted">{factText(fact)} · {fact.origin === "user" ? "внесено пользователем" : "связано с исходником"}</span>{editable !== null && <div className="mt-2"><label htmlFor={`fact-${fact.id}`} className="mb-1 block">Значение факта</label><input id={`fact-${fact.id}`} className={field} value={state.factDrafts[fact.id] ?? editable} onChange={(event) => dispatch({ type: "factDraft", id: fact.id, text: event.target.value })} />{state.errors[fact.id] && <p role="alert" className="mt-1 text-danger">{state.errors[fact.id]}</p>}<div className="mt-2 flex gap-2"><button type="button" className={control} onClick={() => dispatch({ type: "fact", id: fact.id, value: state.factDrafts[fact.id] ?? editable })}>Применить факт</button><button type="button" className={control} onClick={() => dispatch({ type: "cancelFact", id: fact.id })}>Отменить ввод факта</button></div></div>}{fact.kind === "technology" && <p className="mt-2 text-xs text-muted">Изменение технологии будет доступно после подключения выбора из каталога.</p>}</div>; })}
          <button type="button" className={control} onClick={() => dispatch({ type: "panel", panel: "sources" })}>Показать источники</button>
        </div>
        <div className="mt-6 border-t border-outline pt-4"><button type="button" className={control} disabled={block.status === "stale"} onClick={() => dispatch({ type: "review", id: block.id })}>{isReviewed ? "Снять отметку проверки" : "Отметить блок проверенным"}</button></div>
      </section>
      <aside className="min-w-0 bg-soft p-5"><Tabs.Root value={state.panel} onValueChange={(value) => { if (isPanel(value)) dispatch({ type: "panel", panel: value }); }}><Tabs.List aria-label="Панель просмотра" className="mb-3 flex flex-wrap gap-2">{(["preview", "sources", "checks"] as const).map((panel) => <Tabs.Trigger key={panel} value={panel} className={`${control} data-[state=active]:border-accent data-[state=active]:text-accent`}>{panel === "preview" ? "Превью" : panel === "sources" ? "Источники" : "Проверки"}</Tabs.Trigger>)}</Tabs.List>
        <Tabs.Content value="preview" className="rounded border border-outline bg-panel p-5"><div className="mb-4 flex flex-wrap justify-between gap-2 text-xs text-muted"><span>Текстовая схема · PDF пока недоступен</span><span>{renderStale(project) ? "Рендер устарел или отсутствует" : "Рендер готов"}</span></div><div className="border-b border-outline pb-3 font-semibold">Вымышленный кандидат <span className="float-right">/generic.</span></div><div className="mt-4 grid gap-4 sm:grid-cols-[100px_minmax(0,1fr)]"><div className="text-xs"><strong>Фокус</strong><p className="mt-2 whitespace-pre-wrap">{project.views.find((item) => item.kind === "focus" && item.visible)?.state.text ?? "—"}</p></div><div className="min-w-0 space-y-4 text-sm">{project.views.filter((item) => item.visible && item.kind !== "focus").map((item) => <section key={item.id}><h3 className="mb-1 border-b border-outline font-semibold">{titles[item.kind]}</h3><p className="whitespace-pre-wrap break-words">{item.state.text || "Раздел пуст"}</p></section>)}</div></div></Tabs.Content>
        <Tabs.Content value="sources" className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 font-semibold">Связанные фрагменты исходника</h2>{relatedUnits.length ? relatedUnits.map((unit) => <blockquote key={unit.id} className="mb-3 whitespace-pre-wrap break-words border-l-2 border-outline bg-surface p-3 text-sm">{unit.text}</blockquote>) : <p className="text-sm text-muted">Для этого раздела нет связанного фрагмента.</p>}<p className="mt-4 text-xs text-muted">Исходный текст неизменен; правки фактов хранятся отдельно в памяти вкладки.</p></Tabs.Content>
        <Tabs.Content value="checks" className="rounded border border-outline bg-panel p-5"><h2 className="mb-3 font-semibold">Проверки</h2><ul className="list-disc space-y-2 pl-5 text-sm"><li>{reviewCount} нерешённых вопросов в примере</li><li>{staleCount} блоков требуют повторной проверки</li><li>{isReviewed ? "Выбранный блок отмечен проверенным" : "Выбранный блок ещё не отмечен проверенным"}</li></ul><p className="mt-4 text-xs text-muted">Полная проверка покрытия появится позже. Связь с источником не доказывает точность формулировки.</p></Tabs.Content>
      </Tabs.Root></aside>
    </main>}
    {state.stage === "export" && <main className="mx-auto max-w-5xl p-6"><h1 className="mb-2 text-2xl font-semibold">Документы и проект для следующего раза</h1><p className="mb-5 text-muted">Выгрузка пока недоступна: сборка PDF/DOCX и сохранение .cvproject будут подключены позже.</p><div className="grid gap-4 md:grid-cols-3">{["PDF", "DOCX", "Проект .cvproject"].map((name) => <div key={name} className="rounded border border-outline bg-panel p-5"><h2 className="font-semibold">{name}</h2><button type="button" disabled className={`${control} mt-4`}>Скачать</button></div>)}</div>{project && <p className="mt-5 text-sm text-muted">Редакция {project.revision} · {renderStale(project) ? "актуального PDF нет" : "PDF готов"} · {reviewCount} нерешённых вопросов</p>}</main>}
    <footer className="flex flex-wrap gap-5 border-t border-outline bg-panel px-6 py-3 text-xs text-muted"><span>Проект в памяти вкладки</span><span>Текстовых операций в этой сессии: 0</span><span>Ручное редактирование: 0 запросов</span></footer>
  </div>;
}
