import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { errorMessage } from "../../errors/messages";
import type { TemplateCatalog } from "../../projects/api";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { OperationStatus } from "../ui/OperationStatus";
import { checkTemplateConfig, readTemplateCatalog, readTemplateConfig, resetTemplateConfig, saveTemplateConfig, setDefaultTemplate,
  withState, type TemplateConfigState, type TemplateProblem } from "./config";
import { shownId, templateKind, unsaved, type ShownTemplate } from "./studio";

const YamlEditor = lazy(() => import("./YamlEditor"));
type Work = "loading" | "checking" | "saving" | "resetting" | "defaulting" | null;
type Outcome = "checked" | "saved" | "reset" | "default" | null;

/** The templates screen: the list, the YAML of the shown template and, later, the assistant. New imports use these
 * templates; existing resumes keep their own captured version. */
export default function TemplatesScreen({ close }: { close: () => void }) {
  const [catalog, setCatalog] = useState<TemplateCatalog | null>(null);
  const [shown, setShown] = useState<ShownTemplate | null>(null);
  const [text, setText] = useState("");
  const [work, setWork] = useState<Work>("loading");
  const [problem, setProblem] = useState<TemplateProblem | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  // Opening another template drops unsaved edits of the shown one, so it asks first.
  const [asking, setAsking] = useState(false);
  const answer = useRef<((open: boolean) => void) | null>(null);
  const [technical, setTechnical] = useState(false);
  const dirty = unsaved(shown, text), selected = shownId(shown), state = shown?.kind === "saved" ? shown.state : null;

  async function run(kind: Exclude<Work, null>, task: () => Promise<void>) {
    setWork(kind); setFailure(null); setOutcome(null);
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
    if (!dirty) return Promise.resolve(true);
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
    if (result.valid) { setProblem(null); setOutcome("checked"); } else setProblem(result.error);
  });
  const save = () => run("saving", async () => {
    if (!state) return;
    const result = await saveTemplateConfig(state.package.id, text);
    if (!result.saved) { setProblem(result.error); return; }
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

  const busy = work !== null;
  return <section className="templates-screen" aria-label="Шаблоны">
    <div className="settings-title"><button className="text-button" onClick={close}>← К резюме</button></div>
    <div className="templates-layout">
      <nav className="templates-list" aria-label="Список шаблонов">
        {catalog?.templates.map(entry => <button key={entry.id} className="template-row" disabled={busy}
          aria-current={entry.id === selected ? "page" : undefined} onClick={() => void choose(entry.id)}>
          <strong>{entry.name}</strong>
          <small>{entry.revision}{entry.id === catalog.defaultId ? " · основной" : ""} · {templateKind(entry)}</small>
        </button>)}
      </nav>
      <div className="templates-editor">
        {state && catalog && <div className="template-active">
          <h3>{state.package.name}</h3>
          <span className="small">Версия {state.package.revision}</span><span className="small muted">{templateKind(state)}</span>
          {state.package.id === catalog.defaultId ? <span className="small muted">основной</span>
            : <Button className="small" busy={work === "defaulting"} busyLabel="Сохраняем…" disabled={busy} onClick={() => void makeDefault()}>Сделать основным</Button>}
        </div>}
        {work === "loading" && <OperationStatus label="Загружаем шаблон" timed />}
        {failure !== null && <p className="notice error" role="alert">{errorMessage(failure)}</p>}
        {problem && <p className="notice error template-problem" role="alert">Ошибка в <code>{problem.path}</code>: {problem.message}</p>}
        {outcome === "checked" && <OperationStatus state="success" label="Ошибок нет." />}
        {outcome === "saved" && <OperationStatus state="success" label="Сохранено. Изменения применятся к новым резюме." />}
        {outcome === "reset" && <OperationStatus state="success" label="Встроенный шаблон восстановлен." />}
        {outcome === "default" && state && <OperationStatus state="success" label={`Основной шаблон: ${state.package.name}.`} />}
        {shown && <label className="template-technical small"><input type="checkbox" checked={technical} onChange={event => setTechnical(event.target.checked)} />
          Показать служебные разделы</label>}
        {shown && <Suspense fallback={<div className="template-yaml-loading"><OperationStatus label="Загружаем редактор" /></div>}>
          <YamlEditor value={text} problem={problem} readOnly={busy} technical={technical}
            change={value => { setText(value); setProblem(null); setOutcome(null); }} />
        </Suspense>}
        <div className="settings-actions">
          {!shown && !busy && <Button className="small" onClick={() => void load()}>Загрузить снова</Button>}
          {state && <>
            <Button variant="primary" busy={work === "saving"} busyLabel="Сохраняем…" disabled={!dirty || busy} onClick={() => void save()}>Сохранить</Button>
            <Button busy={work === "checking"} busyLabel="Проверяем…" disabled={busy} onClick={() => void check()}>Проверить</Button>
            <Button variant="quiet" disabled={!dirty || busy} onClick={() => { setText(state.text); setProblem(null); setOutcome(null); }}>Отменить правки</Button>
            {state.bundled && <Button variant="quiet" busy={work === "resetting"} busyLabel="Возвращаем…" disabled={busy || !state.edited}
              onClick={() => setConfirmReset(true)}>Вернуть встроенный</Button>}
          </>}
          {dirty && <span className="settings-saved" role="status">Не сохранено</span>}
        </div>
      </div>
    </div>
    <Dialog open={confirmReset} close={() => setConfirmReset(false)} title="Вернуть встроенный шаблон?">
      <p className="dialog-copy">Ваши правки этого шаблона пропадут. Готовые резюме не изменятся.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmReset(false)}>Отмена</Button>
        <Button variant="primary" onClick={() => { setConfirmReset(false); void reset(); }}>Вернуть</Button></div>
    </Dialog>
    <Dialog open={asking} close={() => answered(false)} title="Открыть другой шаблон?">
      <p className="dialog-copy">Несохранённые правки пропадут.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => answered(false)}>Остаться</Button>
        <Button variant="danger" onClick={() => answered(true)}>Открыть</Button></div>
    </Dialog>
  </section>;
}
