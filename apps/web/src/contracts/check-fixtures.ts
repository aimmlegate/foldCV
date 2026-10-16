import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { validateContract, validateExtractResult, validateFactRequest, validateFactSheet,
  validateRenderRequest, validateSemanticProposal, validateDraftRequest, validateDraftProposal, validateDraftResult } from "./validate.js";

type Edit = { op: "set" | "remove" | "append" | "clone" | "repeat_text" | "fill_sidebar"; path: (string | number)[]; value?: unknown; from?: (string | number)[]; text?: string; count?: number; repeat?: number; items?: number; sections?: number };
type Case = { name: string; contract: string; base: string; valid: boolean; edits: Edit[] };

const here = dirname(fileURLToPath(import.meta.url));
const examples = resolve(here, "../../../../contracts/examples");
function read(name: string): unknown {
  return JSON.parse(readFileSync(resolve(examples, name), "utf8")) as unknown;
}
function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("fixture object expected");
  return value as Record<string, unknown>;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error("fixture array expected");
  return value as unknown[];
}
function child(value: unknown, key: string | number): unknown {
  return typeof key === "number" ? array(value)[key] : record(value)[key];
}
function edit(data: unknown, change: Edit): void {
  const parent = change.path.slice(0, -1).reduce<unknown>((value, key) => child(value, key), data);
  const key = change.path.at(-1);
  if (key === undefined) throw new Error("empty edit path");
  if (change.op === "clone") {
    if (change.from === undefined) throw new Error("clone source missing");
    const source = change.from.reduce<unknown>((value, part) => child(value, part), data);
    array(child(parent, key)).push(structuredClone(source));
    return;
  }
  if (change.op === "repeat_text") {
    if (change.text === undefined || change.count === undefined) throw new Error("repeat data missing");
    if (typeof key === "number") array(parent)[key] = change.text.repeat(change.count);
    else record(parent)[key] = change.text.repeat(change.count);
    return;
  }
  if (change.op === "fill_sidebar") {
    if (change.text === undefined || change.repeat === undefined || change.items === undefined || change.sections === undefined) throw new Error("sidebar data missing");
    record(parent)[String(key)] = Array.from({ length: change.sections }, () => ({ title: "T", items: Array.from({ length: change.items! }, () => change.text!.repeat(change.repeat!)) }));
    return;
  }
  if (change.op === "append") { array(child(parent, key)).push(change.value); return; }
  if (typeof key === "number") {
    const target = array(parent);
    if (change.op === "remove") target.splice(key, 1);
    else target[key] = change.value;
  } else {
    const target = record(parent);
    if (change.op === "remove") delete target[key];
    else target[key] = change.value;
  }
}
const project = read("project.json");
const zip = read("zip_manifest.json");
const archive = read("archive_manifest.json");
const render = read("render_request.json");
const prepare = read("prepare_request.json");
const extract = read("extract_result.json");
const bases: Record<string, unknown> = { project, proposal: child(child(project, "proposals"), 0), template: child(project, "template"), zip_manifest: zip, archive_manifest: archive, render_request: render, prepare_request: prepare, extract_result: extract,
  fact_request: read("fact_request.json"), fact_sheet: read("fact_sheet.json"), semantic_proposal: read("semantic_proposal.json"),
  draft_request: read("draft_request.json"), draft_proposal: read("draft_proposal.json"), draft_result: read("draft_result.json") };
for (const name of ["project_v4", "workspace_v5", "archive_manifest_v5", "render_snapshot_v4", "mutation", "mutation_result", "document", "preferences", "registry", "rules", "selection", "source_context", "source_context_request", "editorial_plan", "save_rules_request", "rules_settings_error", "rules_settings", "gui_normalize_request", "gui_semantic_proposal", "gui_normalized_result", "gui_draft_request", "gui_draft_proposal", "gui_draft_result", "gui_create_project_request", "gui_start_generation_request", "gui_project_response", "gui_rename_project_request"]) {
  bases[name] = read(`recovery/${name}.json`);
}
const cases = array(read("cases.json")) as Case[];
bases.rich_panel_request = read("recovery/rich_panel_request.json");
for (const name of ["agent_settings", "agent_run_request", "agent_message", "agent_web_source", "agent_finding", "agent_conversation",
  "agent_commit_result", "agent_event", "agent_prepare_request", "agent_prepare_result", "agent_edit_receipt", "agent_run", "agent_read_snapshot"]) {
  bases[name] = read(`agent/${name}.json`);
}
for (const name of ["background_submission_v1", "background_snapshot_v1", "background_proposal_v1", "background_scope_guard_v1",
  "background_writer_v1", "background_barrier_v1", "background_draft_v1", "background_receipt_v1", "background_apply_v2", "background_event_v1", "background_saved_v2",
  "background_intent_v1", "background_undo_v1", "background_sidecar_v1", "background_attempt_v1", "background_draft_payload_v1", "background_saved_snapshot_v1", "background_dispatch_v1", "background_agent_request_v1", "background_artifact_v1", "background_legacy_run_v2", "background_project_v1", "background_replay_request_v1", "background_replay_v1",
  "background_history_sidecar_v1", "background_manual_sidecar_v1", "background_history_metadata_full_v1",
  "background_asset_sidecar_v1", "background_compact_manual_v1"]) {
  bases[name] = read(`background/${name}.json`);
}
for (const test of cases) {
  const source = bases[test.base];
  if (source === undefined) throw new Error(`unknown fixture base ${test.base}`);
  const data: unknown = structuredClone(source);
  for (const change of test.edits) edit(data, change);
  const valid = test.contract === "render_request" ? await validateRenderRequest(data)
    : test.contract === "extract_result" ? validateExtractResult(data)
      : test.contract === "fact_request" ? validateFactRequest(data)
        : test.contract === "fact_sheet" ? validateFactSheet(data)
          : test.contract === "semantic_proposal" ? validateSemanticProposal(data)
            : test.contract === "draft_request" ? validateDraftRequest(data)
              : test.contract === "draft_proposal" ? validateDraftProposal(data)
                : test.contract === "draft_result" ? validateDraftResult(data)
            : validateContract(test.contract, data);
  assert.equal(valid, test.valid, test.name);
}
process.stdout.write(`${cases.length} shared browser contract cases passed\n`);
