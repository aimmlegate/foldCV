import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AgentApiFailure } from "../../assistant/api";
import { AssistantRuns, terminal } from "../../assistant/controller";
import { errorText, shownFailure } from "../../assistant/presentation";
import { onTarget, proposalTarget, sampleSpent, TEMPLATE_TEXT_BYTES, TemplateAssistantApi, textBytes, textHash, type ShownTarget,
  type TemplateFields, type TemplateProposal, type TemplateSample } from "../../assistant/template";
import { useAutoscroll, useDrawer } from "../../assistant/useDrawer";
import { DrawerView } from "../assistant/DrawerView";
import { templateScope } from "../assistant/scope";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Icon } from "../ui/Icon";
import { Spinner } from "../ui/Spinner";
import type { ApplyOutcome } from "./apply";
import { TemplateProposalCard } from "./ProposalCard";

/** The editor as a run sees it: the shown template (null for a new one), whose assets the draft uses, and the text. */
export type TemplateContext = { templateId: string | null; assetsFrom: string | null; text: string; name: string };
export type ApplyProposal = (proposal: TemplateProposal, force: boolean, assetsFrom: string | null) => Promise<ApplyOutcome>;

const code = (error: unknown) => error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED";
const sampleTypes = ".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** The template assistant beside the YAML editor (D141): it reads templates and samples, never resumes, and its
 * proposals change only the editor text; the user saves. Its toggle goes into `toggleHost` over the editor (D147); the
 * pane shows only while open, and the remembered drawer size keeps that choice. */
