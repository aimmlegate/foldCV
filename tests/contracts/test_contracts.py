"""Shared C01 cases with independent expected outcomes."""

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
CASES = json.loads((EXAMPLES / "cases.json").read_text(encoding="utf-8"))
PROJECT = json.loads((EXAMPLES / "project.json").read_text(encoding="utf-8"))
ZIP = json.loads((EXAMPLES / "zip_manifest.json").read_text(encoding="utf-8"))
RENDER = json.loads((EXAMPLES / "render_request.json").read_text(encoding="utf-8"))
PREPARE = json.loads((EXAMPLES / "prepare_request.json").read_text(encoding="utf-8"))
EXTRACT = json.loads((EXAMPLES / "extract_result.json").read_text(encoding="utf-8"))


def case_data(case: dict) -> object:
    bases = {"project": PROJECT, "proposal": PROJECT["proposals"][0], "template": PROJECT["template"], "zip_manifest": ZIP,
             "render_request": RENDER, "prepare_request": PREPARE, "extract_result": EXTRACT}
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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_shared_case(case: dict) -> None:
    try:
        if case["contract"] == "render_request":
            RenderRequest.model_validate(case_data(case))
        elif case["contract"] == "prepare_request":
            PrepareRequest.model_validate(case_data(case))
        elif case["contract"] == "extract_result":
            ExtractResult.model_validate(case_data(case))
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
