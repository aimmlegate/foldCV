# Contracts

Python Pydantic models are the authority for every wire and file shape.
`tools/generate_contracts.py` writes one JSON Schema per model into
`contracts/json-schema/`; `json2ts` turns each schema into a TypeScript type in
`apps/web/src/contracts/generated/`. Wire keys use camelCase, Python attributes
snake_case. Models reject unknown fields. Each file and reply model carries its own
`schemaVersion` (projects `WorkspaceV7`, archives `ArchiveManifestV7`); a changed
field or meaning needs a new version, with no implicit fallback.

## Contract list

`CONTRACTS` in `tools/generate_contracts.py`, 69 models:

| Group | Contracts |
|---|---|
| Project routes (`models/projects.py`, `PROJECT_CONTRACTS`) | `history_state_v1`, `task_status_v1`, `project_open_result_v1`, `edit_request_v1`, `edit_result_v1`, `history_request_v1`, `clipboard_capture_request_v1`, `revision_conflict_v1`, `rename_request_v1`, `delete_request_v1`, `rewrite_preview_request_v1`, `rewrite_cancel_request_v1` |
| Project route bodies the service modules define (`resume_api/projects`) | `import_command`, `export_command`, `export_retry`, `archive_download` |
| Template editing and project files | `template_project_response_v1`, `template_edit_preparation_v1`, `template_clipboard_capture_v1`, `template_rewrite_preview_v1`, `template_snapshot_identity`, `rich_document_v2`, `workspace_v7`, `archive_manifest_v7`, `template_import_v1` (import operation sidecar), `template_render_request_v1` (render worker input), `template_definition`, `template_package` |
| V6 parts the V7 models are built from and the client still types | `working_facts`, `rich_document_v1`, `rich_panel_request` |
| Assistant (`models/assistant.py`, `ASSISTANT_CONTRACTS`) | `assistant_error_v1`, `assistant_run_request_v2`, `assistant_run_v1`, `assistant_conversation_v1`, `assistant_conversation_list_v1`, `assistant_messages_v1`, `assistant_events_v1`, `assistant_change_proposal_v1`, `assistant_change_proposal_list_v1`, `assistant_apply_request_v1`, `assistant_apply_result_v1`, `assistant_skill_list_v1`, `propose_changes_v1`, `publish_findings_v1`, `assistant_capabilities_v1`, `assistant_file_v1` |
| Agent records shared with the run files (`models/agent.py`, `AGENT_CONTRACTS`) | `agent_error`, `agent_settings`, `agent_settings_request`, `agent_message`, `agent_web_source`, `agent_finding`, `agent_event`, `agent_fetch_request` |
| Settings (`models/settings.py`, `SETTINGS_CONTRACTS`) | `rules`, `rules_settings`, `rules_settings_error`, `save_rules_request`, `preferences`, `save_import_model_preference`, `save_limits_preference`, `save_analysis_preference` |
| Other | `registry`, `cli_installation_payload`; domain and worker models `extract_result`, `render_request`, `prepare_request`, `project` (kept tests read their examples) |

The generator also writes `contracts/template-source.schema.json`: editor hints for
template YAML in both forms, with no TypeScript type. To add a contract, register the
model in `CONTRACTS` (or its module's registry), regenerate, and commit the schema
and the type together.

## Generate and check

Use the arm64 Node 22 from nvm. The default `node` is x64 v12 and its Python child
cannot load the arm64 `pydantic_core` in `.venv`.

```sh
cd apps/web
export PATH="$HOME/.nvm/versions/node/v22.14.0/bin:$PATH"
npm run contracts:generate
npm run contracts:check
```

`contracts:generate` empties both output folders, writes the schemas, runs `json2ts`
on each schema and strips the generated banners, so a model that left the list leaves
no file behind. `contracts:check` (`tools/check_contract_drift.py`) expects exactly
`len(CONTRACTS)` schema/type pairs plus the template source schema, regenerates, and
fails on any changed, new or missing file, restoring the previous files. Zero drift is
required. `tests/foundation/test_contract_drift.py` covers the check itself.

## Client use

The client parses replies with `JSON.parse` and types them with the generated types
(`rich/v7-connection.ts`, `projects/api.ts`, `assistant/api.ts`, `api/client.ts`).
The application bundle has no runtime schema validator (no ajv): the service
validates every request and builds every reply from its models. The one extra client
check is `contracts/template-export.ts`: an export reply must name the snapshot the
editor sent.

## Tests

`tests/contracts/test_contracts.py` checks every schema with
`Draft202012Validator.check_schema`, validates the kept examples in
`contracts/examples/` and the cases in `contracts/examples/cases.json` against their
models, and checks that each generated schema accepts every value its model accepts.
It runs in the default suite; alone:

```sh
PYTHONPATH=services/api/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/contracts
```

The error catalog `contracts/error-messages.ru.json` is checked by
`tests/settings/test_error_messages.py`: every public code needs a Russian text.
