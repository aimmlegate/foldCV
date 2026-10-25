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
    # Keys a reply may still carry although the schema has none (I3: bookkeeping the coordinator derives when a request
    # offers no items); they are dropped before validation instead of failing the whole reply.
    tolerated_keys: list[str] = []

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
        payload = self.tolerate(raw["payload"])
        validate_payload(self.full_schema, payload)
        return PayloadEnvelope.model_validate({"payload": payload}, strict=True)

    def tolerate(self, payload):
        defined = set(self.full_schema.get("properties", {}))
        if not self.tolerated_keys or not isinstance(payload, dict):
            return payload
        return {key: value for key, value in payload.items() if key not in self.tolerated_keys or key in defined}


def dynamic_result(schema: JsonObject, tolerated_keys: tuple[str, ...] = ()) -> DynamicResultSpec:
    projected, _ = project_payload(schema)
    return DynamicResultSpec(schemaVersion=1,fullSchema=schema,providerSchema=projected,
        projectionVersion=PROJECTION_VERSION,capabilityProfile=PROFILE_ID,
        decode="raw_json_payload_v1",validation="raw_before_decode",coordinatorOwned=True, toleratedKeys=list(tolerated_keys))
