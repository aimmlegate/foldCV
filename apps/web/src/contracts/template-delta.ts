import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import deltaSchema from "../../../../contracts/json-schema/template_prepared_edit_delta_v1.schema.json" with { type: "json" };
import mutationSchema from "../../../../contracts/json-schema/template_mutation_v1.schema.json" with { type: "json" };
import { sha256 } from "../background/wire";
import type { TemplatePreparedEditDeltaV1 } from "./generated/template_prepared_edit_delta_v1";
import type { TemplateProjectResponseV1 } from "./generated/template_project_response_v1";
import type { TemplateMutationV1 } from "./generated/template_mutation_v1";
import { applyVerifiedCanonicalPatch } from "./canonical-patch";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "./lossless-json";
import { taggedSchema } from "./tagged-schema";
import { templateProjectWire } from "./template-validate";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const deltaShape = ajv.compile<TemplatePreparedEditDeltaV1>(taggedSchema(deltaSchema));
const mutationShape = ajv.compile<TemplateMutationV1>(taggedSchema(mutationSchema));

export type ExpectedTemplateDelta = Pick<TemplatePreparedEditDeltaV1, "clientMutationId" | "requestHash" | "capture" | "baseSnapshot">;
export type TemplateDeltaAdoption = {
  delta: TemplatePreparedEditDeltaV1;
  response: TemplateProjectResponseV1;
  responseWire: JsonWireNode;
  workspaceWire: JsonWireNode;
};

function invalid(): never { throw new Error("INVALID_RESULT"); }
function expectedWire(value: unknown): string {
  const wire = JSON.stringify(value);
  return typeof wire === "string" ? parseJsonWire(wire).wire : invalid();
}

export async function applyPreparedTemplateDelta(baseInput: JsonWireNode, deltaInput: JsonWireNode,
  expected: ExpectedTemplateDelta): Promise<TemplateDeltaAdoption> {
  // Own the decoded trees before awaiting so values cannot drift from verified bytes.
  const base = parseJsonWire(baseInput.wire), root = parseJsonWire(deltaInput.wire);
  const expectedId = expected.clientMutationId, expectedHash = expected.requestHash;
  const expectedCapture = expectedWire(expected.capture), expectedSnapshot = expectedWire(expected.baseSnapshot);
  const delta = root.value;
  if (!deltaShape(delta)) return invalid();
  const original = await templateProjectWire(base);
  if (!original || original.durability !== "durable" || !original.presentation || !original.workspace.project
    || delta.clientMutationId !== expectedId || delta.requestHash !== expectedHash
    || jsonWireAt(root, ["capture"]).wire !== expectedCapture
    || jsonWireAt(root, ["baseSnapshot"]).wire !== expectedSnapshot
    || jsonWireAt(base, ["snapshot"]).wire !== jsonWireAt(root, ["baseSnapshot"]).wire
    || delta.baseSnapshot.projectId !== delta.resultSnapshot.projectId
    || delta.baseSnapshot.packageHash !== delta.resultSnapshot.packageHash) return invalid();
  const ids = Object.values(delta.createdIds).flatMap(slots => Object.values(slots));
  if (new Set(ids).size !== ids.length) return invalid();
  const workspace = await applyVerifiedCanonicalPatch(jsonWireAt(base, ["workspace"]), delta.workspacePatch,
    delta.baseWorkspaceSha256, delta.resultWorkspaceSha256);
  const references = jsonWireAt(base, ["presentation", "blocks"]), patch = delta.presentationPatch;
  if (await sha256(references.wire) !== patch.beforeHash || new Set(patch.remove).size !== patch.remove.length) return invalid();
  const blocks = new Map(references.children);
  for (const key of patch.remove) {
    if (!blocks.delete(key) || Object.hasOwn(patch.set, key)) return invalid();
  }
  for (const key of Object.keys(patch.set)) blocks.set(key, jsonWireAt(root, ["presentationPatch", "set", key]));
  const blocksWire = jsonObjectWire([...blocks].map(([key, value]) => {
    if (typeof key !== "string") return invalid();
    return [key, value.wire];
  }));
  if (await sha256(blocksWire) !== patch.afterHash
    || jsonWireAt(workspace, ["project", "templatePackage"]).wire
      !== jsonWireAt(base, ["workspace", "project", "templatePackage"]).wire) return invalid();
  if (delta.mutationWire === null) {
    if (delta.workspacePatch.length || Object.keys(patch.set).length || patch.remove.length || ids.length
      || delta.baseWorkspaceSha256 !== delta.resultWorkspaceSha256
      || jsonWireAt(root, ["baseSnapshot"]).wire !== jsonWireAt(root, ["resultSnapshot"]).wire
      || jsonWireAt(root, ["resultIdentity"]).wire !== jsonWireAt(base, ["identity"]).wire
      || jsonWireAt(root, ["resultGeneration"]).wire !== jsonWireAt(base, ["generation"]).wire) return invalid();
    return { delta, response: original, responseWire: base, workspaceWire: workspace };
  }
  const mutation = parseJsonWire(delta.mutationWire);
  if (!mutationShape(mutation.value) || mutation.value.clientMutationId !== delta.clientMutationId
    || mutation.value.projectId !== delta.baseSnapshot.projectId || mutation.value.history.kind !== "edit"
    || jsonWireAt(mutation, ["capture"]).wire !== jsonWireAt(root, ["capture"]).wire
    || delta.resultSnapshot.projectRevision <= delta.baseSnapshot.projectRevision
    || delta.resultSnapshot.documentRevision <= delta.baseSnapshot.documentRevision) return invalid();
  const presentation = jsonObjectWire([["schemaVersion", "1"], ["snapshot", jsonWireAt(root, ["resultSnapshot"]).wire],
    ["recipe", jsonWireAt(base, ["presentation", "recipe"]).wire], ["blocks", blocksWire]]);
  const responseWire = parseJsonWire(jsonObjectWire([
    ["schemaVersion", "1"], ["workspace", workspace.wire], ["snapshot", jsonWireAt(root, ["resultSnapshot"]).wire],
    ["presentation", presentation], ["durability", '"pending"'], ["saveError", "null"],
    ["savedProjectRevision", jsonWireAt(base, ["savedProjectRevision"]).wire],
    ["savedDocumentRevision", jsonWireAt(base, ["savedDocumentRevision"]).wire],
    ["identity", jsonWireAt(root, ["resultIdentity"]).wire], ["generation", jsonWireAt(root, ["resultGeneration"]).wire],
  ]));
  const response = await templateProjectWire(responseWire);
  if (!response) return invalid();
  return { delta, response, responseWire, workspaceWire: workspace };
}
