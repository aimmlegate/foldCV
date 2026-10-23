"""Check declared pinned protocol support before any authenticated turn."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/gui/handoffs/BACKGROUND-WORK/nb00b-evidence"
RETAINED_MANIFEST_SHA256 = "d50e282e4037181758769f84ba2018c5a8151d84beb7ebd4392c8b9b2436ddd8"
SCHEMAS = {
    "initialize": "v1/InitializeParams.json",
    "thread": "v2/ThreadStartParams.json",
    "turn": "v2/TurnStartParams.json",
    "interrupt": "v2/TurnInterruptParams.json",
    "toolCall": "DynamicToolCallParams.json",
    "toolReply": "DynamicToolCallResponse.json",
}


class ProtocolUnsupported(ValueError):
    pass


def load_pinned(*, runtime_identity=None):
    """Read the retained export; a different runtime needs its own evidence."""
    path = EVIDENCE / "pinned-schema-export.json"
    raw = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(raw).hexdigest() != RETAINED_MANIFEST_SHA256:
        raise ProtocolUnsupported("Pinned export provenance is invalid")
    manifest = json.loads(raw)
    identity = {key: manifest[key] for key in ("binarySha256", "hostSha256", "manifestSha256")}
    if runtime_identity is not None and runtime_identity != identity:
        raise ProtocolUnsupported("Retained schema does not prove this runtime")
    if (manifest["experimental"] is not True
            or manifest["nativeModelStarts"] != 0 or manifest["emptyProfile"] is not True):
        raise ProtocolUnsupported("Pinned export provenance is invalid")
    result = {}
    for name, relative in SCHEMAS.items():
        path = EVIDENCE / "pinned-schema" / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][relative]:
            raise ProtocolUnsupported("Pinned schema bytes changed")
        result[name] = json.loads(path.read_bytes())
    return result


def require_capabilities(schemas):
    try:
        initialize = schemas["initialize"]["definitions"]["InitializeCapabilities"]
        assert initialize["properties"]["experimentalApi"]["type"] == "boolean"
        thread = schemas["thread"]
        assert "dynamicTools" in thread["properties"] and "ephemeral" in thread["properties"]
        assert "config" in thread["properties"] and "developerInstructions" in thread["properties"]
        tools = thread["definitions"]["DynamicToolSpec"]["oneOf"]
        function = next(item for item in tools if item["properties"]["type"]["enum"] == ["function"])
        namespace = next(item for item in tools if item["properties"]["type"]["enum"] == ["namespace"])
        assert {"name", "description", "inputSchema", "type"} <= set(function["required"])
        assert {"name", "description", "tools", "type"} <= set(namespace["required"])
        assert "outputSchema" in schemas["turn"]["properties"]
        assert {"threadId", "input"} <= set(schemas["turn"]["required"])
        assert {"threadId", "turnId"} <= set(schemas["interrupt"]["required"])
        call = schemas["toolCall"]
        assert {"threadId", "turnId", "callId", "tool", "arguments"} <= set(call["required"])
        assert "namespace" in call["properties"]
        assert all(call["properties"][key]["type"] == "string" for key in ("threadId", "turnId", "callId", "tool"))
        assert {"contentItems", "success"} <= set(schemas["toolReply"]["required"])
        assert schemas["toolReply"]["properties"]["success"]["type"] == "boolean"
    except (AssertionError, KeyError, TypeError, StopIteration) as error:
        raise ProtocolUnsupported("Pinned protocol lacks required isolated-turn fields") from error
    return {"declaredSupport": True, "effectiveIsolationProved": False, "nativeGo": False}
