import assert from "node:assert/strict";
import { ProjectJobs, type JobsTransport } from "../../src/background/jobs";
import type { BackgroundConversation } from "../../src/background/api";
import type { JobProjectV1 } from "../../src/contracts/generated/background_project_v1";
import type { JobSnapshotV1 } from "../../src/contracts/generated/background_snapshot_v1";
import type { JobAgentRequestV1 } from "../../src/contracts/generated/background_agent_request_v1";
import type { AgentRun } from "../../src/contracts/generated/agent_run";
import type { AgentSettings } from "../../src/contracts/generated/agent_settings";
import type { AssistantApi } from "../../src/assistant/controller";
import { before, job, proposal } from "./background-writer";

export function running(id = "job-one", cursor = 1): JobSnapshotV1 {
  return { ...structuredClone(job), id, execution: "running", publication: "none", proposalId: null, receipt: null,
    eventCursor: cursor, attempts: [], error: null, publicationError: null };
}
export function run(value: JobSnapshotV1, conversationId = "conversation-one"): AgentRun {
  return { id: value.id, projectId: value.submission.identity.projectId, conversationId,
    clientRequestId: value.submission.identity.requestId, ownerEpoch: value.executionGeneration,
    state: value.execution === "completed" ? "completed" : value.execution === "cancelled" ? "cancelled" : "running",
    allowEdits: true, allowWeb: false, scope: { kind: "resume" }, model: "model-one", connectionEpoch: "account-one",
    settingsRevision: 1, createdAt: value.createdAt, deadline: "2026-10-17T12:00:00Z", finishedAt: null,
    usage: null, error: null, savedBatchId: null, outcomeUnknown: false };
}
export function conversation(value: JobSnapshotV1, id = "conversation-one"): BackgroundConversation {
  return { schemaVersion: 1, id, projectId: value.submission.identity.projectId, createdAt: value.createdAt, updatedAt: value.updatedAt,
    runs: [run(value, id)], messages: [{ id: `user-${value.id}`, role: "user", runId: value.id, text: value.id,
      timestamp: value.createdAt, sources: [], findings: [], error: null, truncated: false }], sources: [], findings: [] };
}

export function jobsHarness(projectId = job.submission.identity.projectId, initial: JobSnapshotV1[] = [running()]) {
  let state: JobProjectV1 = { schemaVersion: 1, projectId, lineage: job.submission.identity.lineage, requestEpoch: 1,
    jobs: initial.map(value => ({ ...value, submission: { ...value.submission, identity: { ...value.submission.identity, projectId } } })) };
  const calls = { cancel: 0, legacy: 0, submit: [] as JobAgentRequestV1[] }, timers = new Set<() => void>();
  let projectReply = () => Promise.resolve(structuredClone(state));
  let conversationReply = (id: string) => { const value = state.jobs.find(value => value.id === id); assert.ok(value); return Promise.resolve(conversation(value)); };
  const api: JobsTransport = {
    project: projectId, projectJobs: () => projectReply(), read: id => { const value = state.jobs.find(job => job.id === id); assert.ok(value); return Promise.resolve(value); },
    submit: request => { calls.submit.push(structuredClone(request)); const value = running(`submitted-${String(calls.submit.length)}`);
      state = { ...state, jobs: [...state.jobs, value] }; return Promise.resolve(value); },
    cancel: id => { calls.cancel++; const old = state.jobs.find(job => job.id === id); assert.ok(old);
      const value: JobSnapshotV1 = { ...old, execution: "cancelled", eventCursor: old.eventCursor + 1 };
      state = { ...state, jobs: state.jobs.map(job => job.id === id ? value : job) }; return Promise.resolve(value); },
    replay: (id, generation, after) => { const value = state.jobs.find(job => job.id === id); assert.ok(value);
      return Promise.resolve({ schemaVersion: 1, events: Array.from({ length: Math.max(0, value.eventCursor - after) }, (_value, index) => {
        const cursor = after + index + 1;
        return { schemaVersion: 1, projectId, lineage: state.lineage, jobId: id, generation, cursor,
          type: "job.snapshot", snapshot: { ...value, eventCursor: cursor } };
      }) }); },
    proposal: () => Promise.resolve(proposal), legacy: id => { calls.legacy++; const value = state.jobs.find(job => job.id === id); assert.ok(value);
      return Promise.resolve({ schemaVersion: 2, jobId: id, publication: value.publication, run: run(value) }); },
    conversation: id => conversationReply(id),
  };
  const jobs = new ProjectJobs(api, { later: callback => { timers.add(callback); return () => { timers.delete(callback); }; } });
  return { jobs, api, calls, timers, get state() { return state; }, set: (next: JobSnapshotV1[]) => { state = { ...state, jobs: next }; },
    projectReply: (reply: typeof projectReply) => { projectReply = reply; }, conversationReply: (reply: typeof conversationReply) => { conversationReply = reply; },
    close() { jobs.close(); assert.equal(timers.size, 0); } };
}

export function assistantApi(projectId = before.response.workspace.projectId) {
  const now = "2026-10-16T12:00:00Z", calls = { lease: 0, cancel: 0 };
  let settings: AgentSettings = { schemaVersion: 1, revision: 1, enabled: true, selectedAgentModel: "model-one" };
  const forbidden = () => { calls.lease++; return Promise.reject(new Error("Legacy owner path reached")); };
  const api: AssistantApi = { projectId, settings: () => Promise.resolve(settings),
    saveSettings: value => { settings = { schemaVersion: 1, revision: settings.revision + 1, ...value }; return Promise.resolve(settings); },
    capabilities: () => Promise.resolve({ schemaVersion: 1, ready: true, binaryVersion: "synthetic", binarySha256: "a".repeat(64),
      protocolSha256: "b".repeat(64), configSha256: "c".repeat(64), connectionEpoch: "account-one", modes: ["edit", "check_only"],
      tools: [], webAvailable: false, models: [], unavailable: null }),
    conversations: () => Promise.resolve({ items: [{ id: "conversation-one", createdAt: now, updatedAt: now, title: "Synthetic", activeRunId: null }], nextCursor: null }),
    conversation: () => Promise.resolve({ schemaVersion: 1, id: "conversation-two", projectId, createdAt: now, updatedAt: now, messages: [], runs: [], sources: [], findings: [] }),
    messages: () => Promise.resolve({ items: [], nextCursor: null }), resources: () => Promise.resolve({ sources: [], findings: [], nextCursor: null }),
    open: forbidden, renew: forbidden, close: forbidden, submit: forbidden, read: forbidden,
    cancel: () => { calls.cancel++; return Promise.reject(new Error("Legacy Stop reached")); },
    events: async function* () { yield* []; },
    prepared: () => ({ claim: forbidden, commit: forbidden, recover: forbidden, report: forbidden }) };
  return { api, calls };
}
