import { useEffect, useImperativeHandle, useRef, useState, type Ref, type RefObject } from "react";
import type { TemplateEditorHandle } from "../rich/TemplateEditor";
import { AgentApiFailure, AssistantApi } from "./api";
import { AssistantController, type AssistantSelection } from "./controller";
import { errorText, shownFailure } from "./presentation";
import { useAutoscroll, useDrawer } from "./useDrawer";
import { DrawerView } from "../workbench/assistant/DrawerView";

export type AssistantHandle = { stop: () => Promise<void> };

function blocksText(count: number): string {
  const last = count % 10, tens = count % 100;
  const word = last === 1 && tens !== 11 ? "блок" : last >= 2 && last <= 4 && (tens < 12 || tens > 14) ? "блока" : "блоков";
  return `${String(count)} ${word}`;
}

/** The assistant drawer of the open V7 editor: runs read a pinned snapshot, proposals change the resume only through
 * the editor's Apply (D093, D109). */
export function AssistantDrawer({ projectId, editor, settingsOpen, settings, ref, title = "Резюме", onProjectLifecycle }: {
  projectId: string; editor: RefObject<TemplateEditorHandle | null>; settingsOpen: boolean; settings: () => void; ref: Ref<AssistantHandle>;
  title?: string; onProjectLifecycle?: (kind: "archive" | "delete") => Promise<boolean> }) {
  const [captured, setCaptured] = useState<AssistantSelection | null>(null);
  const selectionKey = useRef("");
  const lifecycle = useRef(onProjectLifecycle);
  lifecycle.current = onProjectLifecycle;
  const { view, size, setSize, failure, setFailure, controller, log, report } = useDrawer("foldcv.assistant.drawer", projectId, changed => {
    const api = new AssistantApi(projectId);
    const current = new AssistantController(api, {
      applyProposal: (id, allowEdits) => {
        const mounted = editor.current;
        return mounted ? mounted.applyAssistant(id, allowEdits) : Promise.reject(new AgentApiFailure("EDITOR_TOKEN_UNKNOWN"));
      },
      actionApplied: async action => {
        if (action.action === "archive" || action.action === "delete") { await lifecycle.current?.(action.action); return; }
        if (action.action !== "restore") await editor.current?.refresh();
      } }, changed);
    return { controller: current, settings: () => api.settings() };
  });
  useEffect(() => { if (!settingsOpen) report(controller.current?.refresh()); }, [settingsOpen]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.activeElement?.closest(".cv-document")) return;
      const next = editor.current?.captureSelection() ?? null;
      const id = JSON.stringify(next);
      if (id !== selectionKey.current) { selectionKey.current = id; setCaptured(next); }
    }, 200);
    return () => clearInterval(timer);
  }, [editor]);
  useAutoscroll(log, [view?.messages, view?.partial, view?.findings, view?.sources, view?.activity, view?.proposals]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [view?.conversationId, view?.run?.id]);
  useImperativeHandle(ref, () => ({ stop: async () => { if (controller.current?.active) await controller.current.stop(); } }), []);
  function send() {
    const current = controller.current, mounted = editor.current, scope = captured;
    if (!current || !mounted) return;
    setFailure(null);
    // The run reads the saved project, so typing is saved first.
    report(current.send(async () => { await mounted.flush(); return scope; }));
  }
  const active = controller.current?.active ?? false, failed = shownFailure(failure, view?.run ?? null);
  return view?.settings?.enabled ? <DrawerView view={view} active={active} title={title} collapsed={size.collapsed} expanded={size.height >= 500} height={size.height}
    toggle={() => setSize(value => ({ ...value, collapsed: !value.collapsed }))} expand={() => setSize(value => ({ ...value, height: value.height >= 500 ? 320 : 520 }))}
    resize={height => setSize(value => ({ ...value, height }))}
    log={log} captured={captured ? blocksText(captured.blockIds.length) : null}
    applying={view.proposalBusy !== null}
    failure={failed ? errorText(failed) : view.error ? errorText(view.error) : null} fence={null}
    draft={value => controller.current?.draft(value)} flags={(allowEdits, allowWeb) => controller.current?.flags({ allowEdits, allowWeb })}
    model={model => report(controller.current?.chooseModel(model))} send={send} stop={() => report(controller.current?.stop())} clear={() => setCaptured(null)} settings={settings}
    select={id => report(controller.current?.select(id))} fresh={() => report(controller.current?.newConversation())}
    applyProposal={value => report(controller.current?.applyProposal(value))}
    discardProposal={value => report(controller.current?.discardProposal(value))}
    resource={(kind, id) => report(controller.current?.resource(kind, id))} focus={anchor => editor.current?.focusFinding(anchor) ?? false} />
    : null;
}
