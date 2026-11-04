import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { errorMessage } from "../../errors/messages";
import type { TemplateCatalog } from "../../projects/api";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { OperationStatus } from "../ui/OperationStatus";
import { deliverFile, deliveryMessage, type Delivery } from "../files/delivery";
import { checkTemplateConfig, createTemplate, deleteTemplate, readTemplateCatalog, readTemplateConfig, resetTemplateConfig, saveTemplateConfig,
  setDefaultTemplate, withState, type TemplateConfigState, type TemplateProblem, type TemplateSave } from "./config";
import { deleteControl, downloadName, draftLabel, shownId, templateKind, unsaved, type ShownTemplate } from "./studio";
import type { TemplateProposal } from "../../assistant/template";
import { applyProposal, type ApplyOutcome } from "./apply";
import { TemplateAssistant, type TemplateContext } from "./TemplateAssistant";

const YamlEditor = lazy(() => import("./YamlEditor"));
type Work = "loading" | "checking" | "saving" | "resetting" | "defaulting" | "adding" | "deleting" | "applying" | null;
type Outcome = "checked" | "saved" | "reset" | "default" | "added" | "deleted" | null;

/** The templates screen: the list, the YAML of the shown template and the template assistant. New imports use these
 * templates; existing resumes keep their own captured version. */
