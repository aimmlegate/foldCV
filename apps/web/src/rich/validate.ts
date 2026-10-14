import Ajv2020 from "ajv/dist/2020.js";
import workspaceSchema from "../../../../contracts/json-schema/workspace_v6.schema.json" with { type: "json" };
import factsSchema from "../../../../contracts/json-schema/working_facts.schema.json" with { type: "json" };
import documentSchema from "../../../../contracts/json-schema/rich_document_v1.schema.json" with { type: "json" };
import type { WorkspaceV6 } from "../contracts/generated/workspace_v6";
import type { WorkingFacts } from "../contracts/generated/working_facts";
import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";

const ajv = new Ajv2020({ strict: false, allErrors: true });
const workspaceShape = ajv.compile<WorkspaceV6>(workspaceSchema);
const factsShape = ajv.compile<WorkingFacts>(factsSchema);
const documentShape = ajv.compile<RichDocumentV1>(documentSchema);

export function validateWorkingFacts(value: unknown): value is WorkingFacts { return factsShape(value); }
export function validateRichDocumentShape(value: unknown): value is RichDocumentV1 { return documentShape(value); }
export function validateRichWorkspaceShape(value: unknown): value is WorkspaceV6 { return workspaceShape(value); }
