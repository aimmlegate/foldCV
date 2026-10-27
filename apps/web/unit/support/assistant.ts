import type { AgentEvent } from "../../src/contracts/generated/agent_event";
import type { AgentMessage } from "../../src/contracts/generated/agent_message";
import type { AgentSettings } from "../../src/contracts/generated/agent_settings";
import type { AssistantCapabilitiesV1 } from "../../src/contracts/generated/assistant_capabilities_v1";
import type { AssistantEventsV1 } from "../../src/contracts/generated/assistant_events_v1";
import type { AssistantMessagesV1 } from "../../src/contracts/generated/assistant_messages_v1";
import type { AssistantRunRequestV2 } from "../../src/contracts/generated/assistant_run_request_v2";
import type { Port, AssistantView } from "../../src/assistant/controller";
import type { Proposal, Run } from "../../src/assistant/api";

export const PROJECT = "template-project";
export const settings: AgentSettings = { schemaVersion: 1, revision: 2, enabled: true, selectedAgentModel: "assistant-model" };
export const capabilities: AssistantCapabilitiesV1 = { ready: true, unavailable: null, models: [{ model: "assistant-model", state: "unverified" }],
  webAvailable: true, tools: ["read_resume"] };

export function run(state: Run["state"] = "running", id = "run-1", conversationId = "conversation-1"): Run {
  return { id, conversationId, projectId: PROJECT, clientRequestId: "request-1", state, allowEdits: true, allowWeb: false,
    model: "assistant-model", baseRevision: 1, createdAt: "2026-10-27T12:00:00+00:00",
    finishedAt: ["completed", "failed", "cancelled", "interrupted"].includes(state) ? "2026-10-27T12:00:05+00:00" : null,
    error: null, usage: null };
}
export function event(sequence: number, type: AgentEvent["type"], payload: unknown, runId = "run-1"): AgentEvent {
  return { schemaVersion: 1, id: `event_${String(sequence)}`, sequence, projectId: PROJECT, conversationId: "conversation-1", runId,
    timestamp: `2026-10-27T12:00:${String(sequence).padStart(2, "0")}+00:00`, type, payload } as AgentEvent;
}
export function message(role: "user" | "assistant", text: string, runId = "run-1"): AgentMessage {
  return { id: `message-${role}-${runId}`, role, text, runId, timestamp: "2026-10-27T12:00:00+00:00", sources: [], findings: [],
    truncated: false, error: null };
}
export function proposal(changes: Partial<Proposal> = {}): Proposal {
  return { schemaVersion: 1, id: "proposal-1", projectId: PROJECT, conversationId: "conversation-1", runId: "run-1", kind: "edit",
    summary: "Clearer wording", baseRevision: 1, touched: { "block-paper-a": "a".repeat(64) }, expectedActionId: null,
    ops: [{ op: "replace_text", blockId: "block-paper-a", cellId: null, field: "content", find: "By", replace: "Written by" }],
    preview: [{ target: "block-paper-a", label: "replace_text", before: "By Shared title", after: "Written by Shared title" }],
    state: "draft", appliedRevision: null, createdAt: "2026-10-27T12:00:03+00:00", updatedAt: "2026-10-27T12:00:03+00:00", ...changes };
}
export function view(changes: Partial<AssistantView> = {}): AssistantView {
  return { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: false }, conversations: [], conversationId: "conversation-1",
    messages: [], sources: [], findings: [], files: [], run: run(), activity: [], partial: "", partialTruncated: false, proposals: [],
    proposalBusy: null, staleProposals: [], draft: "", submitting: false, pendingSend: false, error: null, ...changes };
}

/** A scripted assistant server: conversations, a run whose events come from `script`, and proposals. */
export function fakeApi(script: AgentEvent[][] = [], final: Run = run("completed")) {
  const calls = { submit: [] as AssistantRunRequestV2[], events: [] as number[], cancel: 0, discard: [] as string[], messages: 0,
    concurrentEvents: 0, peakEvents: 0 };
  const state = { messages: [message("user", "Проверь резюме")] as AgentMessage[], files: [] as AssistantMessagesV1["files"],
    runs: [] as Run[], proposals: [] as Proposal[], cancelled: false, submitFailures: 0 };
  let replies = 0;
  const api: Port = {
    projectId: PROJECT,
    settings: () => Promise.resolve(settings),
    saveSettings: value => Promise.resolve({ ...settings, revision: settings.revision + 1, enabled: value.enabled, selectedAgentModel: value.selectedAgentModel }),
    capabilities: () => Promise.resolve(capabilities),
    conversations: () => Promise.resolve({ items: [{ id: "conversation-1", title: "Проверь резюме", createdAt: "2026-10-27T12:00:00+00:00",
      updatedAt: "2026-10-27T12:00:00+00:00" }] }),
    createConversation: () => Promise.resolve({ id: "conversation-2", title: "", createdAt: "2026-10-27T12:01:00+00:00", updatedAt: "2026-10-27T12:01:00+00:00" }),
    messages: id => { calls.messages++; return Promise.resolve({ conversation: { id, title: "Проверь резюме", createdAt: "2026-10-27T12:00:00+00:00",
      updatedAt: "2026-10-27T12:00:00+00:00" }, messages: state.messages, sources: [], findings: [], runs: state.runs as AssistantMessagesV1["runs"],
      files: state.files } as AssistantMessagesV1); },
    submit: async (_conversation, request) => {
      calls.submit.push(structuredClone(request));
      if (state.submitFailures > 0) { state.submitFailures--; throw new TypeError("fetch failed"); }
      const started = run("running");
      state.runs = [started];
      return started;
    },
    events: async (_run, after): Promise<AssistantEventsV1> => {
      calls.events.push(after); calls.concurrentEvents++; calls.peakEvents = Math.max(calls.peakEvents, calls.concurrentEvents);
      // A long-poll answers on a later task, so Stop and other UI work can interleave as in the browser.
      await new Promise(resolve => { setTimeout(resolve, 0); });
      calls.concurrentEvents--;
      const batch = state.cancelled ? [] : script[replies++] ?? [];
      const done = state.cancelled || replies > script.length;
      const current = state.cancelled ? run("cancelled") : done ? final : run("running");
      if (done) state.runs = [current];
      return { run: current, events: batch, next: batch.at(-1)?.sequence ?? after };
    },
    cancel: () => { calls.cancel++; state.cancelled = true; return Promise.resolve(run("cancelling")); },
    proposals: () => Promise.resolve({ items: state.proposals }),
    discard: id => { calls.discard.push(id); const found = state.proposals.find(item => item.id === id) ?? proposal({ id });
      return Promise.resolve({ ...found, state: "discarded" }); },
  };
  return { api, calls, state };
}
