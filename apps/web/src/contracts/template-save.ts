import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import resultSchema from "../../../../contracts/json-schema/background_writer_prepared_save_result_v2.schema.json" with { type: "json" };
import deltaSchema from "../../../../contracts/json-schema/template_prepared_edit_delta_v1.schema.json" with { type: "json" };
import mutationSchema from "../../../../contracts/json-schema/template_mutation_v1.schema.json" with { type: "json" };
import type { WriterPreparedSaveResultV2 } from "./generated/background_writer_prepared_save_result_v2";
import type { TemplatePreparedEditDeltaV1 } from "./generated/template_prepared_edit_delta_v1";
import type { TemplateMutationV1 } from "./generated/template_mutation_v1";
import type { TemplateProjectResponseV1 } from "./generated/template_project_response_v1";
import { sha256 } from "../background/wire";
import { applyVerifiedCanonicalPatch } from "./canonical-patch";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "./lossless-json";
import { taggedSchema } from "./tagged-schema";
import { templateProjectWire } from "./template-validate";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const resultShape = ajv.compile<WriterPreparedSaveResultV2>(taggedSchema(resultSchema));
const deltaShape = ajv.compile<TemplatePreparedEditDeltaV1>(taggedSchema(deltaSchema));
const mutationShape = ajv.compile<TemplateMutationV1>(taggedSchema(mutationSchema));

export type PreparedSaveOpening = {
  projectId: string;
  lineage: string;
  epoch: number;
  sessionId: string;
  incarnation: string;
  actionCursor: number;
  minimumTouchGeneration: number;
};

export type TemplateSaveVerification = {
  kind: "committed";
  acknowledgment: Extract<WriterPreparedSaveResultV2, { kind: "committed" }>;
  response: TemplateProjectResponseV1;
  responseWire: JsonWireNode;
} | {
  kind: "committed_recovery_required";
  acknowledgment: Extract<WriterPreparedSaveResultV2, { kind: "committed_recovery_required" }>;
};

function invalid(): never { throw new Error("INVALID_RESULT"); }

export async function verifyPreparedTemplateSave(previewInput: JsonWireNode, deltaInput: JsonWireNode,
  resultInput: JsonWireNode, openingInput: PreparedSaveOpening): Promise<TemplateSaveVerification> {
  const preview = parseJsonWire(previewInput.wire), deltaRoot = parseJsonWire(deltaInput.wire);
  const root = parseJsonWire(resultInput.wire), opening = { ...openingInput };
  const delta = deltaRoot.value, result = root.value;
  if (!deltaShape(delta) || !resultShape(result) || delta.mutationWire === null) return invalid();
  const mutation = parseJsonWire(delta.mutationWire);
  if (!mutationShape(mutation.value) || mutation.value.clientMutationId !== delta.clientMutationId
    || mutation.value.projectId !== opening.projectId || mutation.value.capture.sessionId !== opening.sessionId
    || mutation.value.history.kind !== "edit"
    || jsonWireAt(mutation, ["capture"]).wire !== jsonWireAt(deltaRoot, ["capture"]).wire) return invalid();
  const original = await templateProjectWire(preview);
  if (!original || original.durability !== "pending" || !original.workspace.project || !original.presentation
    || original.workspace.projectId !== opening.projectId
    || delta.baseSnapshot.projectId !== opening.projectId
    || jsonWireAt(preview, ["snapshot"]).wire !== jsonWireAt(deltaRoot, ["resultSnapshot"]).wire
    || await sha256(jsonWireAt(preview, ["workspace"]).wire) !== delta.resultWorkspaceSha256
    || result.clientMutationId !== delta.clientMutationId || result.preparationRequestHash !== delta.requestHash
    || result.mutationSha256 !== await sha256(delta.mutationWire)
    || result.replay.clientMutationId !== result.clientMutationId || result.replay.requestSha256 !== result.mutationSha256
    || result.replay.resultingRevision !== delta.resultSnapshot.projectRevision
    || result.currentCanonicalRevision < result.replay.resultingRevision
    || result.writer.projectId !== opening.projectId || result.writer.lineage !== opening.lineage
    || result.writer.epoch !== opening.epoch || result.writer.sessionId !== opening.sessionId
    || result.writer.incarnation !== opening.incarnation || result.writer.acknowledgedCursor < opening.actionCursor
    || result.writer.touchGeneration < opening.minimumTouchGeneration) return invalid();
  if (result.kind === "committed_recovery_required") return { kind: result.kind, acknowledgment: result };
  const binding = result.commitBinding;
  if (binding.epoch !== opening.epoch || binding.incarnation !== opening.incarnation
    || binding.actionCursor !== opening.actionCursor || binding.touchGeneration < opening.minimumTouchGeneration
    || binding.touchGeneration > result.writer.touchGeneration || binding.draftId !== null
    || binding.draftSequence !== null || binding.draftSha256 !== null
    || result.preparedWorkspaceSha256 !== delta.resultWorkspaceSha256
    || jsonWireAt(root, ["committedSnapshot"]).wire !== jsonWireAt(deltaRoot, ["resultSnapshot"]).wire
    || result.currentEqualsCommitted !== (result.currentCanonicalRevision === result.committedSnapshot.projectRevision
      && result.currentCanonicalSha256 === result.committedWorkspaceSha256)
    || result.localHistoryAck !== null
      && result.localHistoryAck.actionId !== (mutation.value.history.originActionId ?? mutation.value.actionId)) return invalid();
  const before = jsonWireAt(preview, ["workspace"]);
  const workspace = await applyVerifiedCanonicalPatch(before, result.commitPatch,
    result.preparedWorkspaceSha256, result.committedWorkspaceSha256);
  if (before.children.size !== workspace.children.size || [...before.children].some(([key, node]) =>
    key !== "updatedAt" && node.wire !== workspace.children.get(key)?.wire)) return invalid();
  const responseWire = parseJsonWire(jsonObjectWire([
    ["schemaVersion", "1"], ["workspace", workspace.wire], ["snapshot", jsonWireAt(root, ["committedSnapshot"]).wire],
    ["presentation", jsonWireAt(preview, ["presentation"]).wire], ["durability", '"durable"'], ["saveError", "null"],
    ["savedProjectRevision", jsonWireAt(root, ["committedSnapshot", "projectRevision"]).wire],
    ["savedDocumentRevision", jsonWireAt(root, ["committedSnapshot", "documentRevision"]).wire],
    ["identity", jsonWireAt(root, ["committedIdentity"]).wire], ["generation", jsonWireAt(root, ["committedGeneration"]).wire],
  ]));
  const response = await templateProjectWire(responseWire);
  if (!response) return invalid();
  return { kind: result.kind, acknowledgment: result, response, responseWire };
}
