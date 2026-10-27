"""Shared C01 cases with independent expected outcomes, for the contracts the service still serves."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.resume_core.models import validate_contract
from packages.resume_core.rendering.models import RenderRequest
from packages.resume_core.rendering.preparation import PrepareRequest
from packages.resume_core.extraction.models import ExtractResult


EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"
ALL_CASES = json.loads((EXAMPLES / "cases.json").read_text(encoding="utf-8"))
PROJECT = json.loads((EXAMPLES / "project.json").read_text(encoding="utf-8"))
DIRECT = {"render_request": RenderRequest, "prepare_request": PrepareRequest, "extract_result": ExtractResult}
# Kinds whose models left with their modules in SR06 step 2: the V1 normalize/draft pipeline, the gui_* (V1-V5)
# generations, the background job and writer protocol, and the agent access/run/edit records of the old assistant.
RETIRED_PREFIXES = ("background_", "gui_", "agent_access", "agent_commit", "agent_conversation", "agent_edit",
    "agent_history", "agent_prepare", "agent_project", "agent_read", "agent_run")
RETIRED = frozenset({"fact_request", "fact_sheet", "semantic_proposal", "draft_request", "draft_proposal", "draft_result",
    "archive_manifest_v5", "document", "editorial_plan", "mutation", "mutation_result", "project_v4", "render_snapshot_v4",
    "selection", "source_context", "source_context_request", "workspace_v5"})


def retired(kind: str) -> bool:
    return kind in RETIRED or kind.startswith(RETIRED_PREFIXES)


CASES = [case for case in ALL_CASES if not retired(case["contract"])]


def case_data(case: dict) -> object:
    bases = {path.stem: json.loads(path.read_text(encoding="utf-8")) for folder in (EXAMPLES, EXAMPLES / "recovery",
        EXAMPLES / "agent") for path in folder.glob("*.json") if not retired(path.stem)}
    bases["proposal"], bases["template"] = PROJECT["proposals"][0], PROJECT["template"]
    data = copy.deepcopy(bases[case["base"]])
    for edit in case["edits"]:
        target = data
        for key in edit["path"][:-1]:
            target = target[key]
        key = edit["path"][-1]
        if edit["op"] == "set":
            target[key] = edit["value"]
        elif edit["op"] == "remove":
            del target[key]
        elif edit["op"] == "append":
            target[key].append(edit["value"])
        elif edit["op"] == "clone":
            source = data
            for part in edit["from"]:
                source = source[part]
            target[key].append(copy.deepcopy(source))
        elif edit["op"] == "repeat_text":
            target[key] = edit["text"] * edit["count"]
        elif edit["op"] == "fill_sidebar":
            target[key] = [{"title": "T", "items": [edit["text"] * edit["repeat"]] * edit["items"]}
                           for _ in range(edit["sections"])]
        else:
            raise AssertionError("unknown test edit")
    return data


def test_every_case_has_a_current_contract():
    unknown = []
    for case in CASES:
        if case["contract"] in DIRECT:
            continue
        try:
            validate_contract(case["contract"], None)
        except ValueError as error:
            # A registered kind fails validation of None; only an unregistered kind raises this message.
            if str(error) == "unknown contract":
                unknown.append(case["contract"])
    assert unknown == []


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_shared_case(case: dict) -> None:
    try:
        if case["contract"] in DIRECT:
            DIRECT[case["contract"]].model_validate(case_data(case))
        else:
            validate_contract(case["contract"], case_data(case))
        accepted = True
    except (ValueError, ValidationError):
        accepted = False
    assert accepted is case["valid"]


def test_manual_value_edit_keeps_identity() -> None:
    edited = case_data(next(c for c in CASES if c["name"] == "manual_value_edit_keeps_id"))
    project = validate_contract("project", edited)
    assert project.facts[2].id == PROJECT["facts"][2]["id"]
    assert project.facts[2].revision == 2


def test_partial_save_preserves_source_bytes_reference() -> None:
    partial = case_data(next(c for c in CASES if c["name"] == "partial_project_save"))
    project = validate_contract("project", partial)
    assert project.sources[0].byte_ref == "sources/source_1/original.txt"
    assert project.template is None
