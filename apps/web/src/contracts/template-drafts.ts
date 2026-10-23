import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import payloadSchema from "../../../../contracts/json-schema/background_writer_draft_payload_v2.schema.json" with { type: "json" };
import readSchema from "../../../../contracts/json-schema/background_writer_draft_read_v2.schema.json" with { type: "json" };
import type { DraftPayloadV2 } from "./generated/background_writer_draft_payload_v2";
import type { WriterDraftReadV2 } from "./generated/background_writer_draft_read_v2";
import { taggedSchema } from "./tagged-schema";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
ajv.addKeyword({ keyword: "x-maxSerializedBytes", schemaType: "number",
  validate: (limit: number, value: unknown): boolean => new TextEncoder().encode(JSON.stringify(value)).length <= limit });
const payloadShape = ajv.compile<DraftPayloadV2>(taggedSchema(payloadSchema));
const readShape = ajv.compile<WriterDraftReadV2>(taggedSchema(readSchema));

/** V7 private drafts: shape and bounds only; the queue record is interpreted by the editor session. */
export function isTemplateDraftPayload(value: unknown): value is DraftPayloadV2 { return payloadShape(value); }
export function isTemplateDraftRead(value: unknown): value is WriterDraftReadV2 { return readShape(value); }
