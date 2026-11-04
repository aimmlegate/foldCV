import * as Tabs from "@radix-ui/react-tabs";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { errorMessage } from "../../errors/messages";
import type { TemplateCatalog, TemplateEntry } from "../../projects/api";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { OperationStatus } from "../ui/OperationStatus";
import { deliverFile, deliveryMessage, type Delivery } from "../files/delivery";
import { checkTemplateConfig, createTemplate, deleteTemplate, problemLine, problemTab, readTemplateCatalog, readTemplateConfig, resetTemplateConfig,
  saveTemplateConfig, sectionTab, sectionTabs, setDefaultTemplate, topLevelSections, withState, type SectionTab, type TemplateConfigState,
  type TemplateProblem, type TemplateSave } from "./config";
import { downloadName, draftLabel, groupedCatalog, menuActions, rowNote, shownId, templateKind, unsaved, type MenuAction, type ShownTemplate } from "./studio";
import { TemplateToolbar } from "./TemplateToolbar";
import type { YamlEditorHandle } from "./YamlEditor";
import type { TemplateProposal } from "../../assistant/template";
import { applyProposal, type ApplyOutcome } from "./apply";
import { TemplateAssistant, type TemplateContext } from "./TemplateAssistant";
import { TemplateBranding } from "./TemplateBranding";

const YamlEditor = lazy(() => import("./YamlEditor"));
type Work = "loading" | "checking" | "saving" | "resetting" | "defaulting" | "adding" | "deleting" | "applying" | null;
type Outcome = "checked" | "saved" | "branded" | "reset" | "default" | "added" | "deleted" | null;
// Work the toolbar buttons do not show themselves goes to the status line.
const progress: Partial<Record<Exclude<Work, null>, string>> = { loading: "Загружаем шаблон", resetting: "Возвращаем встроенный шаблон",
  defaulting: "Делаем шаблон основным", adding: "Добавляем копию", deleting: "Удаляем шаблон", applying: "Применяем предложение" };

/** The templates screen: the list, the YAML of the shown template and the template assistant. New imports use these
 * templates; existing resumes keep their own captured version. */