export function TemplateAssistant({ open, context, names, apply, settings, toggleHost }: {
  open: boolean; context: () => TemplateContext | null; names: ReadonlyMap<string, string>; apply: ApplyProposal; settings: () => void;
  toggleHost: HTMLElement | null;
}) {
  const [proposals, setProposals] = useState<TemplateProposal[]>([]);
  const [working, setWorking] = useState<string | null>(null), [confirm, setConfirm] = useState<TemplateProposal | null>(null);
  const api = useRef<TemplateAssistantApi | null>(null), picker = useRef<HTMLInputElement>(null);
  // The attached sample goes with the next run only; the service keeps the last three in memory.
  const [sample, setSample] = useState<TemplateSample | null>(null), [uploading, setUploading] = useState(false);
  // The sample of the request being sent: a retried send repeats that request, whatever is attached by then.
  const sent = useRef<string | null>(null);
  const { view, size, setSize, failure, setFailure, controller, log, report } = useDrawer("foldcv.templates.assistant.drawer", "templates", changed => {
      const port = new TemplateAssistantApi();
      // No proposal of this scope goes through the run controller: the cards below apply into the editor.
      const current = new AssistantRuns<TemplateFields>(port, { applyProposal: () => Promise.reject(new AgentApiFailure("REQUEST_FAILED")) }, changed);
      current.flags({ allowEdits: false, allowWeb: true });
      api.current = port;
      return { controller: current, settings: () => port.settings() };
    });
  useEffect(() => { if (open) report(controller.current?.refresh()); }, [open]);
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
  useAutoscroll(log, [view?.messages, view?.partial, view?.sources, view?.activity, proposals]);
  // The hash of the editor text: a card compares its proposal's base with it, so «Заменить» follows the text.
  const shown = context(), shownText = shown?.text ?? null;
  const [hashed, setHashed] = useState<{ text: string; hash: string } | null>(null);
  useEffect(() => {
    if (shownText === null) { setHashed(null); return; }
    let alive = true;
    void textHash(shownText).then(hash => { if (alive) setHashed({ text: shownText, hash }); });
    return () => { alive = false; };
  }, [shownText]);
  const target: ShownTarget = shown && { templateId: shown.templateId, draft: shown.templateId === null, unsaved: false };
  const changedFor = (proposal: TemplateProposal) => onTarget(proposal, target) && hashed !== null && hashed.text === shownText && hashed.hash !== proposal.baseHash;
  const paneOpen = !size.collapsed, toggleButton = useRef<HTMLButtonElement>(null), wasOpen = useRef(paneOpen);
  // The pane's own close button goes away with it: the focus moves to the toggle, which stays.
  useEffect(() => { if (wasOpen.current && !paneOpen) toggleButton.current?.focus(); wasOpen.current = paneOpen; }, [paneOpen]);

  function send() {
    const current = controller.current, before = current?.view.run?.id ?? null;
    if (!current || !shown) return;
    setFailure(null);
    // A retried send repeats its request; a new one must fit the run limit, which is below the editor's.
    if (!current.view.pendingSend && textBytes(shown.text) > TEMPLATE_TEXT_BYTES) { setFailure("TEMPLATE_TEXT_LIMIT"); return; }
    // The editor text is read when the request is built, so typing up to that moment goes with the run.
    report(current.sendWith(async () => {
      const latest = context();
      if (!latest) throw new AgentApiFailure("REQUEST_FAILED");
      sent.current = sample?.sampleId ?? null;
      return { templateId: latest.templateId, assetsFrom: latest.assetsFrom, text: latest.text, textHash: await textHash(latest.text), sampleId: sent.current };
    }).then(() => { if (sampleSpent(before, current.view)) setSample(value => value !== null && value.sampleId === sent.current ? null : value); }));
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
      // "changed" needs no record: the card compares the base with the target's text once it is shown.
      if (await apply(proposal, force, port.runAssets.get(proposal.runId) ?? null) === "applied") replaced(await port.decide(proposal.id, "applied"));
    } catch (error) { setFailure(code(error)); } finally { setWorking(null); }
  }
  async function discard(proposal: TemplateProposal) {
    const port = api.current;
    if (!port || working) return;
    setWorking(proposal.id); setFailure(null);
    try { replaced(await port.decide(proposal.id, "discarded")); } catch (error) { setFailure(code(error)); } finally { setWorking(null); }
  }

  if (!view?.settings?.enabled) return null;
  const active = controller.current?.active ?? false, failed = shownFailure(failure, view.run), frozen = view.submitting || view.pendingSend;
  const toggle = () => setSize(value => ({ ...value, collapsed: !value.collapsed }));
  return <>
    {toggleHost && createPortal(<Button ref={toggleButton} className="small template-assistant-toggle" aria-pressed={paneOpen} aria-controls={templateScope.host}
      title={paneOpen ? "Скрыть помощника" : "Показать помощника"} onClick={toggle}><Icon name="chat" /><span>Помощник</span>
      {active && <Spinner />}</Button>, toggleHost)}
    {paneOpen && <DrawerView view={view} active={active} title={shown?.name ?? "Шаблон"} collapsed={false} expanded={size.height >= 500} height={size.height}
      toggle={toggle} expand={() => setSize(value => ({ ...value, height: value.height >= 500 ? 320 : 520 }))}
      resize={height => setSize(value => ({ ...value, height }))} log={log} captured={null} applying={working !== null}
      failure={failed ? errorText(failed) : view.error ? errorText(view.error) : null} fence={null}
      draft={value => controller.current?.draft(value)} flags={(_edits, allowWeb) => controller.current?.flags({ allowEdits: false, allowWeb })}
      model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => {}} settings={settings}
      select={id => report(controller.current?.select(id))} fresh={() => report(controller.current?.newConversation())}
      applyProposal={() => {}} discardProposal={() => {}} resource={(kind, id) => report(controller.current?.resource(kind, id))} focus={() => false}
      scope={templateScope} attachment={id => api.current?.runSamples.get(id) ?? null}
      context={<><span className="chat-context-resume" title={shown?.name}><Icon name="file" />{shown?.name ?? "Шаблон не открыт"}</span>
        {sample ? <span className="chat-attachment" title={sample.name}><Icon name="file" />{sample.name}
          <button type="button" aria-label={`Убрать образец: ${sample.name}`} disabled={frozen} onClick={() => setSample(null)}><Icon name="close" /></button></span>
          : <button type="button" className="chat-scope" disabled={uploading || frozen} onClick={() => picker.current?.click()}>
            <Icon name="upload" />{uploading ? "Читаем образец…" : "Образец DOCX или PDF"}</button>}
        <input ref={picker} type="file" accept={sampleTypes} hidden aria-label="Образец DOCX или PDF" onChange={event => {
          const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
          if (file) void attach(file);
        }} /></>}
      extra={proposals.map(value => <TemplateProposalCard key={value.id} value={value} target={proposalTarget(value, names)} onTarget={onTarget(value, target)}
        current={() => context()?.text ?? ""} busy={active || working !== null} applying={working === value.id} changed={changedFor(value)}
        apply={() => void decide(value, false)} replace={() => setConfirm(value)} discard={() => void discard(value)} />)} />}
    <Dialog open={confirm !== null} close={() => setConfirm(null)} title="Заменить текст шаблона?">
      <p className="dialog-copy">Текст в редакторе изменился после запуска. Эти правки пропадут, текст станет предложенным. Сохранить можно будет потом.</p>
      <div className="dialog-actions"><Button variant="quiet" onClick={() => setConfirm(null)}>Отмена</Button>
        <Button variant="danger" onClick={() => { const value = confirm; setConfirm(null); if (value) void decide(value, true); }}>Заменить</Button></div>
    </Dialog>
  </>;
}
