import { useEffect, useRef, useState } from "react";
import { ConnectionWorkflow } from "../../connection/workflow";
import { AgentApiFailure } from "../../assistant/api";
import { AssistantRuns, terminal, type AssistantView } from "../../assistant/controller";
import { drawerSize, errorText, rereadsCapabilities, shownFailure } from "../../assistant/presentation";
import { proposalTarget, sampleSpent, TemplateAssistantApi, textHash, type TemplateFields, type TemplateProposal, type TemplateSample } from "../../assistant/template";
import { DrawerView } from "../assistant/DrawerView";
import { templateScope } from "../assistant/scope";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import type { ApplyOutcome } from "./apply";
import { TemplateProposalCard } from "./ProposalCard";

/** The editor as a run sees it: the shown template (null for a new one), whose assets the draft uses, and the text. */
export type TemplateContext = { templateId: string | null; assetsFrom: string | null; text: string; name: string };
export type ApplyProposal = (proposal: TemplateProposal, force: boolean, assetsFrom: string | null) => Promise<ApplyOutcome>;

const key = "foldcv.templates.assistant.drawer";
function storedSize() { try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null"); return drawerSize(value); } catch { return drawerSize(null); } }
const code = (error: unknown) => error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED";
const sampleTypes = ".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** The template assistant beside the YAML editor (D141): it reads templates and samples, never resumes, and its
 * proposals change only the editor text; the user saves. */
export function TemplateAssistant({ open, context, names, apply, settings }: {
  open: boolean; context: () => TemplateContext | null; names: ReadonlyMap<string, string>; apply: ApplyProposal; settings: () => void;
}) {
  const [view, setView] = useState<AssistantView | null>(null), [size, setSize] = useState(storedSize);
  const [failure, setFailure] = useState<string | null>(null);
  const [proposals, setProposals] = useState<TemplateProposal[]>([]);
  const [changed, setChanged] = useState<ReadonlySet<string>>(() => new Set());
  const [working, setWorking] = useState<string | null>(null), [confirm, setConfirm] = useState<TemplateProposal | null>(null);
  const api = useRef<TemplateAssistantApi | null>(null), controller = useRef<AssistantRuns<TemplateFields> | null>(null);
  const log = useRef<HTMLDivElement>(null), picker = useRef<HTMLInputElement>(null);
  // The attached sample goes with the next run only; the service keeps the last three in memory.
  const [sample, setSample] = useState<TemplateSample | null>(null), [uploading, setUploading] = useState(false);
  const report = (work: Promise<void> | undefined) => { void work?.catch(error => setFailure(code(error))); };
  useEffect(() => {
    const port = new TemplateAssistantApi(), connection = new ConnectionWorkflow(() => {});
    // No proposal of this scope goes through the run controller: the cards below apply into the editor.
    const current = new AssistantRuns<TemplateFields>(port, { applyProposal: () => Promise.reject(new AgentApiFailure("REQUEST_FAILED")) }, setView);
    current.flags({ allowEdits: false, allowWeb: true });
    api.current = port; controller.current = current; setView(current.view);
    void (async () => {
      await connection.peek(false);
      if ((await port.settings()).enabled) await connection.checkUnchecked();
      await current.init();
    })().catch(() => setFailure("REQUEST_FAILED"));
    return () => { connection.close(); current.close(); if (controller.current === current) controller.current = null; };
  }, []);
  useEffect(() => { if (open) report(controller.current?.refresh()); }, [open]);
  const refused = rereadsCapabilities(view);
  useEffect(() => {
    if (!refused) return;
    const timer = setInterval(() => { report(controller.current?.refreshCapabilities()); }, 2000);
    return () => clearInterval(timer);
  }, [refused]);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(size)); } catch { /* Size is optional when browser storage is unavailable. */ } }, [size]);
  // Proposals are read for the shown conversation, again when one is announced and when a run ends.
  const conversationId = view?.conversationId ?? null, runId = view?.run?.id ?? null, ended = terminal(view?.run ?? null);
  const announced = view?.activity.filter(event => event.type === "proposal.ready").length ?? 0;
  useEffect(() => {
    const port = api.current;
    if (!port || !conversationId) { setProposals([]); return; }
    let alive = true;
    void port.templateProposals(conversationId).then(items => { if (alive) setProposals(items); }, error => { if (alive) setFailure(code(error)); });
    return () => { alive = false; };
  }, [conversationId, runId, ended, announced]);
  useEffect(() => {
    const element = log.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 180) element.scrollTop = element.scrollHeight;
  }, [view?.messages, view?.partial, view?.sources, view?.activity, proposals]);

  function send() {
    const current = controller.current;
    if (!current || !context()) return;
    setFailure(null);
    const attached = sample, before = current.view.run?.id ?? null;
    // The editor text is read when the request is built, so typing up to that moment goes with the run.
    report(current.sendWith(async () => {
      const shown = context();
      if (!shown) throw new AgentApiFailure("REQUEST_FAILED");
      return { templateId: shown.templateId, assetsFrom: shown.assetsFrom, text: shown.text, textHash: await textHash(shown.text), sampleId: attached?.sampleId ?? null };
    }).then(() => { if (attached && sampleSpent(before, current.view)) setSample(value => value === attached ? null : value); }));
  }
  async function attach(file: File) {
    const port = api.current;
    if (!port) return;
    setUploading(true); setFailure(null);
    try { setSample(await port.uploadSample(file)); } catch (error) { setFailure(code(error)); } finally { setUploading(false); }
  }
  function replaced(proposal: TemplateProposal) { setProposals(items => items.map(item => item.id === proposal.id ? proposal : item)); }
  async function decide(proposal: TemplateProposal, force: boolean) {
    const port = api.current;
    if (!port || working) return;
    setWorking(proposal.id); setFailure(null);
    try {
      const outcome = await apply(proposal, force, port.runAssets.get(proposal.runId) ?? null);
      if (outcome === "changed") setChanged(value => new Set([...value, proposal.id]));
      if (outcome === "applied") replaced(await port.decide(proposal.id, "applied"));
    } catch (error) { setFailure(code(error)); } finally { setWorking(null); }
  }
  async function discard(proposal: TemplateProposal) {
    const port = api.current;
    if (!port || working) return;
    setWorking(proposal.id); setFailure(null);
    try { replaced(await port.decide(proposal.id, "discarded")); } catch (error) { setFailure(code(error)); } finally { setWorking(null); }
  }

  if (!view?.settings?.enabled) return null;
  const active = controller.current?.active ?? false, failed = shownFailure(failure, view.run), shown = context();
  return <>
    <DrawerView view={view} active={active} title={shown?.name ?? "Шаблон"} collapsed={size.collapsed} expanded={size.height >= 500} height={size.height}
      toggle={() => setSize(value => ({ ...value, collapsed: !value.collapsed }))} expand={() => setSize(value => ({ ...value, height: value.height >= 500 ? 320 : 520 }))}
      resize={height => setSize(value => ({ ...value, height }))} log={log} captured={null} applying={working !== null}
      failure={failed ? errorText(failed) : view.error ? errorText(view.error) : null} fence={null}
      draft={value => controller.current?.draft(value)} flags={(_edits, allowWeb) => controller.current?.flags({ allowEdits: false, allowWeb })}
      model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => {}} settings={settings}
      select={id => report(controller.current?.select(id))} fresh={() => report(controller.current?.newConversation())}
      applyProposal={() => {}} discardProposal={() => {}} resource={(kind, id) => report(controller.current?.resource(kind, id))} focus={() => false}
      scope={templateScope} attachment={id => api.current?.runSamples.get(id) ?? null}
      context={<><span className="chat-context-resume" title={shown?.name}><Icon name="file" />{shown?.name ?? "Шаблон не открыт"}</span>
        {sample ? <span className="chat-attachment" title={sample.name}><Icon name="file" />{sample.name}
          <button type="button" aria-label={`Убрать образец: ${sample.name}`} disabled={view.submitting} onClick={() => setSample(null)}><Icon name="close" /></button></span>
          : <button type="button" className="chat-scope" disabled={uploading || view.submitting} onClick={() => picker.current?.click()}>
            <Icon name="upload" />{uploading ? "Читаем образец…" : "Образец DOCX или PDF"}</button>}
        <input ref={picker} type="file" accept={sampleTypes} hidden aria-label="Образец DOCX или PDF" onChange={event => {
          const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
          if (file) void attach(file);
        }} /></>}
      extra={proposals.map(value => <TemplateProposalCard key={value.id} value={value} target={proposalTarget(value, names)} current={shown?.text ?? ""}
        busy={active || working !== null} applying={working === value.id} changed={changed.has(value.id)}
        apply={() => void decide(value, false)} replace={() => setConfirm(value)} discard={() => void discard(value)} />)} />
    <Dialog open={confirm !== null} close={() => setConfirm(null)} title="Заменить текст шаблона?">
      <p className="dialog-copy">Текст в редакторе изменился после запуска. Эти правки пропадут, текст станет предложенным. Сохранить можно будет потом.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirm(null)}>Отмена</Button>
        <Button variant="danger" onClick={() => { const value = confirm; setConfirm(null); if (value) void decide(value, true); }}>Заменить</Button></div>
    </Dialog>
  </>;
}