export default function TemplatesScreen({ open, settings }: { open: boolean; settings: () => void }) {
  const [catalog, setCatalog] = useState<TemplateCatalog | null>(null);
  const [shown, setShown] = useState<ShownTemplate | null>(null);
  const [text, setText] = useState("");
  const [work, setWork] = useState<Work>("loading");
  const [problem, setProblem] = useState<TemplateProblem | null>(null);
  // A save refused for a taken revision offers the next free one instead of the bare refusal.
  const [offer, setOffer] = useState<TemplateProblem | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  // Check found no error, but the text's revision is saved with other content: Save will offer this one.
  const [nextRevision, setNextRevision] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false), [confirmDelete, setConfirmDelete] = useState(false);
  // The name of a copy; null while the dialog is closed.
  const [copyName, setCopyName] = useState<string | null>(null), [branding, setBranding] = useState(false);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  // Opening another template drops unsaved edits of the shown one, so it asks first.
  const [asking, setAsking] = useState(false);
  const answer = useRef<((open: boolean) => void) | null>(null);
  // The design part first: blocks, not the model's English prompt text at the top of the file.
  const [tab, setTab] = useState<SectionTab>("blocks");
  const yaml = useRef<YamlEditorHandle>(null), more = useRef<HTMLButtonElement>(null);
  // The assistant puts its toggle here, at the end of the tab row.
  const [assistantSlot, setAssistantSlot] = useState<HTMLElement | null>(null);
  const dirty = unsaved(shown, text), selected = shownId(shown), state = shown?.kind === "saved" ? shown.state : null;
  const draft = shown?.kind === "draft" ? shown : null;
  // The assistant reads and applies after renders: these hold what the editor shows now.
  const live = useRef({ shown, text });
  live.current = { shown, text };
  const names = useMemo(() => new Map(catalog?.templates.map(entry => [entry.id, entry.name]) ?? []), [catalog]);
  const present = useMemo(() => new Set(topLevelSections(text).map(section => sectionTab(section.key))), [text]);

  function begin(kind: Exclude<Work, null>) { setWork(kind); setFailure(null); setOutcome(null); setNextRevision(null); setDelivery(null); }
  async function run(kind: Exclude<Work, null>, task: () => Promise<void>) {
    begin(kind);
    try { await task(); } catch (error) { setFailure(error); } finally { setWork(null); }
  }
  function adopt(next: TemplateConfigState) { setShown({ kind: "saved", state: next }); setText(next.text); setProblem(null); }
  /** A problem opens the tab that holds its key, so its marked line shows. */
  function showProblem(value: TemplateProblem) { setTab(problemTab(value.path)); setProblem(value); }
  const load = () => run("loading", async () => {
    const listed = catalog ?? await readTemplateCatalog();
    setCatalog(listed);
    adopt(await readTemplateConfig(selected ?? listed.defaultId));
  });
  useEffect(() => { void load(); }, []); // Load once per mount; Retry calls load again.
  function mayLeave(): Promise<boolean> {
    if (!unsaved(live.current.shown, live.current.text)) return Promise.resolve(true);
    return new Promise(resolve => { answer.current = resolve; setAsking(true); });
  }
  function answered(open: boolean) { setAsking(false); answer.current?.(open); answer.current = null; }
  const choose = async (templateId: string) => {
    if (templateId === selected || !await mayLeave()) return;
    await run("loading", async () => adopt(await readTemplateConfig(templateId)));
  };

  const check = () => run("checking", async () => {
    if (!state) return;
    const result = await checkTemplateConfig(state.package.id, text);
    // A taken revision is no error in the text: Save resolves it with the offered one.
    if (result.valid || result.error.nextRevision) { setProblem(null); setOutcome("checked"); setNextRevision(result.valid ? null : result.error.nextRevision ?? null); }
    else showProblem(result.error);
  });
  const save = (revision?: string) => run("saving", async () => {
    if (draft) { if (created(await createTemplate({ text, assetsFrom: draft.assetsFrom }))) setOutcome("saved"); return; }
    if (!state) return;
    const result = await saveTemplateConfig(state.package.id, text, revision);
    if (!result.saved) { if (result.error.nextRevision) setOffer(result.error); else showProblem(result.error); return; }
    adopt(result.state); setCatalog(value => value && withState(value, result.state)); setOutcome("saved");
  });
  const reset = () => run("resetting", async () => {
    if (!state) return;
    const next = await resetTemplateConfig(state.package.id);
    adopt(next); setCatalog(value => value && withState(value, next)); setOutcome("reset");
  });
  const makeDefault = () => run("defaulting", async () => {
    if (!state) return;
    setCatalog(await setDefaultTemplate(state.package.id)); setOutcome("default");
  });
  /** A new template opens at once and joins the list under the id the server chose. */
  function created(result: TemplateSave): boolean {
    if (!result.saved) { showProblem(result.error); return false; }
    adopt(result.state); setCatalog(value => value && withState(value, result.state));
    return true;
  }
  const add = async () => {
    const name = copyName?.trim();
    if (!state || !name) return;
    setCopyName(null);
    if (!await mayLeave()) return;
    await run("adding", async () => { if (created(await createTemplate({ copyOf: state.package.id, name }))) setOutcome("added"); });
  };
  const remove = () => run("deleting", async () => {
    if (!state) return;
    const next = await deleteTemplate(state.package.id);
    setCatalog(next); adopt(await readTemplateConfig(next.defaultId)); setOutcome("deleted");
  });
  function context(): TemplateContext | null {
    const { shown: current, text: source } = live.current;
    if (!current) return null;
    return current.kind === "saved" ? { templateId: current.state.package.id, assetsFrom: current.state.package.id, text: source, name: current.state.package.name }
      : { templateId: null, assetsFrom: current.assetsFrom, text: source, name: draftLabel(current.name) };
  }
  async function apply(proposal: TemplateProposal, force: boolean, runAssets: string | null): Promise<ApplyOutcome> {
    const replace = (value: string) => { setText(value); setProblem(null); setOutcome(null); };
    // The list and the editor wait while the target opens, so nothing typed meanwhile is overwritten.
    begin("applying");
    try {
      return await applyProposal(proposal, force, runAssets, { current: () => live.current, mayLeave,
        open: async templateId => { const opened = await readTemplateConfig(templateId); adopt(opened); return opened.text; },
        showDraft: (name, assetsFrom, value) => { setShown({ kind: "draft", name, assetsFrom }); replace(value); },
        renameDraft: name => setShown(value => value?.kind === "draft" ? { ...value, name } : value), replace });
    } finally { setWork(null); }
  }
  const download = async () => {
    setDelivery(null);
    setDelivery(await deliverFile(new Blob([text], { type: "application/yaml" }), downloadName(shown)));
  };

  function pick(action: MenuAction) {
    if (action === "copy") setCopyName(state ? `${state.package.name} — копия` : "");
    else if (action === "branding") setBranding(true);
    else if (action === "default") void makeDefault();
    else if (action === "download") void download();
    else if (action === "reset") setConfirmReset(true);
    else setConfirmDelete(true);
  }

  const busy = work !== null;
  const groups = catalog && groupedCatalog(catalog);
  const row = (entry: TemplateEntry) => <button key={entry.id} className="template-row" disabled={busy}
    aria-current={entry.id === selected ? "page" : undefined} onClick={() => void choose(entry.id)}>
    <strong>{entry.name}{entry.id === catalog?.defaultId && <span className="template-default" title="Основной шаблон"><Icon name="star" /></span>}</strong>
    <small>{rowNote(entry, catalog?.defaultId ?? "")}</small>
  </button>;
  const chips = state && catalog ? [{ label: state.package.revision }, { label: templateKind(state) },
    ...(state.package.id === catalog.defaultId ? [{ label: "основной", main: true }] : [])] : [{ label: "новый" }];
  const done = outcome === "checked" ? nextRevision ? `Ошибок нет. Эта версия уже сохранена с другим содержимым: при сохранении будет предложена версия ${nextRevision}.` : "Ошибок нет."
    : outcome === "saved" ? "Сохранено. Изменения применятся к новым резюме."
    : outcome === "branded" && state ? `Сохранено как версия ${state.package.revision}. Новые резюме получат логотип и email; готовые не изменятся.`
    : outcome === "reset" ? "Встроенный шаблон восстановлен."
    : outcome === "default" && state ? `Основной шаблон: ${state.package.name}.`
    : outcome === "added" && state ? `Добавлен шаблон «${state.package.name}».`
    : outcome === "deleted" ? "Шаблон удалён. Готовые резюме сохранили свой вид." : deliveryMessage(delivery);
  const running = work && progress[work];
  return <section className="templates-screen" aria-label="Шаблоны">
    <div className="templates-layout">
      <nav className="templates-list" aria-label="Список шаблонов">
        <div className="templates-list-heading"><span className="eyebrow">Встроенные</span>
          <button type="button" className="icon templates-add" aria-label="Копия выбранного" title="Копия выбранного" disabled={busy || !state}
            onClick={() => setCopyName(state ? `${state.package.name} — копия` : "")}><Icon name="plus" /></button></div>
        {groups?.bundled.map(row)}
        {groups && (groups.own.length > 0 || draft) && <div className="templates-list-heading"><span className="eyebrow">Свои</span></div>}
        {groups?.own.map(row)}
        {draft && <button className="template-row" aria-current="page" disabled={busy}><strong>{draftLabel(draft.name)}</strong><small>новый</small></button>}
      </nav>
      <div className="templates-editor">
        {shown && <TemplateToolbar name={state ? state.package.name : draft ? draftLabel(draft.name) : ""} chips={chips}
          actions={menuActions(shown, catalog?.defaultId ?? null)} dirty={dirty} busy={busy} saving={work === "saving"} checking={work === "checking"}
          save={() => void save()} check={state ? () => void check() : undefined} more={more} choose={pick} />}
        {!shown && <div className="template-yaml-loading">
          {work === "loading" ? <OperationStatus label="Загружаем шаблон" timed />
            : <>{failure !== null && <p className="notice error" role="alert">{errorMessage(failure)}</p>}
              <Button className="small" onClick={() => void load()}>Загрузить снова</Button></>}
        </div>}
        {shown && <Tabs.Root className="template-tabs" value={tab} onValueChange={value => setTab(value as SectionTab)}>
          <div className="template-tab-row">{present.size > 0 && <Tabs.List className="template-tab-list" aria-label="Разделы шаблона">
            {sectionTabs.map(item => <Tabs.Trigger key={item.id} value={item.id} disabled={!present.has(item.id)}>{item.label}</Tabs.Trigger>)}
          </Tabs.List>}<span className="template-assistant-slot" ref={setAssistantSlot} /></div>
          {/* The assistant pane sits under the toolbar beside the editor; on a narrow window it lies over the editor only. */}
          <div className="template-work">
            {/* One editor for every tab: the panel follows the chosen tab instead of holding a copy per tab. */}
            <Tabs.Content className="template-tab-panel" value={tab} forceMount>
              <Suspense fallback={<div className="template-yaml-loading"><OperationStatus label="Загружаем редактор" /></div>}>
                <YamlEditor ref={yaml} value={text} problem={problem} readOnly={busy} tab={tab}
                  change={value => { setText(value); setProblem(null); setOutcome(null); }} />
              </Suspense>
            </Tabs.Content>
            <aside className="templates-assistant" aria-label="Помощник по шаблонам">
              <TemplateAssistant open={open} context={context} names={names} apply={apply} settings={settings} toggleHost={assistantSlot} />
            </aside>
          </div>
        </Tabs.Root>}
        {shown && <div className="template-status">
          <div className="template-status-message">
            {running ? <OperationStatus label={running} />
              : failure !== null ? <p className="template-status-error" role="alert">{errorMessage(failure)}</p>
              : problem ? <p className="template-status-error" role="alert"><button type="button" className="template-problem" title={`Показать в тексте: ${problem.path}`}
                onClick={() => yaml.current?.reveal()}><Icon name="warning" /><span>Строка {problemLine(text, problem.path)}: {problem.message}</span></button></p>
              : done ? <OperationStatus state="success" label={done} /> : null}
          </div>
          {dirty && <span className="settings-saved" role="status">Не сохранено</span>}
          {dirty && state && <button type="button" className="text-button" disabled={busy}
            onClick={() => { setText(state.text); setProblem(null); setOutcome(null); }}>Отменить правки</button>}
        </div>}
      </div>
    </div>
    <Dialog open={branding} close={() => setBranding(false)} title="Логотип и подвал" returnFocus={more.current}>
      {branding && state && <TemplateBranding templateId={state.package.id} packageHash={state.package.packageHash} blocked={dirty} disabled={busy}
        close={() => setBranding(false)} saved={next => { adopt(next); setCatalog(value => value && withState(value, next)); setBranding(false); setOutcome("branded"); }} />}
    </Dialog>
    <Dialog open={confirmReset} close={() => setConfirmReset(false)} title="Вернуть встроенный шаблон?" returnFocus={more.current}>
      <p className="dialog-copy">Ваши правки этого шаблона пропадут. Готовые резюме не изменятся.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmReset(false)}>Отмена</Button>
        <Button variant="primary" onClick={() => { setConfirmReset(false); void reset(); }}>Вернуть</Button></div>
    </Dialog>
    <Dialog open={copyName !== null} close={() => setCopyName(null)} title="Новый шаблон" returnFocus={more.current}>
      <form className="template-name-form" onSubmit={event => { event.preventDefault(); void add(); }}>
        <p className="dialog-copy">Копия шаблона «{state?.package.name}». Она сохранится сразу, её можно будет изменить и удалить.</p>
        <label htmlFor="template-copy-name">Название</label>
        <input id="template-copy-name" value={copyName ?? ""} maxLength={120} autoFocus onChange={event => setCopyName(event.currentTarget.value)} />
        <div className="dialog-actions"><Button type="button" variant="quiet" onClick={() => setCopyName(null)}>Отмена</Button>
          <Button type="submit" variant="primary" disabled={!copyName?.trim()}>Добавить</Button></div>
      </form>
    </Dialog>
    <Dialog open={confirmDelete} close={() => setConfirmDelete(false)} title={`Удалить шаблон «${state?.package.name ?? ""}»?`} returnFocus={more.current}>
      <p className="dialog-copy">Новые резюме не смогут его выбрать. Готовые резюме сохранят свой вид.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmDelete(false)}>Отмена</Button>
        <Button variant="danger" onClick={() => { setConfirmDelete(false); void remove(); }}>Удалить</Button></div>
    </Dialog>
    <Dialog open={offer !== null} close={() => { if (offer) showProblem(offer); setOffer(null); }} title="Сохранить как новую версию?">
      <p className="dialog-copy">Эта версия шаблона уже сохранена с другим содержимым. Сохранить правки как версию {offer?.nextRevision}?</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => { if (offer) showProblem(offer); setOffer(null); }}>Отмена</Button>
        <Button variant="primary" onClick={() => { const next = offer?.nextRevision; setOffer(null); if (next) void save(next); }}>
          Сохранить как {offer?.nextRevision}</Button></div>
    </Dialog>
    <Dialog open={asking} close={() => answered(false)} title="Открыть другой шаблон?">
      <p className="dialog-copy">Несохранённые правки пропадут.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => answered(false)}>Остаться</Button>
        <Button variant="danger" onClick={() => answered(true)}>Открыть</Button></div>
    </Dialog>
  </section>;
}
