import { useEffect, useRef, useState } from "react";
import { ConnectionWorkflow } from "./workflow";
import type { ConnectionView } from "./workflow";

const control = "rounded border border-outline bg-panel px-3 py-2 text-content hover:bg-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50";
const field = "w-full rounded border border-outline bg-surface p-2 text-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

const messages: Record<ConnectionView["snapshot"]["state"], string> = {
  unchecked: "Check the installed CLI when you are ready.",
  detached: "Disconnected from this app. Your CLI sign-in stays in place.",
  cli_missing: "Codex CLI was not found. Install it, or start the local service with FOLDCV_CODEX_EXECUTABLE set to its path.",
  launcher_unsupported: "This CLI needs Node to start. Install Node, then restart the local service so it can find Node, and refresh.",
  unsupported_version: "This CLI version is not supported by this service mode.",
  login_required: "Sign in with ChatGPT through the Codex CLI to check your plan and models.",
  api_key_mode: "The CLI is using an API key. This app requires a ChatGPT subscription login.",
  metadata_failed: "The CLI could not report account or model details. Check the CLI and try again.",
  quota_exhausted: "The CLI reports a reached plan limit. Wait for its reset before using models.",
  unknown_limits: "The CLI reported models, but plan limits are unavailable.",
  connected: "ChatGPT login and model catalog are available.",
  login_pending: "Complete sign-in in the browser opened by the CLI.",
  login_failed: "CLI sign-in did not finish. Try again.",
  cleanup_blocked: "Could not confirm that the CLI operation stopped safely. Restart the local service after checking it.",
};

export function ConnectionPanel({ onReadyChange }: { onReadyChange?: (ready: boolean) => void }) {
  const [view, setView] = useState<ConnectionView>({ snapshot: { state: "unchecked", version: null,
    plan: null, models: [], selectedModel: null, quota: { state: "unknown", usedPercent: null, resetsAt: null },
    metadataReady: false, generationReady: false, experimentalMode: false }, pending: false, detaching: false, error: null });
  const workflowRef = useRef<ConnectionWorkflow | null>(null);
  if (!workflowRef.current) workflowRef.current = new ConnectionWorkflow((next) => {
    setView(next);
    onReadyChange?.(next.snapshot.generationReady);
  });
  const workflow = workflowRef.current;
  useEffect(() => () => workflow.close(), [workflow]);
  const { snapshot } = view;
  return <section aria-label="Codex connection" className="rounded border border-outline bg-panel p-5">
    <h2 className="mb-3 text-lg font-semibold">Codex connection</h2>
    <p role="status" className="text-sm">{view.detaching ? "Stopping this app's CLI operation…" : messages[snapshot.state]}</p>
    {snapshot.version && <p className="mt-2 text-sm text-muted">CLI version: {snapshot.version}</p>}
    {snapshot.plan && <p className="mt-1 text-sm text-muted">Reported plan: {snapshot.plan}</p>}
    <div className="mt-4 flex flex-wrap gap-2">
      <button type="button" className={control} disabled={view.pending} onClick={() => void workflow.refresh()}>Refresh connection</button>
      {snapshot.state === "login_required" && <button type="button" className={control} disabled={view.pending} onClick={() => void workflow.login()}>Sign in with Codex CLI</button>}
      {snapshot.state === "login_pending" && <button type="button" className={control} onClick={() => void workflow.cancelLogin()}>Cancel sign-in</button>}
      <button type="button" className={control} disabled={view.detaching} onClick={() => void workflow.detach()}>Detach</button>
    </div>
    {view.pending && <p className="mt-2 text-sm text-muted" aria-live="polite">{view.detaching ? "Stopping…" : "Checking…"}</p>}
    {view.error && <p role="alert" className="mt-2 text-sm text-danger">{view.error}</p>}
    {snapshot.metadataReady && <div className="mt-4 border-t border-outline pt-4">
      <label htmlFor="connection-model" className="block text-sm font-semibold">Reported model</label>
      <select id="connection-model" className={`${field} mt-1`} disabled={view.pending}
        value={snapshot.selectedModel ?? ""} onChange={(event) => void workflow.select(event.target.value)}>
        <option value="">Choose a model</option>
        {snapshot.models.map((model) => <option key={model} value={model}>{model}</option>)}
      </select>
      <p className="mt-1 text-xs text-muted">A listed model does not confirm access to it.</p>
      <p className="mt-2 text-sm text-muted">Plan limit: {snapshot.quota.state === "unknown" ? "Unknown" :
        snapshot.quota.state === "exhausted" ? "Reached" : "Available"}
        {snapshot.quota.usedPercent !== null ? ` · ${snapshot.quota.usedPercent}% used` : ""}
        {snapshot.quota.resetsAt !== null ? ` · resets ${new Date(snapshot.quota.resetsAt * 1000).toLocaleString()}` : ""}</p>
    </div>}
    {snapshot.experimentalMode ? <p className="mt-4 border-l-4 border-accent pl-3 text-sm">
      {snapshot.generationReady ? "Personal CLI experiment is ready." : "Personal CLI experiment: sign in, refresh, and choose a model to enable generation."}
      {" "}Uses your ChatGPT subscription; provider retention applies. The native CLI may expose built-in tools to the model and retain prompt or response traces. Dedicated sign-in and state persist after Detach.
    </p> : <p className="mt-4 border-l-4 border-danger pl-3 text-sm text-danger">Generation is unavailable: this CLI profile has not passed the safety check.</p>}
    <p className="mt-3 text-xs text-muted">Need setup? <a className="underline" href="https://developers.openai.com/codex/cli" target="_blank" rel="noreferrer">Install Codex CLI</a> · <a className="underline" href="https://learn.chatgpt.com/docs/auth" target="_blank" rel="noreferrer">Sign-in guide</a></p>
  </section>;
}
