import rulesSettings from "../../../../contracts/json-schema/rules_settings.schema.json" with { type: "json" };
import saveRules from "../../../../contracts/json-schema/save_rules_request.schema.json" with { type: "json" };
import rulesError from "../../../../contracts/json-schema/rules_settings_error.schema.json" with { type: "json" };
import { Ajv2020 } from "ajv/dist/2020.js";
import project from "../../../../contracts/json-schema/project_v4.schema.json" with { type: "json" };
import workspace from "../../../../contracts/json-schema/workspace_v5.schema.json" with { type: "json" };
import archive from "../../../../contracts/json-schema/archive_manifest_v5.schema.json" with { type: "json" };
import document from "../../../../contracts/json-schema/document.schema.json" with { type: "json" };
import error from "../../../../contracts/json-schema/docx_error.schema.json" with { type: "json" };
import plan from "../../../../contracts/json-schema/editorial_plan.schema.json" with { type: "json" };
import mutation from "../../../../contracts/json-schema/mutation.schema.json" with { type: "json" };
import result from "../../../../contracts/json-schema/mutation_result.schema.json" with { type: "json" };
import preferences from "../../../../contracts/json-schema/preferences.schema.json" with { type: "json" };
import registry from "../../../../contracts/json-schema/registry.schema.json" with { type: "json" };
import render from "../../../../contracts/json-schema/render_snapshot_v4.schema.json" with { type: "json" };
import rules from "../../../../contracts/json-schema/rules.schema.json" with { type: "json" };
import selection from "../../../../contracts/json-schema/selection.schema.json" with { type: "json" };
import context from "../../../../contracts/json-schema/source_context.schema.json" with { type: "json" };

const ajv = new Ajv2020({ allErrors: true, strict: false });
const schemas = { project_v4: project, workspace_v5: workspace, archive_manifest_v5: archive,
  document, docx_error: error, editorial_plan: plan, mutation, mutation_result: result,
  preferences, registry, render_snapshot_v4: render, rules, selection, source_context: context, save_rules_request: saveRules, rules_settings_error: rulesError, rules_settings: rulesSettings };
const validators = new Map(Object.entries(schemas).map(([name, schema]) => [name, ajv.compile(schema)]));

export function validateRecoveryShape(kind: string, value: unknown): boolean {
  return validators.get(kind)?.(value) === true;
}
