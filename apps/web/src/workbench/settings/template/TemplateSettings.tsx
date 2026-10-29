import { lazy, Suspense, useEffect, useState } from "react";
import { errorMessage } from "../../../errors/messages";
import type { TemplateCatalog } from "../../../projects/api";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { OperationStatus } from "../../ui/OperationStatus";
import { checkTemplateConfig, readTemplateCatalog, readTemplateConfig, resetTemplateConfig, saveTemplateConfig, setDefaultTemplate,
  withState, type TemplateConfigState, type TemplateProblem } from "./config";

const YamlEditor = lazy(() => import("./YamlEditor"));
type Work = "loading" | "checking" | "saving" | "resetting" | "defaulting" | null;
type Outcome = "checked" | "saved" | "reset" | "default" | null;

/** The YAML of each template new imports can use, and the default one. Existing resumes keep their own version. */
export default function TemplateSettings({ dirtyChange }: { dirtyChange: (dirty: boolean) => void }) {
  const [catalog, setCatalog] = useState<TemplateCatalog | null>(null);
  const [state, setState] = useState<TemplateConfigState | null>(null);
  const [text, setText] = useState("");
  const [work, setWork] = useState<Work>("loading");
  const [problem, setProblem] = useState<TemplateProblem | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  // A template to switch to once unsaved edits of the shown one may be dropped.
  const [switchTo, setSwitchTo] = useState<string | null>(null);
  const [technical, setTechnical] = useState(false);
  const dirty = state !== null && text !== state.text;
  useEffect(() => { dirtyChange(dirty); }, [dirty, dirtyChange]);

  async function run(kind: Exclude<Work, null>, task: () => Promise<void>) {
    setWork(kind); setFailure(null); setOutcome(null);
    try { await task(); } catch (error) { setFailure(error); } finally { setWork(null); }
  }
  function adopt(next: TemplateConfigState) { setState(next); setText(next.text); setProblem(null); }
  const load = () => run("loading", async () => {
    const listed = catalog ?? await readTemplateCatalog();
    setCatalog(listed);
    adopt(await readTemplateConfig(state?.package.id ?? listed.defaultId));
  });
  useEffect(() => { void load(); }, []); // Load once per mount; Retry calls load again.
  const open = (templateId: string) => run("loading", async () => adopt(await readTemplateConfig(templateId)));
  const choose = (templateId: string) => { if (dirty) setSwitchTo(templateId); else void open(templateId); };

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
  const selected = state?.package.id ?? "";
  const kind = !state ? "" : !state.bundled ? "свой шаблон" : state.edited ? "изменён" : "встроенный";
  return <>
    <h3>Шаблон резюме</h3>
    {catalog && state && <div className="template-choice">
      <label htmlFor="template-select">Шаблон</label>
      <select className="model-select" id="template-select" value={selected} disabled={busy} onChange={event => choose(event.currentTarget.value)}>
        {catalog.templates.map(entry => <option key={entry.id} value={entry.id}>
          {entry.name}{entry.id === catalog.defaultId ? " · основной" : ""}</option>)}
      </select>
      {selected !== catalog.defaultId && <Button className="small" busy={work === "defaulting"} busyLabel="Сохраняем…" disabled={busy}
        onClick={() => void makeDefault()}>Сделать основным</Button>}
    </div>}
    {state && <p className="template-active small">Версия {state.package.revision}<span className="muted">{kind}</span></p>}
    {work === "loading" && <OperationStatus label="Загружаем шаблон" timed />}
    {failure !== null && <p className="notice error" role="alert">{errorMessage(failure)}</p>}
    {problem && <p className="notice error template-problem" role="alert">Ошибка в <code>{problem.path}</code>: {problem.message}</p>}
    {outcome === "checked" && <OperationStatus state="success" label="Ошибок нет." />}
    {outcome === "saved" && <OperationStatus state="success" label="Сохранено. Изменения применятся к новым резюме." />}
    {outcome === "reset" && <OperationStatus state="success" label="Встроенный шаблон восстановлен." />}
    {outcome === "default" && state && <OperationStatus state="success" label={`Основной шаблон: ${state.package.name}.`} />}
    {state && <label className="template-technical small"><input type="checkbox" checked={technical} onChange={event => setTechnical(event.target.checked)} />
      Показать служебные разделы</label>}
    {state && <Suspense fallback={<div className="template-yaml-loading"><OperationStatus label="Загружаем редактор" /></div>}>
      <YamlEditor value={text} problem={problem} readOnly={busy} technical={technical}
        change={value => { setText(value); setProblem(null); setOutcome(null); }} />
    </Suspense>}
    <div className="settings-actions">
      {!state && !busy && <Button className="small" onClick={() => void load()}>Загрузить снова</Button>}
      {state && <>
        <Button variant="primary" busy={work === "saving"} busyLabel="Сохраняем…" disabled={!dirty || busy} onClick={() => void save()}>Сохранить</Button>
        <Button busy={work === "checking"} busyLabel="Проверяем…" disabled={busy} onClick={() => void check()}>Проверить</Button>
        <Button variant="quiet" disabled={!dirty || busy} onClick={() => { setText(state.text); setProblem(null); setOutcome(null); }}>Отменить правки</Button>
        {state.bundled && <Button variant="quiet" busy={work === "resetting"} busyLabel="Возвращаем…" disabled={busy || !state.edited}
          onClick={() => setConfirmReset(true)}>Вернуть встроенный</Button>}
        {dirty && <span className="settings-saved" role="status">Не сохранено</span>}
      </>}
    </div>
    <Dialog open={confirmReset} close={() => setConfirmReset(false)} title="Вернуть встроенный шаблон?">
      <p className="dialog-copy">Ваши правки этого шаблона пропадут. Готовые резюме не изменятся.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmReset(false)}>Отмена</Button>
        <Button variant="primary" onClick={() => { setConfirmReset(false); void reset(); }}>Вернуть</Button></div>
    </Dialog>
    <Dialog open={switchTo !== null} close={() => setSwitchTo(null)} title="Открыть другой шаблон?">
      <p className="dialog-copy">Несохранённые правки пропадут.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setSwitchTo(null)}>Остаться</Button>
        <Button variant="danger" onClick={() => { const next = switchTo; setSwitchTo(null); if (next) void open(next); }}>Открыть</Button></div>
    </Dialog>
  </>;
}
