"""Offline Draft 2020-12 validation and a conservative provider projection."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import re
import threading

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from pydantic import JsonValue
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable

from .models import JsonObject

PROFILE_ID = "closed-json-v1"
PROFILE_VERSION = "1"
FORMATS = ("date", "email")
FORMAT_CHECKER = FormatChecker(formats=FORMATS)


def offline_resource(uri):
    raise NoSuchResource(ref=uri)


OFFLINE_REGISTRY = Registry(retrieve=offline_resource)
SHAPE_KEYS = {"type", "properties", "required", "additionalProperties", "items", "enum", "const", "anyOf", "$ref", "$defs"}
ANNOTATIONS = {"description", "title", "default", "readOnly", "writeOnly", "examples", "$schema", "$comment"}
SERVER_KEYS = {"minLength", "maxLength", "pattern", "format", "minimum", "maximum", "exclusiveMinimum",
               "exclusiveMaximum", "multipleOf", "minItems", "maxItems", "uniqueItems", "contains", "minContains",
               "maxContains", "minProperties", "maxProperties", "if", "then", "else", "not", "allOf",
               "dependentRequired", "dependentSchemas"}


class SchemaFailure(ValueError):
    def __init__(self, path: str, reason: str):
        self.path, self.reason = path, reason
        super().__init__(f"{path}: {reason}")


def pointer_tokens(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or pointer and not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise SchemaFailure(pointer, "invalid JSON pointer")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")] if pointer else []


def resolve(root: JsonObject, ref: str) -> JsonObject:
    if not ref.startswith("#/$defs/"):
        raise SchemaFailure(ref, "only local definition references are supported")
    current: JsonValue = root
    for key in pointer_tokens(ref[1:]):
        if not isinstance(current, dict) or key not in current:
            raise SchemaFailure(ref, "missing definition")
        current = current[key]
    if not isinstance(current, dict):
        raise SchemaFailure(ref, "reference must resolve to a schema object")
    return current


def schema_children(node: JsonObject):
    for key in ("properties", "$defs", "patternProperties", "dependentSchemas"):
        children = node.get(key)
        if isinstance(children, dict):
            for name, child in children.items():
                if isinstance(child, dict): yield f"{key}/{name}", child
    for key in ("items", "contains", "additionalProperties", "propertyNames", "not", "if", "then", "else",
                "unevaluatedProperties", "unevaluatedItems"):
        child = node.get(key)
        if isinstance(child, dict): yield key, child
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        children = node.get(key)
        if isinstance(children, list):
            for index, child in enumerate(children):
                if isinstance(child, dict): yield f"{key}/{index}", child


def validate_schema(schema: JsonObject) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise SchemaFailure("/" + "/".join(map(str, error.path)), error.message) from None
    count = 0

    def visit(node: JsonObject, path: str, chain: frozenset[str]) -> None:
        nonlocal count
        count += 1
        if count > 50_000: raise SchemaFailure(path, "schema exceeds technical traversal limit")
        if "$schema" in node and node["$schema"] not in {
                "https://json-schema.org/draft/2020-12/schema", "https://json-schema.org/draft/2020-12/schema#"}:
            raise SchemaFailure(path, "unsupported schema dialect")
        if any(key in node for key in ("$id", "$anchor", "$dynamicRef", "$recursiveRef", "$dynamicAnchor", "$recursiveAnchor")):
            raise SchemaFailure(path, "resource IDs, anchors and dynamic/recursive references are unsupported")
        if "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str): raise SchemaFailure(path, "reference must be a string")
            if ref in chain: raise SchemaFailure(path, "recursive schemas are unsupported")
            visit(resolve(schema, ref), ref, chain | {ref})
        if "format" in node and node["format"] not in FORMATS:
            raise SchemaFailure(path, "unsupported format")
        for key, child in schema_children(node): visit(child, path + "/" + key, chain)
    visit(schema, "", frozenset())


_REACHABLE: OrderedDict[str, JsonObject] = OrderedDict()
_REACHABLE_LOCK = threading.Lock()


def reachable_schema(payload: JsonObject, definitions: dict[str, JsonObject]) -> JsonObject:
    # Workspace validation derives every fact type's schema on each read; the meta-schema checks dominate import time.
    key = hashlib.sha256(json.dumps([payload, definitions], sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    with _REACHABLE_LOCK:
        found = _REACHABLE.get(key)
        if found is not None:
            _REACHABLE.move_to_end(key)
            return deepcopy(found)
    result = _reachable_schema(payload, definitions)
    with _REACHABLE_LOCK:
        _REACHABLE[key] = deepcopy(result)
        while len(_REACHABLE) > 512:
            _REACHABLE.popitem(last=False)
    return result


def _reachable_schema(payload: JsonObject, definitions: dict[str, JsonObject]) -> JsonObject:
    root = deepcopy(payload)
    local = root.get("$defs", {})
    if not isinstance(local, dict): raise SchemaFailure("/$defs", "definitions must be an object")
    merged = deepcopy(definitions)
    for key, value in local.items():
        if key in merged and merged[key] != value: raise SchemaFailure("/$defs/" + key, "conflicting definition")
        if not isinstance(value, dict): raise SchemaFailure("/$defs/" + key, "definition must be an object")
        merged[key] = value
    root["$defs"] = merged
    validate_schema(root)
    used: set[str] = set()

    def visit(value: JsonObject, include_definitions=False) -> None:
        ref = value.get("$ref")
        if ref is not None:
            if not isinstance(ref, str): raise SchemaFailure("$ref", "reference must be a string")
            resolve(root, ref)
            name = pointer_tokens(ref[1:])[1]
            if name not in used:
                used.add(name); visit(merged[name], True)
        for key, child in schema_children(value):
            if include_definitions or not key.startswith("$defs/"): visit(child, include_definitions)
    visit(payload)
    root.pop("$defs", None)
    if used: root["$defs"] = {key: merged[key] for key in sorted(used)}
    validate_schema(root)
    return root


def project_payload(full: JsonObject) -> tuple[JsonObject, list[str]]:
    omitted: list[str] = []

    def project(value: JsonValue, path: str) -> JsonObject:
        if not isinstance(value, dict): raise SchemaFailure(path, "boolean or untyped provider schemas are unsupported")
        unknown = set(value) - SHAPE_KEYS - ANNOTATIONS - SERVER_KEYS
        if unknown: raise SchemaFailure(path, "unsupported schema keywords: " + ", ".join(sorted(unknown)))
        if not any(key in value for key in ("type", "$ref", "anyOf", "enum", "const")):
            raise SchemaFailure(path, "provider shape must be explicit")
        result: JsonObject = {}
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in SERVER_KEYS:
                omitted.append(child_path)
            elif key in ANNOTATIONS:
                continue
            elif key in {"properties", "$defs"}:
                if not isinstance(child, dict): raise SchemaFailure(child_path, "expected schema map")
                result[key] = {name: project(part, child_path + "/" + name) for name, part in child.items()}
            elif key == "items": result[key] = project(child, child_path)
            elif key == "anyOf":
                if not isinstance(child, list) or not child: raise SchemaFailure(child_path, "expected union branches")
                result[key] = [project(part, f"{child_path}/{i}") for i, part in enumerate(child)]
            elif key == "const": result["enum"] = [deepcopy(child)]
            else: result[key] = deepcopy(child)
        kind = value.get("type")
        types = kind if isinstance(kind, list) else [kind]
        if "object" in types or "properties" in value:
            properties = value.get("properties")
            if not isinstance(properties, dict) or value.get("additionalProperties") is not False:
                raise SchemaFailure(path, "provider objects require closed properties")
            required = value.get("required", [])
            if not isinstance(required, list) or set(required) != set(properties):
                raise SchemaFailure(path, "every property must be required; represent missing scalars with null")
        if "array" in types and "items" not in value:
            raise SchemaFailure(path, "provider arrays require an item shape")
        return result

    projected = project(full, "/payload")
    definitions = projected.pop("$defs", None)
    result: JsonObject = {"type": "object", "additionalProperties": False,
                          "required": ["payload"], "properties": {"payload": projected}}
    if definitions is not None: result["$defs"] = definitions
    return result, sorted(set(omitted))


def schema_at(root: JsonObject, pointer: str) -> JsonObject:
    current = root
    for token in pointer_tokens(pointer):
        while "$ref" in current:
            ref = current["$ref"]
            if not isinstance(ref, str): raise SchemaFailure(pointer, "invalid reference")
            current = resolve(root, ref)
        kind = current.get("type")
        types = kind if isinstance(kind, list) else [kind]
        if "array" in types and (token == "*" or token.isdecimal()): value = current.get("items")
        else:
            properties = current.get("properties", {})
            value = properties.get(token) if isinstance(properties, dict) else None
        if not isinstance(value, dict): raise SchemaFailure(pointer, "unknown field")
        current = value
    while "$ref" in current:
        ref = current["$ref"]
        if not isinstance(ref, str): raise SchemaFailure(pointer, "invalid reference")
        current = resolve(root, ref)
    return current


def validate_payload(schema: JsonObject, value: JsonValue) -> None:
    try:
        error = next(Draft202012Validator(schema, format_checker=FORMAT_CHECKER,
            registry=OFFLINE_REGISTRY).iter_errors(value), None)
    except Unresolvable:
        raise SchemaFailure("/payload", "unresolvable offline schema reference") from None
    if error:
        raise SchemaFailure("/payload/" + "/".join(map(str, error.absolute_path)), error.message)


def binding_shape(root: JsonObject, pointer: str) -> JsonValue:
    def shape(node: JsonObject) -> JsonValue:
        while "$ref" in node:
            node = resolve(root, node["$ref"])
        result: JsonObject = {}
        for key in ("type", "enum", "const", "required", "additionalProperties"):
            if key in node:
                value = node[key]
                result[key] = sorted(value) if key in {"type", "required"} and isinstance(value,list) else value
        properties = node.get("properties")
        if isinstance(properties,dict): result["properties"] = {key:shape(child) for key,child in properties.items()}
        items = node.get("items")
        if isinstance(items,dict): result["items"] = shape(items)
        branches = node.get("anyOf")
        if isinstance(branches,list): result["anyOf"] = [shape(child) for child in branches]
        return result
    return shape(schema_at(root,pointer))
