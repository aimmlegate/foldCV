import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import requestSchema from "../../../../contracts/json-schema/background_writer_prepare_edit_v2.schema.json" with { type: "json" };
import replySchema from "../../../../contracts/json-schema/background_writer_prepared_delta_v2.schema.json" with { type: "json" };
import advanceSchema from "../../../../contracts/json-schema/background_writer_advance_v2.schema.json" with { type: "json" };
import type { WriterPrepareEditV2 } from "./generated/background_writer_prepare_edit_v2";
import type { WriterPreparedDeltaV2 } from "./generated/background_writer_prepared_delta_v2";
import type { WriterAdvanceV2 } from "./generated/background_writer_advance_v2";
import { sha256 } from "../background/wire";
import { jsonResponseWire } from "./json-response";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "./lossless-json";
import { verifyAddressMap, type VerifiedAddressMap } from "./template-address";
import { applyPreparedTemplateDelta, type TemplateDeltaAdoption } from "./template-delta";
import { verifyPreparedTemplateSave, type PreparedSaveOpening, type TemplateSaveVerification } from "./template-save";
import { taggedSchema } from "./tagged-schema";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const requestShape = ajv.compile<WriterPrepareEditV2>(taggedSchema(requestSchema));
const replyShape = ajv.compile<WriterPreparedDeltaV2>(taggedSchema(replySchema));
const advanceShape = ajv.compile<WriterAdvanceV2>(taggedSchema(advanceSchema));
export type BoundTemplatePreparation = {
  requestWire: string;
  replyWire: string;
  prepared: TemplateDeltaAdoption;
  address: VerifiedAddressMap;
};
function invalid(): never { throw new Error("INVALID_RESULT"); }

/** Python binds its normalization to independently hashed, frozen browser input. */
export async function prepareTemplateTransport(project: string, baseInput: JsonWireNode, input: WriterPrepareEditV2,
  send: (request: WriterPrepareEditV2) => Promise<unknown>): Promise<BoundTemplatePreparation> {
  const base = parseJsonWire(baseInput.wire), root = parseJsonWire(JSON.stringify(input));
  if (!requestShape(root.value)) return invalid();
  const request = root.value;
  const inputWire = request.preparationInputWire ?? jsonWireAt(root, ["preparation"]).wire;
  parseJsonWire(inputWire);
  if (request.preparation.snapshot.projectId !== project || request.preparation.capture.sessionId !== request.proof.sessionId) return invalid();
  const expected = structuredClone(request.preparation);
  const outbound = { ...request, preparationInputWire: inputWire };
  const requestWire = JSON.stringify(outbound);
  const inputHash = await sha256(inputWire);
  const reply = jsonResponseWire(await send(outbound)), value = reply.value;
  if (!replyShape(value) || value.preparationInputSha256 !== inputHash || value.requestHash !== value.delta.requestHash) return invalid();
  const prepared = await applyPreparedTemplateDelta(base, jsonWireAt(reply, ["delta"]), {
    clientMutationId: expected.clientMutationId, requestHash: value.requestHash, capture: expected.capture,
    baseSnapshot: expected.snapshot,
  });
  const address = await verifyAddressMap(jsonWireAt(reply, ["addressMap"]), value.addressMapSha256, base,
    prepared.responseWire, { clientMutationId: expected.clientMutationId, requestHash: value.requestHash,
      createdIds: prepared.delta.createdIds });
  return { requestWire, replyWire: reply.wire, prepared, address };
}

export async function saveTemplateTransport(project: string, advanceInput: JsonWireNode, preparation: BoundTemplatePreparation,
  openingInput: PreparedSaveOpening, send: (request: JsonWireNode) => Promise<unknown>): Promise<TemplateSaveVerification> {
  const advance = parseJsonWire(advanceInput.wire), reply = parseJsonWire(preparation.replyWire);
  const preview = parseJsonWire(preparation.prepared.responseWire.wire), opening = { ...openingInput };
  if (!advanceShape(advance.value) || !replyShape(reply.value)) return invalid();
  const header = advance.value, delta = reply.value.delta;
  if (delta.mutationWire === null || delta.baseSnapshot.projectId !== project || opening.projectId !== project
    || header.proof.lineage !== opening.lineage || header.proof.epoch !== opening.epoch
    || header.proof.sessionId !== opening.sessionId || header.proof.incarnation !== opening.incarnation
    || header.actionCursor !== opening.actionCursor || delta.capture.sessionId !== opening.sessionId) return invalid();
  const deltaRoot = jsonWireAt(reply, ["delta"]);
  const request = parseJsonWire(jsonObjectWire([
    ...[...advance.children].map(([key, child]) => [String(key), child.wire] as const),
    ["mutation", delta.mutationWire], ["preparation", jsonObjectWire([["requestHash", JSON.stringify(delta.requestHash)]])],
    ["responseMode", '"prepared_delta"'],
  ]));
  const result = jsonResponseWire(await send(request));
  return verifyPreparedTemplateSave(preview, deltaRoot, result, opening);
}
