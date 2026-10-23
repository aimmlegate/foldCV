"""Bounded JSON-compatible YAML loading with explicit scalar semantics."""

from __future__ import annotations

import json
import math
import re

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .projection import SchemaFailure

CONFIG_BYTES = 2 * 1024 * 1024
CONFIG_DEPTH = 64
CONFIG_NODES = 50_000


def finite_number(value):
    parsed = float(value)
    if not math.isfinite(parsed): raise SchemaFailure('/', 'non-finite number')
    if parsed == 0.0 and any(character in '123456789' for character in value.lower().split('e')[0]):
        raise SchemaFailure('/', 'number outside the supported range')
    return parsed


def load_declared_definition(raw: bytes, original_format: str) -> dict:
    if original_format=='yaml':return load_definition(raw)
    if original_format!='json':raise SchemaFailure('/', 'unsupported configuration format')
    if len(raw)>CONFIG_BYTES:raise SchemaFailure('/', 'configuration exceeds technical byte limit')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise SchemaFailure('/', 'duplicate key: '+key)
            result[key]=value
        return result
    def constant(_value):raise SchemaFailure('/', 'non-JSON numeric constant')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_float=finite_number,parse_constant=constant)
        count=0
        def check(value,path,depth):
            nonlocal count
            count+=1
            if depth>CONFIG_DEPTH or count>CONFIG_NODES:
                raise SchemaFailure(path, 'configuration exceeds technical nesting/node limit')
            if isinstance(value,dict):
                for key,child in value.items():
                    key.encode('utf-8');check(child,path+'/'+key,depth+1)
            elif isinstance(value,list):
                for index,child in enumerate(value):check(child,path+'/'+str(index),depth+1)
            elif isinstance(value,str):value.encode('utf-8')
        check(value,'',0)
        if not isinstance(value,dict):raise SchemaFailure('/', 'template must be an object')
        return value
    except (UnicodeError,ValueError,RecursionError) as error:
        raise SchemaFailure('/', 'invalid JSON: '+str(error).splitlines()[0]) from None


def load_definition(raw: bytes) -> dict:
    if len(raw) > CONFIG_BYTES:
        raise SchemaFailure("/", "configuration exceeds technical byte limit")
    try:
        text = raw.decode("utf-8")
        if any(isinstance(event, AliasEvent) for event in yaml.parse(text, Loader=yaml.SafeLoader)):
            raise SchemaFailure("/", "YAML aliases are unsupported")
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        count = 0

        def read(value, path, depth):
            nonlocal count
            count += 1
            if depth > CONFIG_DEPTH or count > CONFIG_NODES:
                raise SchemaFailure(path, "configuration exceeds technical nesting/node limit")
            if isinstance(value, MappingNode):
                if value.tag != "tag:yaml.org,2002:map": raise SchemaFailure(path, "unsupported mapping tag")
                result = {}
                for key, child in value.value:
                    if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                        raise SchemaFailure(path, "mapping keys must be strings")
                    if key.value in result: raise SchemaFailure(path + "/" + key.value, "duplicate key")
                    result[key.value] = read(child, path + "/" + key.value, depth + 1)
                return result
            if isinstance(value, SequenceNode):
                if value.tag != "tag:yaml.org,2002:seq": raise SchemaFailure(path, "unsupported sequence tag")
                return [read(child, f"{path}/{i}", depth + 1) for i, child in enumerate(value.value)]
            if not isinstance(value, ScalarNode): raise SchemaFailure(path, "empty configuration")
            kind = value.tag.removeprefix("tag:yaml.org,2002:")
            if kind == "str": return value.value
            if kind == "null" and value.value.lower() in {"null", "~", ""}: return None
            if kind == "bool" and value.value.lower() in {"true", "false"}: return value.value.lower() == "true"
            if kind in {"int", "float"} and re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", value.value):
                return json.loads(value.value, parse_float=finite_number)
            raise SchemaFailure(path, "implicit non-JSON scalar or unsupported tag")

        result = read(node, "", 0)
        if not isinstance(result, dict): raise SchemaFailure("/", "template must be an object")
        return result
    except SchemaFailure:
        raise
    except (yaml.YAMLError, UnicodeError, ValueError, RecursionError) as error:
        raise SchemaFailure("/", "invalid YAML/JSON: " + str(error).splitlines()[0]) from None
