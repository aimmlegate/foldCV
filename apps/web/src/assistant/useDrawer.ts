import { useEffect, useRef, useState, type RefObject } from "react";
import { ConnectionWorkflow } from "../connection/workflow";
import type { AgentSettings } from "../contracts/generated/contracts";
import { AgentApiFailure } from "./api";
import type { AssistantRuns, AssistantView } from "./controller";
import { drawerSize, rereadsCapabilities, type DrawerSize } from "./presentation";

function storedSize(key: string): DrawerSize {
  try { const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null"); return drawerSize(value); } catch { return drawerSize(null); }
}

/** What both drawers share: the controller's life, the connection check before the first read, the capability
 * re-reads while a check runs, the remembered size and the failure line. `identity` restarts the controller. */
export function useDrawer<Controller extends Pick<AssistantRuns<never>, "view" | "init" | "close" | "refreshCapabilities">>(key: string, identity: string,
  create: (changed: (view: AssistantView) => void) => { controller: Controller; settings: () => Promise<AgentSettings> }) {
  const [view, setView] = useState<AssistantView | null>(null), [size, setSize] = useState(() => storedSize(key));
  const [failure, setFailure] = useState<string | null>(null);
  const controller = useRef<Controller | null>(null), log = useRef<HTMLDivElement>(null);
  const factory = useRef(create);
  factory.current = create;
  const report = (work: Promise<void> | undefined) => { void work?.catch(error => setFailure(error instanceof AgentApiFailure ? error.code : "REQUEST_FAILED")); };
  useEffect(() => {
    const { controller: current, settings } = factory.current(setView), connection = new ConnectionWorkflow(() => {});
    controller.current = current; setView(current.view);
    void (async () => {
      // Providers not checked yet are checked only when the assistant is on.
      await connection.peek(false);
      if ((await settings()).enabled) await connection.checkUnchecked();
      await current.init();
    })().catch(() => setFailure("REQUEST_FAILED"));
    return () => { connection.close(); current.close(); if (controller.current === current) controller.current = null; };
  }, [identity]);
  // A connection check can still be running when the panel shows a refusal; re-read until it settles.
  const refused = rereadsCapabilities(view);
  useEffect(() => {
    if (!refused) return;
    const timer = setInterval(() => { report(controller.current?.refreshCapabilities()); }, 2000);
    return () => clearInterval(timer);
  }, [refused]);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(size)); } catch { /* Size is optional when browser storage is unavailable. */ } }, [key, size]);
  return { view, size, setSize, failure, setFailure, controller, log, report };
}

/** Keeps the transcript at its end while the reader is near it; `deps` are the values whose change adds lines. */
export function useAutoscroll(log: RefObject<HTMLDivElement | null>, deps: readonly unknown[]): void {
  useEffect(() => {
    const element = log.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 180) element.scrollTop = element.scrollHeight;
  }, deps);
}