export default function TemplatesScreen({ open, close, settings }: { open: boolean; close: () => void; settings: () => void }) {
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
  const [copyName, setCopyName] = useState<string | null>(null);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  // Opening another template drops unsaved edits of the shown one, so it asks first.
  const [asking, setAsking] = useState(false);
  const answer = useRef<((open: boolean) => void) | null>(null);
  const [technical, setTechnical] = useState(false);
  const dirty = unsaved(shown, text), selected = shownId(shown), state = shown?.kind === "saved" ? shown.state : null;
  const draft = shown?.kind === "draft" ? shown : null;
  // The assistant reads and applies after renders: these hold what the editor shows now.
  const live = useRef({ shown, text });
  live.current = { shown, text };
  const names = useMemo(() => new Map(catalog?.templates.map(entry => [entry.id, entry.name]) ?? []), [catalog]);

  function begin(kind: Exclude<Work, null>) { setWork(kind); setFailure(null); setOutcome(null); setNextRevision(null); setDelivery(null); }
  async function run(kind: Exclude<Work, null>, task: () => Promise<void>) {
    begin(kind);
    try { await task(); } catch (error) { setFailure(error); } finally { setWork(null); }
  }
  function adopt(next: TemplateConfigState) { setShown({ kind: "saved", state: next }); setText(next.text); setProblem(null); }
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
    else setProblem(result.error);
  });
  const save = (revision?: string) => run("saving", async () => {
    if (draft) { if (created(await createTemplate({ text, assetsFrom: draft.assetsFrom }))) setOutcome("saved"); return; }
    if (!state) return;
    const result = await saveTemplateConfig(state.package.id, text, revision);
    if (!result.saved) { if (result.error.nextRevision) setOffer(result.error); else setProblem(result.error); return; }
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
    if (!result.saved) { setProblem(result.error); return false; }
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

  const busy = work !== null;
  return <section className="templates-screen" aria-label="Шаблоны">
    <div className="settings-title"><button className="text-button" onClick={close}>← К резюме</button></div>
    <div className="templates-layout">
      <nav className="templates-list" aria-label="Список шаблонов">
        <Button className="small templates-add" busy={work === "adding"} busyLabel="Добавляем…" disabled={busy || !state}
          onClick={() => setCopyName(state ? `${state.package.name} — копия` : "")}><Icon name="plus" />Добавить</Button>
        {catalog?.templates.map(entry => <button key={entry.id} className="template-row" disabled={busy}
          aria-current={entry.id === selected ? "page" : undefined} onClick={() => void choose(entry.id)}>
          <strong>{entry.name}</strong>
          <small>{entry.revision}{entry.id === catalog.defaultId ? " · основной" : ""} · {templateKind(entry)}</small>
        </button>)}
        {draft && <button className="template-row" aria-current="page" disabled={busy}><strong>{draftLabel(draft.name)}</strong><small>новый</small></button>}
      </nav>
      <div className="templates-editor">
        {state && catalog && <div className="template-active">
          <h3>{state.package.name}</h3>
          <span className="small">Версия {state.package.revision}</span><span className="small muted">{templateKind(state)}</span>
          {state.package.id === catalog.defaultId ? <span className="small muted">основной</span>
            : <Button className="small" busy={work === "defaulting"} busyLabel="Сохраняем…" disabled={busy} onClick={() => void makeDefault()}>Сделать основным</Button>}
          {deleteControl({ id: state.package.id, bundled: state.bundled }, catalog.defaultId) !== "hidden" && <Button className="small" variant="danger"
            busy={work === "deleting"} busyLabel="Удаляем…" disabled={busy || deleteControl({ id: state.package.id, bundled: state.bundled }, catalog.defaultId) === "disabled"}
            title={state.package.id === catalog.defaultId ? "Основной шаблон удалить нельзя: сначала сделайте основным другой" : undefined}
            onClick={() => setConfirmDelete(true)}>Удалить</Button>}
        </div>}
        {draft && <div className="template-active"><h3>{draftLabel(draft.name)}</h3>
          <span className="small muted">Сохраните, чтобы новые резюме могли его выбрать.</span></div>}
        {work === "loading" && <OperationStatus label="Загружаем шаблон" timed />}
        {failure !== null && <p className="notice error" role="alert">{errorMessage(failure)}</p>}
        {problem && <p className="notice error template-problem" role="alert">Ошибка в <code>{problem.path}</code>: {problem.message}</p>}
        {outcome === "checked" && <OperationStatus state="success" label={nextRevision
          ? `Ошибок нет. Эта версия уже сохранена с другим содержимым: при сохранении будет предложена версия ${nextRevision}.` : "Ошибок нет."} />}
        {outcome === "saved" && <OperationStatus state="success" label="Сохранено. Изменения применятся к новым резюме." />}
        {outcome === "reset" && <OperationStatus state="success" label="Встроенный шаблон восстановлен." />}
        {outcome === "default" && state && <OperationStatus state="success" label={`Основной шаблон: ${state.package.name}.`} />}
        {outcome === "added" && state && <OperationStatus state="success" label={`Добавлен шаблон «${state.package.name}».`} />}
        {outcome === "deleted" && <OperationStatus state="success" label="Шаблон удалён. Готовые резюме сохранили свой вид." />}
        {deliveryMessage(delivery) && <OperationStatus state="success" label={deliveryMessage(delivery)} />}
        {shown && <label className="template-technical small"><input type="checkbox" checked={technical} onChange={event => setTechnical(event.target.checked)} />
          Показать служебные разделы</label>}
        {shown && <Suspense fallback={<div className="template-yaml-loading"><OperationStatus label="Загружаем редактор" /></div>}>
          <YamlEditor value={text} problem={problem} readOnly={busy} technical={technical}
            change={value => { setText(value); setProblem(null); setOutcome(null); }} />
        </Suspense>}
        <div className="settings-actions">
          {!shown && !busy && <Button className="small" onClick={() => void load()}>Загрузить снова</Button>}
          {draft && <Button variant="primary" busy={work === "saving"} busyLabel="Сохраняем…" disabled={busy} onClick={() => void save()}>Сохранить</Button>}
          {state && <>
            <Button variant="primary" busy={work === "saving"} busyLabel="Сохраняем…" disabled={!dirty || busy} onClick={() => void save()}>Сохранить</Button>
            <Button busy={work === "checking"} busyLabel="Проверяем…" disabled={busy} onClick={() => void check()}>Проверить</Button>
            <Button variant="quiet" disabled={!dirty || busy} onClick={() => { setText(state.text); setProblem(null); setOutcome(null); }}>Отменить правки</Button>
            {state.bundled && <Button variant="quiet" busy={work === "resetting"} busyLabel="Возвращаем…" disabled={busy || !state.edited}
              onClick={() => setConfirmReset(true)}>Вернуть встроенный</Button>}
          </>}
          {shown && <Button variant="quiet" disabled={busy} onClick={() => void download()}><Icon name="download" />Скачать YAML</Button>}
          {dirty && <span className="settings-saved" role="status">Не сохранено</span>}
        </div>
      </div>
      <aside className="templates-assistant" aria-label="Помощник по шаблонам">
        <TemplateAssistant open={open} context={context} names={names} apply={apply} settings={settings} />
      </aside>
    </div>
    <Dialog open={confirmReset} close={() => setConfirmReset(false)} title="Вернуть встроенный шаблон?">
      <p className="dialog-copy">Ваши правки этого шаблона пропадут. Готовые резюме не изменятся.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmReset(false)}>Отмена</Button>
        <Button variant="primary" onClick={() => { setConfirmReset(false); void reset(); }}>Вернуть</Button></div>
    </Dialog>
    <Dialog open={copyName !== null} close={() => setCopyName(null)} title="Новый шаблон">
      <form className="template-name-form" onSubmit={event => { event.preventDefault(); void add(); }}>
        <p className="dialog-copy">Копия шаблона «{state?.package.name}». Она сохранится сразу, её можно будет изменить и удалить.</p>
        <label htmlFor="template-copy-name">Название</label>
        <input id="template-copy-name" value={copyName ?? ""} maxLength={120} autoFocus onChange={event => setCopyName(event.currentTarget.value)} />
        <div className="dialog-actions"><Button type="button" variant="quiet" onClick={() => setCopyName(null)}>Отмена</Button>
          <Button type="submit" variant="primary" disabled={!copyName?.trim()}>Добавить</Button></div>
      </form>
    </Dialog>
    <Dialog open={confirmDelete} close={() => setConfirmDelete(false)} title={`Удалить шаблон «${state?.package.name ?? ""}»?`}>
      <p className="dialog-copy">Новые резюме не смогут его выбрать. Готовые резюме сохранят свой вид.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmDelete(false)}>Отмена</Button>
        <Button variant="danger" onClick={() => { setConfirmDelete(false); void remove(); }}>Удалить</Button></div>
    </Dialog>
    <Dialog open={offer !== null} close={() => { setProblem(offer); setOffer(null); }} title="Сохранить как новую версию?">
      <p className="dialog-copy">Эта версия шаблона уже сохранена с другим содержимым. Сохранить правки как версию {offer?.nextRevision}?</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => { setProblem(offer); setOffer(null); }}>Отмена</Button>
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
