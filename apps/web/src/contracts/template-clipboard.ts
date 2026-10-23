import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import captureSchema from "../../../../contracts/json-schema/template_clipboard_capture_v1.schema.json" with { type: "json" };
import releaseSchema from "../../../../contracts/json-schema/background_writer_clipboard_release_result_v2.schema.json" with { type: "json" };
import type { TemplateClipboardCaptureV1 } from "./generated/template_clipboard_capture_v1";
import type { WriterClipboardReleaseResultV2 } from "./generated/background_writer_clipboard_release_result_v2";
import { taggedSchema } from "./tagged-schema";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const captureShape = ajv.compile<TemplateClipboardCaptureV1>(taggedSchema(captureSchema));
const releaseShape = ajv.compile<WriterClipboardReleaseResultV2>(taggedSchema(releaseSchema));

/** A same-project copy retained by Python for this writer session. */
export function isClipboardCapture(value: unknown): value is TemplateClipboardCaptureV1 { return captureShape(value); }
export function isClipboardRelease(value: unknown): value is WriterClipboardReleaseResultV2 { return releaseShape(value); }
