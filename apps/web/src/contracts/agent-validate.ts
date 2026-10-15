import { Ajv2020 } from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv";
import addFormats from "ajv-formats";
import agent_error from "../../../../contracts/json-schema/agent_error.schema.json" with { type: "json" };
import agent_capabilities from "../../../../contracts/json-schema/agent_capabilities.schema.json" with { type: "json" };
import agent_settings from "../../../../contracts/json-schema/agent_settings.schema.json" with { type: "json" };
import agent_settings_request from "../../../../contracts/json-schema/agent_settings_request.schema.json" with { type: "json" };
import agent_conversation from "../../../../contracts/json-schema/agent_conversation.schema.json" with { type: "json" };
import agent_message from "../../../../contracts/json-schema/agent_message.schema.json" with { type: "json" };
import agent_run_request from "../../../../contracts/json-schema/agent_run_request.schema.json" with { type: "json" };
import agent_run from "../../../../contracts/json-schema/agent_run.schema.json" with { type: "json" };
import agent_read_snapshot from "../../../../contracts/json-schema/agent_read_snapshot.schema.json" with { type: "json" };
import agent_web_source from "../../../../contracts/json-schema/agent_web_source.schema.json" with { type: "json" };
import agent_finding from "../../../../contracts/json-schema/agent_finding.schema.json" with { type: "json" };
import agent_prepare_request from "../../../../contracts/json-schema/agent_prepare_request.schema.json" with { type: "json" };
import agent_prepare_result from "../../../../contracts/json-schema/agent_prepare_result.schema.json" with { type: "json" };
import agent_apply_request from "../../../../contracts/json-schema/agent_apply_request.schema.json" with { type: "json" };
import agent_edit_batch from "../../../../contracts/json-schema/agent_edit_batch.schema.json" with { type: "json" };
import agent_edit_receipt from "../../../../contracts/json-schema/agent_edit_receipt.schema.json" with { type: "json" };
import agent_event from "../../../../contracts/json-schema/agent_event.schema.json" with { type: "json" };
import agent_page_request from "../../../../contracts/json-schema/agent_page_request.schema.json" with { type: "json" };
import agent_conversation_page from "../../../../contracts/json-schema/agent_conversation_page.schema.json" with { type: "json" };
import agent_message_page from "../../../../contracts/json-schema/agent_message_page.schema.json" with { type: "json" };
import agent_resource_page from "../../../../contracts/json-schema/agent_resource_page.schema.json" with { type: "json" };
import agent_lease_open from "../../../../contracts/json-schema/agent_lease_open.schema.json" with { type: "json" };
import agent_lease from "../../../../contracts/json-schema/agent_lease.schema.json" with { type: "json" };
import agent_owner_request from "../../../../contracts/json-schema/agent_owner_request.schema.json" with { type: "json" };
import agent_commit_request from "../../../../contracts/json-schema/agent_commit_request.schema.json" with { type: "json" };
import agent_claim_result from "../../../../contracts/json-schema/agent_claim_result.schema.json" with { type: "json" };
import agent_result_request from "../../../../contracts/json-schema/agent_result_request.schema.json" with { type: "json" };
import agent_events_request from "../../../../contracts/json-schema/agent_events_request.schema.json" with { type: "json" };
import agent_run_read from "../../../../contracts/json-schema/agent_run_read.schema.json" with { type: "json" };
import agent_tool_read from "../../../../contracts/json-schema/agent_tool_read.schema.json" with { type: "json" };
import agent_tool_result from "../../../../contracts/json-schema/agent_tool_result.schema.json" with { type: "json" };
import agent_fetch_request from "../../../../contracts/json-schema/agent_fetch_request.schema.json" with { type: "json" };
import agent_publish_findings from "../../../../contracts/json-schema/agent_publish_findings.schema.json" with { type: "json" };
import agent_project_state from "../../../../contracts/json-schema/agent_project_state.schema.json" with { type: "json" };

import agent_empty_request from "../../../../contracts/json-schema/agent_empty_request.schema.json" with { type: "json" };

const encoder = new TextEncoder();
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addKeyword({ keyword: "x-maxSerializedBytes", schemaType: "number",
  validate: (limit: number, value: unknown): boolean => {
    const json = JSON.stringify(value);
    return json !== undefined && encoder.encode(json).length <= limit;
  } });
