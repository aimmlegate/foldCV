"""Offline regressions for the strict output boundary and unknown source data."""

from copy import deepcopy
import json
import threading
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
import pytest

from tests.providers.fixtures import PROMPT, fake
from resume_api.lifecycle import OperationFiles
from resume_api.providers.codex_cli import CodexCliProvider, Events, FixtureTransport
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy
from resume_api.providers.structured_schema import StructuredSchema


class OptionalRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    default: str = Field(default="existing", min_length=1)
    type: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=2)
    present: bool = False


class OptionalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rows: list[OptionalRow]


def run(fake, model, value):
    cli, root, keep, configure, starts = fake
    configure("valid", result_text=json.dumps(value, ensure_ascii=False),
              schema_required=list(model.model_json_schema()["properties"]))
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        result = provider.generate(ContentInput(PROMPT, model, GenerationPolicy("gpt-6-luna", allow_repair=False)),
                                   files, threading.Event())
    assert starts() == result.logical_attempts == 1
    assert list(root.iterdir()) == [keep]
    return result.value


def test_optional_null_restores_defaults_without_changing_domain_schema(fake):
    original = OptionalResult.model_json_schema()
    preserved = deepcopy(original)
    adapter = StructuredSchema(original)
    assert original == preserved == OptionalResult.model_json_schema()
    row = adapter.wire["$defs"]["OptionalRow"]
    assert row["required"] == ["default", "type", "tags", "present"]
    assert row["properties"]["default"]["anyOf"][0]["minLength"] == 1
    assert row["properties"]["tags"]["anyOf"][0]["maxItems"] == 2
    result = run(fake, OptionalResult, {"rows": [{"default": None, "type": None, "tags": None, "present": None}]})
    assert result == OptionalResult.model_validate({"rows": [{}]})
    assert result.rows[0].type is None and result.rows[0].tags == []


@pytest.mark.parametrize("row", [{"default": ""}, {"tags": ["a", "b", "c"]},
                                {"present": "false"}, {"unknown": True}])
def test_wire_conversion_keeps_domain_constraints_and_single_attempt(fake, row):
    with pytest.raises(ContentFailure, match="INVALID_RESULT"):
        run(fake, OptionalResult, {"rows": [row]})
    assert fake[4]() == 1 and list(fake[1].iterdir()) == [fake[2]]


def test_every_template_reply_contract_passes_the_strict_cli_schema_boundary():
    from packages.resume_core.templates.compiler import compile_template
    from packages.resume_core.templates.replies import BOOKKEEPING_KEYS, proposal_schema, review_schema
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    from resume_api.providers.dynamic_result import dynamic_result

    package = compile_template(BUNDLED_TEMPLATE)
    contracts = [proposal_schema(block.full_schema) for block in package.blocks]
    contracts += [proposal_schema(block.full_schema, ["S1", "S2"]) for block in package.blocks]
    contracts.append(review_schema())
    assert len(contracts) == 2 * len(package.blocks) + 1 > 1
    for contract in contracts:
        wire = StructuredSchema(dynamic_result(contract, BOOKKEEPING_KEYS).provider_schema).wire
        assert wire["type"] == "object" and wire["additionalProperties"] is False


