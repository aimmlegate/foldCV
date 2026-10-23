import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import previewSchema from "../../../../contracts/json-schema/template_rewrite_preview_v1.schema.json" with { type: "json" };
import cancelSchema from "../../../../contracts/json-schema/background_writer_rewrite_cancel_result_v2.schema.json" with { type: "json" };
import type { TemplateRewritePreviewV1 } from "./generated/template_rewrite_preview_v1";
import type { WriterRewriteCancelResultV2 } from "./generated/background_writer_rewrite_cancel_result_v2";
import { taggedSchema } from "./tagged-schema";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const previewShape = ajv.compile<TemplateRewritePreviewV1>(taggedSchema(previewSchema));
const cancelShape = ajv.compile<WriterRewriteCancelResultV2>(taggedSchema(cancelSchema));

/** A generated replacement for one selected range; it changes nothing until applied. */
export function isRewritePreview(value: unknown): value is TemplateRewritePreviewV1 { return previewShape(value); }
export function isRewriteCancel(value: unknown): value is WriterRewriteCancelResultV2 { return cancelShape(value); }
