import draftRequest from "../../../../contracts/json-schema/gui_draft_request.schema.json" with { type: "json" };
import rewriteRequest from "../../../../contracts/json-schema/gui_rewrite_request.schema.json" with { type: "json" };
import exportRequest from "../../../../contracts/json-schema/gui_export_request.schema.json" with { type: "json" };
import analysisRequest from "../../../../contracts/json-schema/gui_analysis_request.schema.json" with { type: "json" };
import analysisPreference from "../../../../contracts/json-schema/save_analysis_preference.schema.json" with { type: "json" };
import analysisProposal from "../../../../contracts/json-schema/gui_reconcile_proposal.schema.json" with { type: "json" };
import projectList from "../../../../contracts/json-schema/gui_project_list_response.schema.json" with { type: "json" };
import deleteProject from "../../../../contracts/json-schema/gui_delete_project_request.schema.json" with { type: "json" };
import archiveRequest from "../../../../contracts/json-schema/gui_archive_request.schema.json" with { type: "json" };
import deleteResult from "../../../../contracts/json-schema/gui_delete_project_result.schema.json" with { type: "json" };
import rewriteProposal from "../../../../contracts/json-schema/gui_rewrite_proposal.schema.json" with { type: "json" };
import createProject from "../../../../contracts/json-schema/gui_create_project_request.schema.json" with { type: "json" };
import startGeneration from "../../../../contracts/json-schema/gui_start_generation_request.schema.json" with { type: "json" };
import renameProject from "../../../../contracts/json-schema/gui_rename_project_request.schema.json" with { type: "json" };
import projectResponse from "../../../../contracts/json-schema/gui_project_response.schema.json" with { type: "json" };
import draftProposal from "../../../../contracts/json-schema/gui_draft_proposal.schema.json" with { type: "json" };
import draftResult from "../../../../contracts/json-schema/gui_draft_result.schema.json" with { type: "json" };
import guiRequest from "../../../../contracts/json-schema/gui_normalize_request.schema.json" with { type: "json" };
import guiProposal from "../../../../contracts/json-schema/gui_semantic_proposal.schema.json" with { type: "json" };
import guiResult from "../../../../contracts/json-schema/gui_normalized_result.schema.json" with { type: "json" };
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
import contextRequest from "../../../../contracts/json-schema/source_context_request.schema.json" with { type: "json" };
import panelRequest from "../../../../contracts/json-schema/rich_panel_request.schema.json" with { type: "json" };

const ajv = new Ajv2020({ allErrors: true, strict: false });
const schemas = { gui_archive_request: archiveRequest, gui_project_list_response: projectList, gui_delete_project_request: deleteProject, gui_delete_project_result: deleteResult, gui_analysis_request: analysisRequest, save_analysis_preference: analysisPreference, gui_reconcile_proposal: analysisProposal, gui_export_request: exportRequest, gui_rewrite_request: rewriteRequest, gui_rewrite_proposal: rewriteProposal, gui_rename_project_request: renameProject, gui_create_project_request: createProject, gui_start_generation_request: startGeneration,
  rich_panel_request: panelRequest, gui_project_response: projectResponse, project_v4: project, workspace_v5: workspace, archive_manifest_v5: archive,
  document, docx_error: error, editorial_plan: plan, mutation, mutation_result: result,
  preferences, registry, render_snapshot_v4: render, rules, selection, source_context: context, source_context_request: contextRequest, save_rules_request: saveRules, rules_settings_error: rulesError, rules_settings: rulesSettings, gui_normalize_request: guiRequest, gui_semantic_proposal: guiProposal, gui_normalized_result: guiResult, gui_draft_request: draftRequest, gui_draft_proposal: draftProposal, gui_draft_result: draftResult };
const validators = new Map(Object.entries(schemas).map(([name, schema]) => [name, ajv.compile(schema)]));

export function validateRecoveryShape(kind: string, value: unknown): boolean {
  return validators.get(kind)?.(value) === true;
}
