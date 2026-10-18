import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { validateAgentShape } from "./agent-validate.js";
import { sameValue, sha256 } from "../background/wire.js";
import rich_mutation from "../../../../contracts/json-schema/rich_mutation.schema.json" with { type: "json" };
import background_submission_v1 from "../../../../contracts/json-schema/background_submission_v1.schema.json" with { type: "json" };
import background_snapshot_v1 from "../../../../contracts/json-schema/background_snapshot_v1.schema.json" with { type: "json" };
import background_summary_v1 from "../../../../contracts/json-schema/background_summary_v1.schema.json" with { type: "json" };
import background_index_v1 from "../../../../contracts/json-schema/background_index_v1.schema.json" with { type: "json" };
import background_proposal_v1 from "../../../../contracts/json-schema/background_proposal_v1.schema.json" with { type: "json" };
import background_scope_guard_v1 from "../../../../contracts/json-schema/background_scope_guard_v1.schema.json" with { type: "json" };
import background_writer_v1 from "../../../../contracts/json-schema/background_writer_v1.schema.json" with { type: "json" };
import background_barrier_v1 from "../../../../contracts/json-schema/background_barrier_v1.schema.json" with { type: "json" };
import background_draft_v1 from "../../../../contracts/json-schema/background_draft_v1.schema.json" with { type: "json" };
import background_receipt_v1 from "../../../../contracts/json-schema/background_receipt_v1.schema.json" with { type: "json" };
import background_apply_v2 from "../../../../contracts/json-schema/background_apply_v2.schema.json" with { type: "json" };
import background_tool_saved_v3 from "../../../../contracts/json-schema/background_tool_saved_v3.schema.json" with { type: "json" };
import background_event_v1 from "../../../../contracts/json-schema/background_event_v1.schema.json" with { type: "json" };
import background_intent_v1 from "../../../../contracts/json-schema/background_intent_v1.schema.json" with { type: "json" };
import background_undo_v1 from "../../../../contracts/json-schema/background_undo_v1.schema.json" with { type: "json" };
import background_sidecar_v1 from "../../../../contracts/json-schema/background_sidecar_v1.schema.json" with { type: "json" };
import background_attempt_v1 from "../../../../contracts/json-schema/background_attempt_v1.schema.json" with { type: "json" };
import background_draft_payload_v1 from "../../../../contracts/json-schema/background_draft_payload_v1.schema.json" with { type: "json" };

import background_dispatch_v1 from "../../../../contracts/json-schema/background_dispatch_v1.schema.json" with { type: "json" };
import background_agent_request_v1 from "../../../../contracts/json-schema/background_agent_request_v1.schema.json" with { type: "json" };
import background_artifact_v1 from "../../../../contracts/json-schema/background_artifact_v1.schema.json" with { type: "json" };
import background_legacy_run_v2 from "../../../../contracts/json-schema/background_legacy_run_v2.schema.json" with { type: "json" };
import background_project_v1 from "../../../../contracts/json-schema/background_project_v1.schema.json" with { type: "json" };
import background_replay_request_v1 from "../../../../contracts/json-schema/background_replay_request_v1.schema.json" with { type: "json" };
import background_replay_v1 from "../../../../contracts/json-schema/background_replay_v1.schema.json" with { type: "json" };