def test_fixed_tag_union_is_equivalent_and_restores_only_selected_branch():
    class First(OptionalRow):
        kind: Literal["first"]

    class Second(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        kind: Literal["second"]
        default: str | None

    class TaggedResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        row: Annotated[First | Second, Field(discriminator="kind")]

    adapter = StructuredSchema(TaggedResult.model_json_schema())
    assert "anyOf" in adapter.wire["properties"]["row"]
    assert "oneOf" not in adapter.wire["properties"]["row"]
    first = TaggedResult.model_validate(adapter.restore({"row": {"kind": "first", "default": None}}, TaggedResult))
    second = TaggedResult.model_validate(adapter.restore({"row": {"kind": "second", "default": None}}, TaggedResult))
    assert first.row.default == "existing" and second.row.default is None


def test_enum_tag_union_preserves_nullable_value_in_the_matching_branch():
    class Defaulted(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        kind: Literal["a", "b"]
        note: str = "existing"

    class Nullable(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        kind: Literal["c"]
        note: str | None

    class UnionResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        row: Defaulted | Nullable

    adapter = StructuredSchema(UnionResult.model_json_schema())
    value = {"row": {"kind": "c", "note": None}}
    assert adapter.restore(value, UnionResult) == value
    assert UnionResult.model_validate(adapter.restore(value, UnionResult)) == UnionResult.model_validate(value)

    class DefaultedRows(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        rows: list[Defaulted]

    class NullableRows(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        rows: list[Nullable]

    class NestedResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        group: DefaultedRows | NullableRows

    nested = {"group": {"rows": [value["row"]]}}
    adapter = StructuredSchema(NestedResult.model_json_schema())
    assert adapter.restore(nested, NestedResult) == nested
    assert NestedResult.model_validate(adapter.restore(nested, NestedResult)) == NestedResult.model_validate(nested)


def test_union_restoration_uses_canonical_patterns_and_bounds():
    class Defaulted(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        name: str = Field(pattern="^a", min_length=2, max_length=20)
        score: int = Field(ge=0, le=10)
        note: str = "existing"

    class Nullable(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        name: str = Field(pattern="^b", min_length=2, max_length=20)
        score: int = Field(ge=11, le=20)
        note: str | None

    class UnionResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        row: Defaulted | Nullable

    adapter = StructuredSchema(UnionResult.model_json_schema())
    value = {"row": {"name": "beta", "score": 15, "note": None}}
    assert adapter.restore(value, UnionResult) == value
    assert UnionResult.model_validate(adapter.restore(value, UnionResult)) == UnionResult.model_validate(value)
    missing = {"row": {"name": "alpha", "score": 5, "note": None}}
    restored = adapter.restore(missing, UnionResult)
    assert restored == {"row": {"name": "alpha", "score": 5}}
    assert UnionResult.model_validate(restored).row.note == "existing"


@pytest.mark.parametrize("key", ["wire_note", "note"])
def test_alias_choices_restore_only_accepted_aliases(fake, key):
    class Aliased(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        note: str = Field(default="existing", validation_alias=AliasChoices("wire_note", "note"))

    assert run(fake, Aliased, {key: None}).note == "existing"


def test_unaccepted_field_name_is_not_removed_as_a_default(fake):
    class Aliased(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        note: str = Field(default="existing", alias="wire_note")

    with pytest.raises(ContentFailure, match="INVALID_RESULT"):
        run(fake, Aliased, {"note": None})
    assert fake[4]() == 1 and list(fake[1].iterdir()) == [fake[2]]


def test_simultaneous_aliases_cannot_become_valid_after_default_restoration(fake):
    class Aliased(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        note: str = Field(default="existing", validation_alias=AliasChoices("wire_note", "note"))

    with pytest.raises(ContentFailure, match="INVALID_RESULT"):
        run(fake, Aliased, {"wire_note": None, "note": "other"})
    assert fake[4]() == 1 and list(fake[1].iterdir()) == [fake[2]]


@pytest.mark.parametrize("schema", [
    {"type": "object", "additionalProperties": {"type": "string"}},
    {"type": "object", "properties": {}, "additionalProperties": False,
     "oneOf": [{"type": "string"}, {"type": "string"}]},
])
def test_unsupported_open_or_exclusive_schema_is_rejected(schema):
    with pytest.raises(ValueError):
        StructuredSchema(schema)


def test_open_map_is_rejected_before_any_cli_execution(fake):
    class DynamicResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        fields: dict[str, str]

    cli, root, keep, _, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure, match="INVALID_SCHEMA"):
        with OperationFiles(root).open() as files:
            provider.generate(ContentInput(PROMPT, DynamicResult, GenerationPolicy("gpt-6-luna")), files, threading.Event())
    assert not (cli.parent / "audit.jsonl").exists()
    assert starts() == 0 and list(root.iterdir()) == [keep]


def test_required_data_cannot_be_replaced_with_null(fake):
    with pytest.raises(ContentFailure, match="INVALID_RESULT"):
        run(fake, OptionalResult, {"rows": None})
    assert fake[4]() == 1 and list(fake[1].iterdir()) == [fake[2]]


def test_native_nested_schema_error_is_terminal_and_safe(fake):
    cli, root, keep, configure, starts = fake
    configure("schema_rejected", schema_required=["rows"])
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(ContentInput(PROMPT, OptionalResult, GenerationPolicy("gpt-6-luna")), files, threading.Event())
    assert raised.value.code == "INVALID_SCHEMA" and raised.value.logical_attempts == 1
    assert "synthetic-secret" not in str(raised.value) and PROMPT not in str(raised.value)
    assert starts() == 1 and list(root.iterdir()) == [keep]


@pytest.mark.parametrize("message", ["invalid_json_schema synthetic-secret", "{bad json}",
                                    '{"error":{"code":["invalid_json_schema"]}}'])
def test_unstructured_or_invalid_error_message_stays_generic(message):
    with pytest.raises(ContentFailure, match="CLI_FAILED"):
        Events().accept(json.dumps({"type": "error", "message": message}).encode())
