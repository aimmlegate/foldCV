import { lazy, Suspense, useEffect, useState } from "react";
import { errorMessage } from "../../../errors/messages";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { OperationStatus } from "../../ui/OperationStatus";
import { checkTemplateConfig, readTemplateConfig, resetTemplateConfig, saveTemplateConfig,
  type TemplateConfigState, type TemplateProblem } from "./config";

const YamlEditor = lazy(() => import("./YamlEditor"));
type Work = "loading" | "checking" | "saving" | "resetting" | null;
type Outcome = { kind: "checked" | "saved" | "reset"; label: string } | null;

/** The YAML of the template used by new imports. Saving activates it; existing resumes keep their own version. */
export default function TemplateSettings({ dirtyChange }: { dirtyChange: (dirty: boolean) => void }) {
  const [state, setState] = useState<TemplateConfigState | null>(null);
  const [text, setText] = useState("");
  const [work, setWork] = useState<Work>("loading");
  const [problem, setProblem] = useState<TemplateProblem | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [technical, setTechnical] = useState(false);
  const dirty = state !== null && text !== state.text;
  useEffect(() => { dirtyChange(dirty); }, [dirty, dirtyChange]);

  async function run(kind: Exclude<Work, null>, task: () => Promise<void>) {
    setWork(kind); setFailure(null); setOutcome(null);
    try { await task(); } catch (error) { setFailure(error); } finally { setWork(null); }
  }
  function adopt(next: TemplateConfigState) { setState(next); setText(next.text); setProblem(null); }
  const load = () => run("loading", async () => adopt(await readTemplateConfig()));
  useEffect(() => { void load(); }, []); // Load once per mount; Retry calls load again.

  const check = () => run("checking", async () => {
    const result = await checkTemplateConfig(text);
    if (result.valid) { setProblem(null); setOutcome({ kind: "checked", label: `${result.package.name} · ${result.package.revision}` }); }
    else setProblem(result.error);
  });
  const save = () => run("saving", async () => {
    const result = await saveTemplateConfig(text);
    if (!result.saved) { setProblem(result.error); return; }
    adopt(result.state); setOutcome({ kind: "saved", label: `${result.state.package.name} · ${result.state.package.revision}` });
  });
  const reset = () => run("resetting", async () => {
    const next = await resetTemplateConfig();
    adopt(next); setOutcome({ kind: "reset", label: `${next.package.name} · ${next.package.revision}` });
  });

  const busy = work !== null;
  return <>
    <h3>Шаблон резюме</h3>
    <p className="small muted">Действует при импорте резюме. Шаблон описывает блоки, их оформление, извлечение данных (<code>extract</code>) и правила переписывания (<code>rewrite</code>). Сохранённый шаблон действует для новых импортов; уже созданные резюме сохраняют свою версию.</p>
    {state && <p className="template-active small">Сейчас используется: <strong>{state.package.name} · {state.package.revision}</strong>
      <span className="muted">{state.bundled ? "встроенный шаблон" : "изменённый шаблон"}</span></p>}
    {work === "loading" && <OperationStatus label="Загружаем шаблон" timed />}
    {failure !== null && <p className="notice error" role="alert">{errorMessage(failure)}</p>}
    {problem && <p className="notice error template-problem" role="alert">Шаблон не принят: <code>{problem.path}</code> — {problem.message}</p>}
    {outcome?.kind === "checked" && <OperationStatus state="success" label={`Шаблон корректен: ${outcome.label}.`} />}
    {outcome?.kind === "saved" && <OperationStatus state="success" label={`Сохранено. Новые импорты используют «${outcome.label}».`} />}
    {outcome?.kind === "reset" && <OperationStatus state="success" label={`Возвращён встроенный шаблон «${outcome.label}».`} />}
    {state && <label className="template-technical small"><input type="checkbox" checked={technical} onChange={event => setTechnical(event.target.checked)} />
      Развернуть технические разделы (шрифты и файлы, хранение фактов, операции)</label>}
    {state && <Suspense fallback={<div className="template-yaml-loading"><OperationStatus label="Загружаем редактор" /></div>}>
      <YamlEditor value={text} problem={problem} readOnly={busy} technical={technical}
        change={value => { setText(value); setProblem(null); setOutcome(null); }} />
    </Suspense>}
    {state && <p className="small muted">Подсказки и проверка по схеме работают при вводе. Перед сохранением сервер проверяет весь шаблон, включая ссылки между блоками и файлы шрифтов и логотипов. Изменённое содержимое требует новой версии в <code>template.revision</code>.</p>}
    <div className="settings-actions">
      {!state && !busy && <Button className="small" onClick={() => void load()}>Повторить загрузку шаблона</Button>}
      {state && <>
        <Button variant="primary" busy={work === "saving"} busyLabel="Сохраняем…" disabled={!dirty || busy} onClick={() => void save()}>Сохранить и использовать</Button>
        <Button busy={work === "checking"} busyLabel="Проверяем…" disabled={busy} onClick={() => void check()}>Проверить</Button>
        <Button variant="quiet" disabled={!dirty || busy} onClick={() => { setText(state.text); setProblem(null); setOutcome(null); }}>Отменить правки</Button>
        <Button variant="quiet" busy={work === "resetting"} busyLabel="Возвращаем…" disabled={busy || state.bundled} onClick={() => setConfirmReset(true)}>Вернуть встроенный шаблон</Button>
        <span className="settings-saved" role="status">{dirty ? "Есть несохранённые правки шаблона" : "Шаблон сохранён"}</span>
      </>}
    </div>
    <Dialog open={confirmReset} close={() => setConfirmReset(false)} title="Вернуть встроенный шаблон?">
      <p className="dialog-copy">Новые импорты будут использовать встроенный шаблон. Несохранённые правки пропадут. Уже созданные резюме не изменятся.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirmReset(false)}>Отмена</Button>
        <Button variant="primary" onClick={() => { setConfirmReset(false); void reset(); }}>Вернуть</Button></div>
    </Dialog>
  </>;
}