import background_writer_proof_v1 from "../../../../contracts/json-schema/background_writer_proof_v1.schema.json" with { type: "json" };
import background_writer_open_v1 from "../../../../contracts/json-schema/background_writer_open_v1.schema.json" with { type: "json" };
import background_writer_advance_v1 from "../../../../contracts/json-schema/background_writer_advance_v1.schema.json" with { type: "json" };
import background_writer_barrier_ack_v1 from "../../../../contracts/json-schema/background_writer_barrier_ack_v1.schema.json" with { type: "json" };
import background_writer_barrier_command_v1 from "../../../../contracts/json-schema/background_writer_barrier_command_v1.schema.json" with { type: "json" };
import background_writer_checkpoint_v1 from "../../../../contracts/json-schema/background_writer_checkpoint_v1.schema.json" with { type: "json" };
import background_writer_abandon_v1 from "../../../../contracts/json-schema/background_writer_abandon_v1.schema.json" with { type: "json" };
import background_writer_view_v1 from "../../../../contracts/json-schema/background_writer_view_v1.schema.json" with { type: "json" };
import background_writer_mutation_v1 from "../../../../contracts/json-schema/background_writer_mutation_v1.schema.json" with { type: "json" };
import background_writer_publish_v1 from "../../../../contracts/json-schema/background_writer_publish_v1.schema.json" with { type: "json" };
import background_writer_publication_v1 from "../../../../contracts/json-schema/background_writer_publication_v1.schema.json" with { type: "json" };
import background_writer_history_request_v1 from "../../../../contracts/json-schema/background_writer_history_request_v1.schema.json" with { type: "json" };
import background_writer_history_offer_v1 from "../../../../contracts/json-schema/background_writer_history_offer_v1.schema.json" with { type: "json" };
import background_writer_history_command_v1 from "../../../../contracts/json-schema/background_writer_history_command_v1.schema.json" with { type: "json" };
import background_writer_history_result_v1 from "../../../../contracts/json-schema/background_writer_history_result_v1.schema.json" with { type: "json" };
import background_writer_draft_reference_v1 from "../../../../contracts/json-schema/background_writer_draft_reference_v1.schema.json" with { type: "json" };
import background_writer_draft_command_v1 from "../../../../contracts/json-schema/background_writer_draft_command_v1.schema.json" with { type: "json" };
import background_writer_draft_read_v1 from "../../../../contracts/json-schema/background_writer_draft_read_v1.schema.json" with { type: "json" };
import background_writer_draft_resolve_v1 from "../../../../contracts/json-schema/background_writer_draft_resolve_v1.schema.json" with { type: "json" };

import background_fixed_request_v1 from "../../../../contracts/json-schema/background_fixed_request_v1.schema.json" with { type: "json" };
import background_fixed_reply_v1 from "../../../../contracts/json-schema/background_fixed_reply_v1.schema.json" with { type: "json" };
import background_fixed_input_v1 from "../../../../contracts/json-schema/background_fixed_input_v1.schema.json" with { type: "json" };
import background_processing_candidate_v1 from "../../../../contracts/json-schema/background_processing_candidate_v1.schema.json" with { type: "json" };

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addKeyword({ keyword: "x-maxSerializedBytes", schemaType: "number",
  validate: (limit: number, value: unknown): boolean => new TextEncoder().encode(JSON.stringify(value)).length <= limit });
const schemas = new Map<string, object>(Object.entries({ background_submission_v1, background_snapshot_v1,
  background_proposal_v1, background_scope_guard_v1, background_writer_v1, background_barrier_v1,
  background_draft_v1, background_receipt_v1, background_apply_v2, background_event_v1, background_intent_v1,
  background_undo_v1, background_sidecar_v1, background_attempt_v1, background_draft_payload_v1, background_dispatch_v1, background_agent_request_v1, background_artifact_v1, background_legacy_run_v2, background_project_v1, background_replay_request_v1, background_replay_v1, background_writer_proof_v1, background_writer_open_v1, background_writer_advance_v1, background_writer_barrier_ack_v1, background_writer_barrier_command_v1, background_writer_checkpoint_v1, background_writer_abandon_v1, background_writer_view_v1, background_writer_mutation_v1, background_writer_publish_v1, background_writer_publication_v1, background_writer_history_request_v1, background_writer_history_offer_v1, background_writer_history_command_v1, background_writer_history_result_v1, background_writer_draft_reference_v1, background_writer_draft_command_v1, background_writer_draft_read_v1, background_writer_draft_resolve_v1, background_fixed_request_v1, background_fixed_reply_v1, background_fixed_input_v1, background_processing_candidate_v1 }));
