import { Ajv2020 } from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv";
import assistant_task_catalog_v1 from "../../../../contracts/json-schema/assistant_task_catalog_v1.schema.json" with { type: "json" };
import assistant_task_request_v1 from "../../../../contracts/json-schema/assistant_task_request_v1.schema.json" with { type: "json" };
import assistant_message_check_v1 from "../../../../contracts/json-schema/assistant_message_check_v1.schema.json" with { type: "json" };
import assistant_task_check_v1 from "../../../../contracts/json-schema/assistant_task_check_v1.schema.json" with { type: "json" };
import assistant_assembly_request_v1 from "../../../../contracts/json-schema/assistant_assembly_request_v1.schema.json" with { type: "json" };
import assistant_proposal_v1 from "../../../../contracts/json-schema/assistant_proposal_v1.schema.json" with { type: "json" };
import assistant_proposal_request_v1 from "../../../../contracts/json-schema/assistant_proposal_request_v1.schema.json" with { type: "json" };
import assistant_proposal_list_v1 from "../../../../contracts/json-schema/assistant_proposal_list_v1.schema.json" with { type: "json" };
import assistant_proposal_result_v1 from "../../../../contracts/json-schema/assistant_proposal_result_v1.schema.json" with { type: "json" };

const ajv = new Ajv2020({ strict: false });
const schemas = new Map<string, object>(Object.entries({ assistant_task_catalog_v1, assistant_task_request_v1,
  assistant_message_check_v1, assistant_task_check_v1, assistant_assembly_request_v1, assistant_proposal_v1,
  assistant_proposal_request_v1, assistant_proposal_list_v1, assistant_proposal_result_v1 }));
const validators = new Map<string, ValidateFunction<unknown>>();

export function validateAssistantShape(kind: string, value: unknown): boolean {
  const schema = schemas.get(kind);
  if (!schema) return false;
  let validate = validators.get(kind);
  if (!validate) { validate = ajv.compile<unknown>(schema); validators.set(kind, validate); }
  return validate(value);
}