ajv.addKeyword({ keyword: "x-maxUtf8Bytes", schemaType: "number", type: "string",
  validate: (limit: number, value: string): boolean => encoder.encode(value).length <= limit });
const schemas = { agent_error, agent_empty_request, agent_capabilities, agent_settings, agent_settings_request, agent_conversation, agent_message, agent_run_request, agent_run, agent_read_snapshot, agent_web_source, agent_finding, agent_prepare_request, agent_prepare_result, agent_apply_request, agent_edit_batch, agent_edit_receipt, agent_event, agent_page_request, agent_conversation_page, agent_message_page, agent_resource_page, agent_lease_open, agent_lease, agent_owner_request, agent_commit_request, agent_claim_result, agent_result_request, agent_events_request, agent_run_read, agent_tool_read, agent_tool_result, agent_fetch_request, agent_publish_findings, agent_project_state };
const schemaByName = new Map<string, object>(Object.entries(schemas));
const validators = new Map<string, ValidateFunction<unknown>>();

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function ids(value: unknown): Set<unknown> {
  return new Set(list(value).map((item: unknown) => record(item) ? item.id : undefined));
}

function conversationReferences(value: Record<string, unknown>): boolean {
  for (const name of ["messages", "runs", "sources", "findings"]) {
    if (ids(value[name]).size !== list(value[name]).length) return false;
  }
  const runs = ids(value.runs);
  const sources = ids(value.sources);
  const findings = ids(value.findings);
  if (list(value.runs).filter((run: unknown) => record(run) && typeof run.state === "string" &&
      !["completed", "failed", "cancelled", "interrupted"].includes(run.state)).length > 1) return false;
  if (list(value.runs).some((run: unknown) => !record(run) ||
      run.conversationId !== value.id || run.projectId !== value.projectId)) return false;
  if ([...list(value.messages), ...list(value.sources), ...list(value.findings)]
    .some((item: unknown) => !record(item) || !runs.has(item.runId))) return false;
  for (const message of list(value.messages)) {
    if (!record(message) || list(message.sources).some((ref: unknown) => !record(ref) || !sources.has(ref.id)) ||
        list(message.findings).some((ref: unknown) => !record(ref) || !findings.has(ref.id))) return false;
  }
  return list(value.findings).every((finding: unknown) => record(finding) &&
    list(finding.sourceIds).every((id: unknown) => sources.has(id)));
}

function semantics(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(semantics);
  if (!record(value)) return true;
  if ("messages" in value && "runs" in value && !conversationReferences(value)) return false;
  if ((value.role === "user" || value.role === "assistant") &&
      (ids(value.sources).size !== list(value.sources).length || ids(value.findings).size !== list(value.findings).length)) return false;
  if ("start" in value && "end" in value && (value.start === null) !== (value.end === null)) return false;
  if (typeof value.start === "number" && typeof value.end === "number" && value.end < value.start) return false;
  if (typeof value.state === "string" && "finishedAt" in value) {
    const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(value.state);
    if (terminal !== (value.finishedAt !== null)) return false;
    if (value.state === "completed" && (value.error !== null || value.outcomeUnknown === true)) return false;
    if (value.allowEdits === false && (value.savedBatchId !== null || value.outcomeUnknown === true)) return false;
  }
  if ("durable" in value && "disposition" in value) {
    if (value.durable !== (value.disposition === "saved")) return false;
    if (value.durable === true && (value.error !== null || value.projectRevision === null ||
        value.documentRevision === null || value.factsRevision === null)) return false;
  }
  if (value.disposition === "no_change" && value.batchId !== null) return false;
  if (value.disposition === "prepared" && "batchId" in value && value.batchId === null) return false;
  if ((value.status === "known" || value.status === "uncertain") && "text" in value && "value" in value &&
      (value.status === "uncertain") !== (value.value === null)) return false;
  if ("mutation" in value && record(value.mutation) && value.mutation.kind !== "structure") return false;
  return Object.values(value).every(semantics);
}

export function validateAgentShape(kind: string, value: unknown): boolean {
  try {
    let validate = validators.get(kind);
    if (validate === undefined) {
      const schema = schemaByName.get(kind);
      if (schema === undefined) return false;
      validate = ajv.compile<unknown>(schema);
      validators.set(kind, validate);
    }
    return validate(value) && semantics(value);
  } catch {
    return false;
  }
}
