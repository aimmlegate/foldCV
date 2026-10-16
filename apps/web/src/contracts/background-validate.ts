import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { validateAgentShape } from "./agent-validate.js";
import background_submission_v1 from "../../../../contracts/json-schema/background_submission_v1.schema.json" with { type: "json" };
import background_snapshot_v1 from "../../../../contracts/json-schema/background_snapshot_v1.schema.json" with { type: "json" };
import background_proposal_v1 from "../../../../contracts/json-schema/background_proposal_v1.schema.json" with { type: "json" };
import background_scope_guard_v1 from "../../../../contracts/json-schema/background_scope_guard_v1.schema.json" with { type: "json" };
import background_writer_v1 from "../../../../contracts/json-schema/background_writer_v1.schema.json" with { type: "json" };
import background_barrier_v1 from "../../../../contracts/json-schema/background_barrier_v1.schema.json" with { type: "json" };
import background_draft_v1 from "../../../../contracts/json-schema/background_draft_v1.schema.json" with { type: "json" };
import background_receipt_v1 from "../../../../contracts/json-schema/background_receipt_v1.schema.json" with { type: "json" };
import background_apply_v2 from "../../../../contracts/json-schema/background_apply_v2.schema.json" with { type: "json" };
import background_event_v1 from "../../../../contracts/json-schema/background_event_v1.schema.json" with { type: "json" };
import background_intent_v1 from "../../../../contracts/json-schema/background_intent_v1.schema.json" with { type: "json" };
import background_undo_v1 from "../../../../contracts/json-schema/background_undo_v1.schema.json" with { type: "json" };
import background_sidecar_v1 from "../../../../contracts/json-schema/background_sidecar_v1.schema.json" with { type: "json" };
import background_attempt_v1 from "../../../../contracts/json-schema/background_attempt_v1.schema.json" with { type: "json" };
import background_draft_payload_v1 from "../../../../contracts/json-schema/background_draft_payload_v1.schema.json" with { type: "json" };

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addKeyword({ keyword: "x-maxSerializedBytes", schemaType: "number",
  validate: (limit: number, value: unknown): boolean => new TextEncoder().encode(JSON.stringify(value)).length <= limit });
const schemas = new Map<string, object>(Object.entries({ background_submission_v1, background_snapshot_v1,
  background_proposal_v1, background_scope_guard_v1, background_writer_v1, background_barrier_v1,
  background_draft_v1, background_receipt_v1, background_apply_v2, background_event_v1, background_intent_v1,
  background_undo_v1, background_sidecar_v1, background_attempt_v1, background_draft_payload_v1 }));
const validators = new Map<string, ValidateFunction<unknown>>();
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
  if ("execution" in value && "publication" in value) {
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
  if ("nativeStarted" in value && ((value.nativeStarted === true) !== (value.childStartedAt !== null) ||
      (value.cleanupVerified === true && ["reserved", "starting", "running", "cleanup_failed"].includes(String(value.state))))) return false;
  if (value.disposition === "saved" && value.schemaVersion === 2 &&
      (!record(value.result) || !record(value.result.receipt) || value.result.receipt.durable !== true || !validateAgentShape("agent_commit_result", value.result))) return false;
  if ("snapshot" in value && "cursor" in value) {
    if (!record(value.snapshot) || !record(value.snapshot.submission) || !record(value.snapshot.submission.identity) ||
        value.snapshot.id !== value.jobId || value.snapshot.submission.identity.projectId !== value.projectId ||
        value.snapshot.submission.identity.lineage !== value.lineage || value.snapshot.eventCursor !== value.cursor || value.snapshot.executionGeneration !== value.generation) return false;
  }
  if ("candidateRef" in value) {
    const count = [value.writerEpoch, value.incarnation, value.barrierGeneration].filter((item) => item !== null).length;
    if (count !== 0 && count !== 3) return false;
  }
  if ("inverseRef" in value) {
    if ((value.writerEpoch === null) !== (value.incarnation === null) ||
        (value.owner === "session" && value.writerEpoch === null) ||
        (["backend", "expired"].includes(String(value.owner)) && value.writerEpoch !== null)) return false;
  }
  if ("activeRequestEpoch" in value) {
    if (typeof value.activeRequestEpoch !== "number" || typeof value.expiredThroughEpoch !== "number" || value.activeRequestEpoch <= value.expiredThroughEpoch) return false;
    const groups = ["jobs", "requests", "proposals", "drafts", "generations", "intents", "inverses"];
    if (groups.reduce((count, key) => count + list(value[key]).length, 0) + Number(value.writer !== null) + Number(value.barrier !== null) > background_sidecar_v1["x-maxMetadataRecords"]) return false;
    const scoped: unknown[] = [value.writer, value.barrier, ...["jobs", "requests", "proposals", "drafts", "intents"].flatMap((key) => list(value[key]))].filter((item) => item !== null);
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
