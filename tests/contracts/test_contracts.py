"""Shared example cases for the generated contracts: the Python model accepts or refuses each case, and the generated
JSON Schema accepts every value the model accepts."""

import copy
from functools import cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest
from pydantic import ValidationError

from packages.resume_core.models.contracts import Project
from tools.generate_contracts import CONTRACTS


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "contracts" / "examples"
SCHEMAS = ROOT / "contracts" / "json-schema"
CASES = json.loads((EXAMPLES / "cases.json").read_text(encoding="utf-8"))
BASES = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in EXAMPLES.rglob("*.json")
         if path.name != "cases.json"}


@cache
def schema(name: str) -> Draft202012Validator:
    value = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)


def case_data(case: dict) -> object:
    data = copy.deepcopy(BASES[case["base"]])
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


def test_every_example_and_case_names_a_generated_contract():
    assert set(BASES) <= set(CONTRACTS)
    assert {case["contract"] for case in CASES} <= set(CONTRACTS)
    assert {case["base"] for case in CASES} <= set(BASES)
    assert {path.name for path in SCHEMAS.glob("*.schema.json")} == {f"{name}.schema.json" for name in CONTRACTS}


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_generated_schema_is_valid(name: str) -> None:
    schema(name)


@pytest.mark.parametrize("name", sorted(BASES))
def test_example_is_accepted_by_its_model_and_schema(name: str) -> None:
    CONTRACTS[name].model_validate(BASES[name])
    assert list(schema(name).iter_errors(BASES[name])) == []


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_shared_case(case: dict) -> None:
    data = case_data(case)
    try:
        CONTRACTS[case["contract"]].model_validate(data)
        accepted = True
    except (ValueError, ValidationError):
        accepted = False
    assert accepted is case["valid"]
    if accepted:
        assert list(schema(case["contract"]).iter_errors(data)) == []


def test_manual_value_edit_keeps_identity() -> None:
    edited = case_data(next(c for c in CASES if c["name"] == "manual_value_edit_keeps_id"))
    project = Project.model_validate(edited)
    assert project.facts[2].id == BASES["project"]["facts"][2]["id"]
    assert project.facts[2].revision == 2


def test_partial_save_preserves_source_bytes_reference() -> None:
    partial = case_data(next(c for c in CASES if c["name"] == "partial_project_save"))
    project = Project.model_validate(partial)
    assert project.sources[0].byte_ref == "sources/source_1/original.txt"
    assert project.template is None