schemas.set("background_summary_v1", background_summary_v1);
schemas.set("background_index_v1", background_index_v1);
schemas.set("background_tool_saved_v3", background_tool_saved_v3);
const validators = new Map<string, ValidateFunction<unknown>>();
const mutationShape = ajv.compile<unknown>(rich_mutation);
export function prepareWriterContracts(): void {
  for (const kind of ["background_writer_view_v1", "background_barrier_v1", "background_draft_v1", "background_writer_draft_read_v1",
    "background_writer_publication_v1", "background_writer_history_offer_v1", "background_undo_v1", "background_writer_history_result_v1"]) {
    const schema = schemas.get(kind);
    if (schema && !validators.has(kind)) validators.set(kind, ajv.compile<unknown>(schema));
  }
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function list(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
function earlier(left: string, right: string): boolean {
  const parts = (value: string): [string, string] => {
    const [whole = "", fraction = ""] = value.replace("+00:00", "Z").slice(0, -1).split(".");
    return [whole, fraction];
  };
  const [a, af] = parts(left), [b, bf] = parts(right);
  return a < b || (a === b && af.slice(0, 6).padEnd(6, "0") < bf.slice(0, 6).padEnd(6, "0"));
}
function semantics(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(semantics);
  if (!record(value)) return true;
  if ("projectTitle" in value && "saved" in value && "jobId" in value) {
    if (value.saved !== (value.publication === "saved") || value.allowEdits === false && value.publication !== "none") return false;
  }
  if (value.schemaVersion === 1 && "jobs" in value && Object.keys(value).every(key => ["schemaVersion", "jobs"].includes(key))) {
    const jobs = list(value.jobs), lineages = new Map<unknown, unknown>();
    const keys = jobs.map(job => record(job) ? JSON.stringify([job.projectId, job.lineage, job.jobId]) : null);
    if (new Set(keys).size !== jobs.length) return false;
    for (const job of jobs) {
      if (!record(job) || lineages.has(job.projectId) && lineages.get(job.projectId) !== job.lineage) return false;
      lineages.set(job.projectId, job.lineage);
    }
  }
  if ("syncId" in value && "actionId" in value && record(value.job)) {
    const job = value.job;
    if (!record(job.submission) || !record(job.submission.identity) || !record(job.submission.input)
      || value.projectId !== job.submission.identity.projectId || job.submission.kind === "agent"
      || (value.syncId === null) !== (value.actionId === null)
      || (job.submission.kind === "processing") !== (value.syncId === null)
      || value.syncId !== null && value.syncId !== job.submission.input.id) return false;
  }
  if ("originalSync" in value && record(value.identity) && record(value.request) && record(value.workspace)) {
    if (value.identity.lineage !== value.request.lineage || value.identity.requestEpoch !== value.request.requestEpoch
      || value.identity.requestId !== value.request.clientRequestId || value.workspace.projectId !== value.identity.projectId
      || list(value.workspace.syncRecords).length || record(value.originalSync) && list(value.originalSync.proposedSteps).length
      || !record(value.request.command)) return false;
    const processing = value.request.command.kind === "processing";
    if ((value.syncId === null) !== (value.actionId === null) || processing !== (value.syncId === null)
      || !processing && value.syncId !== value.id) return false;
    if (["retry", "resolve"].includes(String(value.request.command.kind))) {
      if (!record(value.originalSync) || value.originalSync.id !== value.request.command.syncId) return false;
    } else if (value.originalSync !== null) return false;
  }
  if ("normalized" in value && "inputId" in value && "assessment" in value) {
    if ((value.normalized === null) !== (value.workspace === null) || record(value.workspace) && value.workspace.project === null) return false;
  }
  if ("reads" in value && "writes" in value) {
    for (const group of [list(value.reads), list(value.writes)]) {
      if (new Set(group.map((item: unknown) => record(item) ? JSON.stringify([item.kind, item.key]) : null)).size !== group.length) return false;
    }
  }
  if ("schedulingClass" in value) {
    const classes: Record<string, string> = { agent: "background", processing: "background", rewrite: "interactive", reconciliation: "reconciliation" };
    const stages: Record<string, string[]> = { agent: ["agent"], processing: ["assessment", "extraction"], rewrite: ["rewrite"], reconciliation: ["reconciliation"] };
    const inputs: Record<string, string> = { agent: "agent_journal", processing: "processing", rewrite: "rich_sync", reconciliation: "rich_sync" };
    if (typeof value.kind !== "string" || value.schedulingClass !== classes[value.kind] || !record(value.input) || value.input.kind !== inputs[value.kind] ||
        JSON.stringify(list(value.models).map((model: unknown) => record(model) ? model.stage : null)) !== JSON.stringify(stages[value.kind])) return false;
    const tools = list(value.tools);
    if (new Set(tools).size !== tools.length || !record(value.guards)) return false;
    if (value.allowEdits === false && (list(value.guards.writes).length > 0 || tools.some((tool) => ["prepare_edit_batch", "apply_edit_batch"].includes(String(tool))))) return false;
    if (value.allowWeb === false && tools.includes("read_public_page")) return false;
    if (value.kind !== "agent" && (tools.length > 0 || value.allowEdits !== true || value.allowWeb !== false)) return false;
  }
  if ("authority" in value && ((value.authority === "revoked") !== (value.revocation !== null) ||
      typeof value.acceptedAt !== "string" || typeof value.executionDeadline !== "string" || !earlier(value.acceptedAt, value.executionDeadline))) return false;
  if (value.status === "clean_detached" && value.draftId !== null) return false;
  if (typeof value.touchFloor === "number" && typeof value.acknowledgedCursor === "number" && value.touchFloor > value.acknowledgedCursor) return false;
  if ("draftSequence" in value && "draftId" in value && "actionCursor" in value && !("proof" in value)) {
    const parts = [value.draftId, value.draftSequence, value.draftSha256];
    if (parts.some(item => item === null) && !parts.every(item => item === null)) return false;
  }
  if ("historyOutbox" in value && list(value.historyOutbox).length + list(value.outbox).length > 100) return false;
  if ("canonicalReady" in value) {
    if (!record(value.response) || !record(value.response.workspace) || !record(value.writer)) return false;
    const workspace = value.response.workspace, writer = value.writer;
    if (writer.projectId !== workspace.projectId || list(value.drafts).some(item => !record(item)
      || item.projectId !== workspace.projectId || item.lineage !== writer.lineage)) return false;
    if (value.canonicalReady === true ? value.response.durability !== "durable"
      || value.response.savedProjectRevision !== workspace.projectRevision
      || value.response.savedDocumentRevision !== workspace.documentRevision : value.response.durability === "durable") return false;
  }
  if ("savedWire" in value) {
    if (!record(value.job) || !record(value.job.receipt) || !record(value.proposal) || !record(value.proposal.payload)
      || !record(value.ownership) || !record(value.saved) || !record(value.saved.workspace) || !record(value.saved.workspace.project)
      || !record(value.saved.workspace.project.facts) || !record(value.preview) || !record(value.preview.workspace)
      || !record(value.view) || !record(value.view.response) || !record(value.view.response.workspace) || !record(value.view.writer)) return false;
    const receipt = value.job.receipt, workspace = value.saved.workspace;
    if (value.view.canonicalReady !== true || value.saved.durability !== "durable" || value.preview.durability !== "pending"
      || receipt.projectId !== value.view.response.workspace.projectId || receipt.lineage !== value.view.writer.lineage
      || receipt.jobId !== value.job.id || receipt.proposalId !== value.proposal.id || value.proposal.jobId !== value.job.id
      || value.ownership.jobId !== value.job.id || value.ownership.proposalId !== value.proposal.id || value.job.proposalId !== value.proposal.id
      || value.proposal.payloadSha256 !== receipt.proposalSha256 || value.saved.savedProjectRevision !== receipt.projectRevision
      || value.saved.savedDocumentRevision !== receipt.documentRevision || workspace.projectRevision !== receipt.projectRevision
      || workspace.documentRevision !== receipt.documentRevision || value.saved.workspace.project.facts.revision !== receipt.factsRevision
      || value.preview.workspace.projectId !== receipt.projectId || value.batchId !== (value.proposal.payload.kind === "agent_journal" ? value.proposal.payload.batchId : null)
      || !list(workspace.mutationReplay).some(item => record(item) && item.clientMutationId === receipt.clientMutationId
        && item.requestSha256 === receipt.requestSha256 && item.resultingRevision === receipt.projectRevision)) return false;
  }
  if ("execution" in value && "publication" in value && "submission" in value) {
    if (value.undoExpired === true && value.receipt === null) return false;
    if (["saved", "no_change", "none"].includes(String(value.publication)) && value.publicationError !== null && value.publicationError !== undefined) return false;
    if ((value.publication === "saved") !== (value.receipt !== null) || !record(value.submission) || !record(value.submission.identity)) return false;
    const attempts = list(value.attempts), models = list(value.submission.models);
    if (new Set(attempts.map((attempt) => record(attempt) ? attempt.id : null)).size !== attempts.length || attempts.length > models.length) return false;
    for (const [index, attempt] of attempts.entries()) {
      const model = models[index];
      if (!record(attempt) || !record(model) || attempt.stage !== model.stage || attempt.executionGeneration !== value.executionGeneration) return false;
    }
    if (record(value.receipt) && (value.receipt.jobId !== value.id || value.receipt.projectId !== value.submission.identity.projectId ||
        value.receipt.lineage !== value.submission.identity.lineage || value.receipt.proposalId !== value.proposalId)) return false;
    if (!["none", "no_change", "cancelled"].includes(String(value.publication)) && value.proposalId === null) return false;
    if (value.submission.allowEdits === false && value.publication !== "none") return false;
  }
  if ("requestSha256" in value && "snapshots" in value && "identity" in value) {
    if (!record(value.identity) || !record(value.request) || value.identity.requestId !== value.request.clientRequestId) return false;
    const resources: unknown[] = [...list(value.snapshots), ...list(value.sources), ...list(value.findings), ...(value.reply === null ? [] : [value.reply])];
    if (resources.some((item) => !record(item) || item.runId !== value.jobId)) return false;
    if (value.jobId === null && (resources.length > 0 || list(value.batches).length > 0 || value.usage !== null ||
        value.observedGuards !== undefined && value.observedGuards !== null ||
        value.preparedGuards !== undefined && value.preparedGuards !== null)) return false;
    if (record(value.reply) && value.reply.role !== "assistant") return false;
    for (const item of list(value.batches)) {
      if (!record(item) || item.receipt !== null || item.publication !== undefined && item.publication !== null || list(item.historyActions).length > 0 ||
          record(item.batch) && (item.batch.runId !== value.jobId || item.batch.state !== "prepared")) return false;
    }
  }
  if ("publication" in value && record(value.run) && (value.jobId !== value.run.id || !validateAgentShape("agent_run", value.run))) return false;
  if ("jobs" in value && "requestEpoch" in value) {
    const jobs = list(value.jobs);
    if (new Set(jobs.map((job) => record(job) ? job.id : null)).size !== jobs.length || jobs.some((job) => !record(job) ||
        !record(job.submission) || !record(job.submission.identity) || job.submission.identity.projectId !== value.projectId || job.submission.identity.lineage !== value.lineage)) return false;
  }
  if ("events" in value && !("request" in value)) {
    const events = list(value.events), first = events[0];
    const cursors = events.map((event) => record(event) ? event.cursor : null);
    if (new Set(cursors).size !== cursors.length || cursors.some((cursor, index) => index > 0 && typeof cursor === "number" && typeof cursors[index - 1] === "number" && cursor <= Number(cursors[index - 1]))) return false;
    if (record(first) && events.some((event) => !record(event) || ["projectId", "lineage", "jobId", "generation"].some((key) => event[key] !== first[key]) || events.length > 1 && event.type === "cursor.gap")) return false;
  }
  if ("nativeStarted" in value && ((value.nativeStarted === true) !== (value.childStartedAt !== null) ||
      (value.cleanupVerified === true && ["reserved", "starting", "running", "cleanup_failed"].includes(String(value.state))))) return false;
  if (value.disposition === "saved" && value.schemaVersion === 2 &&
      (!record(value.result) || !record(value.result.receipt) || value.result.receipt.durable !== true || !validateAgentShape("agent_commit_result", value.result))) return false;
  if (value.disposition === "saved" && value.schemaVersion === 3 &&
      (!record(value.receipt) || value.receipt.durable !== true || !validateAgentShape("agent_edit_receipt", value.receipt))) return false;
  if ("snapshot" in value && "cursor" in value) {
    if (!record(value.snapshot) || !record(value.snapshot.submission) || !record(value.snapshot.submission.identity) ||
        value.snapshot.id !== value.jobId || value.snapshot.submission.identity.projectId !== value.projectId ||
        value.snapshot.submission.identity.lineage !== value.lineage || value.snapshot.eventCursor !== value.cursor || value.snapshot.executionGeneration !== value.generation) return false;
  }
  if ("candidateRef" in value) {
    const count = [value.writerEpoch, value.incarnation, value.barrierGeneration].filter((item) => item !== null).length;
    if (count !== 0 && count !== 3) return false;
    if (value.candidatePruned === true && (value.phase !== "receipt_stored" ||
        value.actionId === null || value.actionId === undefined || value.stepsSha256 === null || value.stepsSha256 === undefined)) return false;
  }
  if ("references" in value && "owner" in value) {
    const references = list(value.references);
    if (new Set(references.map((item) => record(item) ? JSON.stringify([item.kind, item.path]) : null)).size !== references.length) return false;
  }
  if ("path" in value && "sha256" in value && ["image", "source"].includes(String(value.kind))) {
    const path = String(value.path);
    const pattern = value.kind === "image" ? /^images\/[0-9a-f]{64}\.(?:png|jpg)$/u : /^sources\/[0-9a-f]{64}\.bin$/u;
    if (pattern.exec(path)?.[0] !== path || value.kind === "image" && path.slice(7, 71) !== value.sha256) return false;
  }
  if ("inverseRef" in value) {
    if ((value.writerEpoch === null) !== (value.incarnation === null) ||
        (value.owner === "session" && value.writerEpoch === null) ||
        (["backend", "expired"].includes(String(value.owner)) && value.writerEpoch !== null)) return false;
    const command = [value.commandRef ?? null, value.commandInverseSha256 ?? null, value.commandInverseBytes ?? null];
    if (command.some(item => item === null) && !command.every(item => item === null)) return false;
  }
  if ("namespace" in value && "definitions" in value) {
    const definitions = list(value.definitions);
    if (new Set(definitions.map((item) => record(item) ? item.key : null)).size !== definitions.length) return false;
  }
  if ("activeRequestEpoch" in value) {
    if (typeof value.activeRequestEpoch !== "number" || typeof value.expiredThroughEpoch !== "number" || value.activeRequestEpoch <= value.expiredThroughEpoch) return false;
    const groups = ["jobs", "requests", "proposals", "drafts", "generations", "intents", "inverses", "manualIntents", "assetPins", "orphanAssets", "cleanupRefs", "writerTouches", "historyCommands", "fixedInvalidations"];
    const invalidations = list(value.fixedInvalidations);
    if (new Set(invalidations.map(item => record(item) ? JSON.stringify([item.requestEpoch, item.sessionId, item.actionId, item.actionToken]) : null)).size !== invalidations.length
      || invalidations.some(item => !record(item) || Number(item.requestEpoch) > Number(value.activeRequestEpoch))) return false;
    const historyRecords = record(value.history) ? 1 + list(value.history.definitions).length : 0;
    if (groups.reduce((count, key) => count + list(value[key]).length, 0) + Number(value.writer !== null) + Number(value.barrier !== null) + historyRecords > background_sidecar_v1["x-maxMetadataRecords"]) return false;
    if (record(value.history) && value.historyNamespace !== undefined && value.historyNamespace !== null && value.historyNamespace !== value.history.namespace) return false;
    const pins = list(value.assetPins), orphans = list(value.orphanAssets), cleanup = list(value.cleanupRefs);
    if (new Set(pins.map((pin) => record(pin) ? JSON.stringify([pin.kind, pin.owner]) : null)).size !== pins.length ||
        new Set(orphans.map((orphan) => record(orphan) ? orphan.path : null)).size !== orphans.length || new Set(cleanup).size !== cleanup.length) return false;
    if (cleanup.some((reference) => typeof reference !== "string" ||
        /^(?:canonical-candidates|agent-artifacts|proposal-intents|events|drafts|fixed-inputs|processing-candidates)\/[A-Za-z0-9_-]{1,128}\.json$/u.exec(reference)?.[0] !== reference)) return false;
    const scoped: unknown[] = [value.writer, value.barrier, ...["jobs", "requests", "proposals", "drafts", "intents", "manualIntents"].flatMap((key) => list(value[key]))].filter((item) => item !== null);
    for (const item of scoped) {
      if (!record(item)) return false;
      const identity: unknown = record(item.submission) ? item.submission.identity : record(item.identity) ? item.identity : item;
      if (!record(identity) || identity.projectId !== value.projectId || identity.lineage !== value.lineage) return false;
    }
    const requests = list(value.requests), jobs = list(value.jobs);
    if (new Set(requests.map((request) => record(request) && record(request.identity) ? JSON.stringify([request.identity.requestEpoch, request.identity.requestId]) : null)).size !== requests.length ||
        new Set(jobs.map((job) => record(job) ? job.id : null)).size !== jobs.length) return false;
    const sameIdentity = (a: unknown, b: unknown): boolean => record(a) && record(b) &&
      ["projectId", "lineage", "requestEpoch", "requestId"].every((key) => a[key] === b[key]);
    for (const job of jobs) {
      if (!record(job) || !record(job.submission)) return false;
      const request = requests.find((item) => record(item) && item.jobId === job.id);
      if (!record(request) || request.archivedResult !== null || !sameIdentity(request.identity, job.submission.identity) || request.payloadSha256 !== job.submission.payloadSha256) return false;
    }
    for (const request of requests) {
      if (!record(request)) return false;
      const archived = request.archivedResult;
      if (record(archived) && (!record(archived.submission) || archived.id !== request.jobId || !sameIdentity(archived.submission.identity, request.identity) ||
          archived.submission.payloadSha256 !== request.payloadSha256 || !["completed", "failed", "cancelled", "interrupted"].includes(String(archived.execution)) ||
          !["none", "saved", "no_change", "discarded", "cancelled"].includes(String(archived.publication)))) return false;
    }
  }
  return Object.values(value).every(semantics);
}
export function validateBackgroundShape(kind: string, value: unknown): boolean {
  let validate = validators.get(kind);
  if (validate === undefined) {
    const schema = schemas.get(kind);
    if (schema === undefined) return false;
    validate = ajv.compile<unknown>(schema);
    validators.set(kind, validate);
  }
  return validate(value) && semantics(value);
}

async function proofBytes(value: Record<string, unknown>): Promise<boolean> {
  if (typeof value.workspaceWire === "string") {
    if (!record(value.response) || await sha256(value.workspaceWire) !== value.workspaceSha256
      || !sameValue(JSON.parse(value.workspaceWire), value.response.workspace)) return false;
    if (typeof value.mutationWire === "string") {
      const mutation: unknown = JSON.parse(value.mutationWire), workspace = value.response.workspace;
      if (!mutationShape(mutation) || !record(mutation) || !record(workspace) || mutation.projectId !== workspace.projectId) return false;
      const checksum = await sha256(value.mutationWire);
      if (!list(workspace.mutationReplay).some(item => record(item) && item.clientMutationId === mutation.clientMutationId
        && item.requestSha256 === checksum && typeof item.resultingRevision === "number" && typeof workspace.projectRevision === "number"
        && item.resultingRevision <= workspace.projectRevision)) return false;
    }
  }
  if (typeof value.savedWire === "string") {
    if (!record(value.job) || !record(value.job.receipt) || !record(value.saved) || !record(value.ownership)
      || typeof value.mutationWire !== "string" || await sha256(value.savedWire) !== value.job.receipt.workspaceSha256
      || !sameValue(JSON.parse(value.savedWire), value.saved.workspace)
      || await sha256(value.mutationWire) !== (value.ownership.commandInverseSha256 ?? value.ownership.inverseSha256)
      || new TextEncoder().encode(value.mutationWire).length !== (value.ownership.commandInverseBytes ?? value.ownership.inverseBytes)) return false;
    const mutation: unknown = JSON.parse(value.mutationWire);
    if (!record(mutation) || !record(value.saved.workspace) || mutation.projectId !== value.saved.workspace.projectId) return false;
  }
  return true;
}

async function exactBytes(value: unknown): Promise<boolean> {
  const proofs: Record<string, unknown>[] = [];
  const visit = (item: unknown): void => {
    if (Array.isArray(item)) item.forEach(visit);
    else if (record(item)) {
      if ("workspaceWire" in item || "savedWire" in item) proofs.push(item);
      Object.values(item).forEach(visit);
    }
  };
  visit(value);
  return (await Promise.all(proofs.map(proofBytes))).every(Boolean);
}

export async function validateBackgroundWire(kind: string, value: unknown): Promise<boolean> {
  try { return validateBackgroundShape(kind, value) && await exactBytes(value); }
  catch { return false; }
}
