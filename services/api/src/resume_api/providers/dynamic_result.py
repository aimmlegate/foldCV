"""Dynamic payloads keep server assertions ahead of all result decoding."""

from typing import Literal

from pydantic import JsonValue, model_validator

from packages.resume_core.models.contracts import Wire
from packages.resume_core.templates.compiler import PROJECTION_VERSION
from packages.resume_core.templates.models import JsonObject
from packages.resume_core.templates.projection import PROFILE_ID, project_payload, validate_payload, validate_schema


class PayloadEnvelope(Wire):
    payload: JsonValue


class DynamicResultSpec(Wire):
    schema_version: Literal[1]
    full_schema: JsonObject
    provider_schema: JsonObject
    projection_version: Literal["closed-json-1"]
    capability_profile: Literal["closed-json-v1"]
    decode: Literal["raw_json_payload_v1"]
    validation: Literal["raw_before_decode"]
    coordinator_owned: Literal[True]

    @model_validator(mode="after")
    def compatible_projection(self):
        validate_schema(self.full_schema)
        expected, _ = project_payload(self.full_schema)
        if self.provider_schema != expected:
            raise ValueError("provider projection does not match its captured full schema")
        return self

    def decode_value(self, raw: object) -> PayloadEnvelope:
        if not isinstance(raw, dict) or set(raw) != {"payload"}:
            raise ValueError("dynamic result requires its exact payload envelope")
        validate_payload(self.full_schema, raw["payload"])
        return PayloadEnvelope.model_validate(raw, strict=True)


def dynamic_result(schema: JsonObject) -> DynamicResultSpec:
    projected, _ = project_payload(schema)
    return DynamicResultSpec(schemaVersion=1,fullSchema=schema,providerSchema=projected,
        projectionVersion=PROJECTION_VERSION,capabilityProfile=PROFILE_ID,
        decode="raw_json_payload_v1",validation="raw_before_decode",coordinatorOwned=True)
