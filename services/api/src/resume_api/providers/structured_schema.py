"""Adapt output schemas without changing the application's optional fields."""

from __future__ import annotations

from copy import deepcopy
from types import UnionType
from typing import Annotated, Union, get_args, get_origin

from pydantic import AliasChoices, BaseModel, TypeAdapter, ValidationError


class StructuredSchema:
    def __init__(self, schema: dict):
        self.original = schema
        if schema.get("type") != "object":
            raise ValueError("output root must be an object")
        self.wire = self._adapt(deepcopy(schema))

    def _resolve(self, node: dict) -> dict:
        ref = node.get("$ref")
        if ref is None:
            return node
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ValueError("unsupported reference")
        value = self.original
        for key in ref[2:].split("/"):
            value = value[key.replace("~1", "/").replace("~0", "~")]
        if not isinstance(value, dict):
            raise ValueError("invalid reference")
        return value

    def _nullable(self, node: dict, seen: frozenset[str] = frozenset()) -> bool:
        ref = node.get("$ref")
        if ref is not None:
            if ref in seen:
                return False
            return self._nullable(self._resolve(node), seen | {ref})
        kind = node.get("type")
        if kind == "null" or isinstance(kind, list) and "null" in kind:
            return True
        return any(self._nullable(part, seen) for key in ("anyOf", "oneOf")
                   for part in node.get(key, []))

    def _adapt(self, node: dict) -> dict:
        if any(key in node for key in ("allOf", "not", "if", "then", "else", "dependentRequired", "dependentSchemas")):
            raise ValueError("unsupported composition")
        if "$ref" in node:
            self._resolve(node)
        node.pop("default", None)
        if "oneOf" in node:
            discriminator = node.get("discriminator", {}).get("propertyName")
            if not isinstance(discriminator, str):
                raise ValueError("exclusive union needs a fixed tag")
            tags = []
            for part in node["oneOf"]:
                branch = self._resolve(part)
                tag = branch.get("properties", {}).get(discriminator, {}).get("const")
                if not isinstance(tag, str) or discriminator not in branch.get("required", []):
                    raise ValueError("exclusive union needs distinct tags")
                tags.append(tag)
            if len(set(tags)) != len(tags):
                raise ValueError("overlapping union tags")
            node["anyOf"] = node.pop("oneOf")
        node.pop("discriminator", None)
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties")
            if not isinstance(properties, dict) or node.get("additionalProperties") is not False:
                raise ValueError("output objects must have fixed properties")
            required = set(node.get("required", []))
            for key, part in properties.items():
                nullable = self._nullable(part)
                adapted = self._adapt(part)
                if key not in required and not nullable:
                    # Null is the wire spelling of an omitted, defaulted field.
                    adapted = {"anyOf": [adapted, {"type": "null"}]}
                properties[key] = adapted
            node["required"] = list(properties)
        for part in node.get("$defs", {}).values():
            self._adapt(part)
        for key in ("anyOf", "oneOf", "prefixItems"):
            for part in node.get(key, []):
                self._adapt(part)
        if isinstance(node.get("items"), dict):
            self._adapt(node["items"])
        return node

    def restore(self, value: object, model: type[BaseModel]) -> object:
        return self._restore(model, value)

    def _restore(self, annotation, value: object) -> object:
        origin = get_origin(annotation)
        if origin is Annotated:
            return self._restore(get_args(annotation)[0], value)
        if origin in (Union, UnionType):
            branches = get_args(annotation)
            # Preserve already valid nullable values before interpreting wire nulls.
            for branch in branches:
                try:
                    TypeAdapter(branch).validate_python(value, strict=True)
                    return value
                except ValidationError:
                    pass
            results = []
            for branch in branches:
                try:
                    restored = self._restore(branch, value)
                    TypeAdapter(branch).validate_python(restored, strict=True)
                    results.append(restored)
                except (ValidationError, ValueError):
                    pass
            if results:
                if any(result != results[0] for result in results[1:]):
                    raise ValueError("ambiguous optional fields")
                return results[0]
            return value
        if origin is list and isinstance(value, list):
            return [self._restore(get_args(annotation)[0], part) for part in value]
        if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, dict):
            result = dict(value)
            for name, field in annotation.model_fields.items():
                alias = field.validation_alias
                if isinstance(alias, AliasChoices):
                    aliases = [choice for choice in alias.choices if isinstance(choice, str)]
                elif alias is None or isinstance(alias, str):
                    aliases = [alias if isinstance(alias, str) else field.alias or name]
                else:
                    aliases = []
                config = annotation.model_config
                if config.get("validate_by_alias") is False:
                    aliases = []
                if config.get("validate_by_name", config.get("populate_by_name", False)):
                    aliases.append(name)
                supplied = [alias for alias in dict.fromkeys(aliases) if alias in result]
                if len(supplied) > 1:
                    raise ValueError("ambiguous field aliases")
                key = supplied[0] if supplied else None
                if key is None:
                    continue
                part = result[key]
                if part is None and not field.is_required():
                    try:
                        TypeAdapter(field.annotation).validate_python(None, strict=True)
                    except ValidationError:
                        del result[key]
                        continue
                result[key] = self._restore(field.annotation, part)
            return result
        return value
