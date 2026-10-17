"""Validate shared-turn evidence without pretending that each job owns a process."""

import hashlib
import json
import math


PROTOCOL = "shared_appserver_v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return type(value) in {float, int} and math.isfinite(value) and value >= 0


def artifact(root, case, path, *, lines=False):
    require(path in case["artifacts"], "Missing retained witness")
    target = root / path
    require(target.resolve().is_relative_to(root.resolve()), "Foreign witness")
    raw = target.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == case["artifacts"][path], "Changed witness")
    if lines:
        require(0 < len(raw) <= 72 * 1024 * 1024, "Unbounded wire witness")
        return [json.loads(line) for line in raw.splitlines()]
    return json.loads(raw)


def assert_shared_case(binding, variant, report, ledger, root, sources):
    case = report["variants"][variant]
    require(binding["transport"] == report["transport"] == PROTOCOL, "Wrong transport")
    require(case["outcome"] == "passed" and case["layer"] == "native" and report["sourceHashes"] == sources,
        "Unproved current source")
    pool_name, pool = binding["pool"], ledger["pools"][binding["pool"]]
    from spikes.background.native_turn_budget import matrix_budget
    cap, _rows, _historical, _retry = matrix_budget(ledger, pool_name,
        retry_authority=root / "docs/gui/handoffs/BACKGROUND-WORK/native-feasibility-retry-authorization.json",
        retry_proposal=root / "docs/gui/handoffs/BACKGROUND-WORK/nb00b-evidence/native-retry-proposal.md",
        repair_authority=root / "docs/gui/handoffs/BACKGROUND-WORK/native-feasibility-repair-authorization.json",
        repair_proposal=root / "docs/gui/handoffs/BACKGROUND-WORK/nb00b-evidence/publication-retry-proposal.md")
    require(pool_name in {"NB00", "NB07b"} and pool["authorized"] is True
        and pool["cap"] == cap
        and type(pool["spent"]) is int and 0 < pool["spent"] <= pool["cap"]
        and pool["spent"] == len([row for row in ledger["attempts"] if row["pool"] == pool_name]), "Wrong native pool")
    roles = binding["roles"]
    turns = case["turns"]
    require(isinstance(roles, list) and roles and [turn["role"] for turn in turns] == roles
        and len({turn["attemptId"] for turn in turns}) == len(turns), "Wrong group roles")
    if binding.get("coveredBySameActualTurn"):
        require(len(turns) == 1 and roles == [binding["attemptRole"]] and case["coveredBy"] == binding["attemptVariant"], "Wrong publication alias")
        parent = report["variants"][binding["attemptVariant"]]
        require(parent["outcome"] == "passed" and turns[0] in parent["turns"], "Alias is not the same actual turn")
    for path in case["artifacts"]:
        target = root / path
        require(target.resolve().is_relative_to(root.resolve())
            and hashlib.sha256(target.read_bytes()).hexdigest() == case["artifacts"][path], "Changed native artifact")
    shutdown = artifact(root, case, case["shutdownArtifact"])
    require(shutdown["status"] == "stopped" and shutdown["ownedPidsGone"] is True
        and shutdown["operationRemoved"] is True
        and shutdown["profileExclusionLost"] is False, "Unproved final server shutdown")
    owner = artifact(root, case, case["ownerShutdownArtifact"])
    require(owner["status"] == "stopped" and owner["profileLockReleased"] is True
        and owner["ownedPidsGone"] is True and owner["operationRemoved"] is True
        and owner["profileExclusionLost"] is False, "Unproved final service ownership release")
    wire = artifact(root, case, case["wireArtifact"], lines=True)
    require(wire and all(number(frame["at"]) and frame["direction"] in {"client", "server"} for frame in wire), "Invalid wire clock")
    runtimes = []
    for turn in turns:
        attempt = next(row for row in ledger["attempts"] if row["id"] == turn["attemptId"])
        actual_variant = binding.get("attemptVariant", variant)
        require(attempt["pool"] == pool_name and attempt["variant"] == actual_variant
            and attempt["role"] == turn["role"] and attempt["status"] == "passed" and attempt["sourceHashes"] == sources
            and attempt["model"] == "gpt-6-luna" and attempt["effort"] == "medium"
            and attempt["transport"] == "one pinned multiplexed App Server", "Wrong charged model turn")
        if _historical:
            require(attempt.get("historicalStarts") == _historical
                and attempt.get("retryAuthoritySha256") == _retry, "Wrong retry authority")
        runtime = artifact(root, case, turn["runtimeArtifact"])
        expected_state = binding.get("states", {}).get(turn["role"], "completed")
        require(runtime["transport"] == PROTOCOL and runtime["nativeStarted"] is True
            and runtime["jobId"] == attempt["jobId"] and runtime["role"] == turn["role"]
            and runtime["state"] == expected_state and runtime["error"] == ("CANCELLED" if expected_state == "cancelled" else None),
            "Wrong runtime outcome")
        require(type(runtime["serverPid"]) is int and runtime["serverPid"] > 0
            and runtime["serverPid"] == shutdown["serverPid"] and runtime["hostPids"]
            and set(runtime["hostPids"]) <= set(shutdown["hostPids"])
            and runtime["sharedProcessDead"] is False and runtime["profileExclusionLost"] is False,
            "False per-job process claim")
        require(all(runtime[name] is True for name in ("toolsClosed", "parserClosed", "operationRemoved", "turnResourcesClosed", "cleanupVerified")),
            "Unclosed turn resources")
        require(number(runtime["startedAt"]) and number(runtime["endedAt"])
            and runtime["startedAt"] < runtime["endedAt"], "Invalid turn interval")
        agent = turn["role"].startswith("agent-")
        require((runtime["toolCalls"] >= (1 if expected_state == "cancelled" else 2) and runtime["mcpListenerClosed"] is True)
            if agent else (runtime["toolCalls"] == 0 and runtime["schemaValidated"] is True
                and runtime["logicalAttempts"] == 1 and runtime["repairTurns"] == 0), "Missing tools or structured grammar")
        def events(method, direction):
            return [frame for frame in wire if frame["direction"] == direction
                and frame["frame"].get("method") == method
                and frame["frame"].get("params", {}).get("threadId") == runtime["threadId"]]
        starts, began, ended = events("turn/start", "client"), events("turn/started", "server"), events("turn/completed", "server")
        require(len(starts) == len(began) == len(ended) == 1
            and began[0]["frame"]["params"]["turn"]["id"] == ended[0]["frame"]["params"]["turn"]["id"] == runtime["turnId"]
            and ended[0]["frame"]["params"]["turn"]["status"] == ("interrupted" if expected_state == "cancelled" else "completed")
            and began[0]["at"] == runtime["startedAt"] and ended[0]["at"] == runtime["endedAt"], "No actual turn interval")
        if not agent:
            require(starts[0]["frame"]["params"].get("outputSchema"), "Missing pinned output grammar")
            publication = runtime["fixedPublication"]
            job = artifact(root, case, publication["jobArtifact"])
            require(publication["exactRequestedChange"] is True and job["id"] == runtime["jobId"]
                and job["execution"] == "completed" and job["publication"] == "saved"
                and job["receipt"]["durable"] is True and job["receipt"]["jobId"] == job["id"],
                "Unproved fixed publication")
        calls = events("item/tool/call", "server")
        unique = {}
        for item in calls:
            frame, params = item["frame"], item["frame"]["params"]
            require(params["turnId"] == runtime["turnId"] and params["namespace"] == runtime["namespace"]
                and params["tool"] in runtime["toolNames"] and runtime["startedAt"] <= item["at"] <= runtime["endedAt"],
                "Foreign tool capability")
            previous = unique.setdefault(params["callId"], frame)
            require(previous == frame, "Tool identity was reused")
            replies = [row for row in wire if row["direction"] == "client" and row["frame"].get("id") == frame["id"]
                and "method" not in row["frame"]]
            require(replies or expected_state == "cancelled", "Missing routed tool reply")
        require(len(unique) == runtime["toolCalls"], "False native tool count")
        if expected_state == "cancelled":
            stops = events("turn/interrupt", "client")
            require(len(stops) == 1 and stops[0]["frame"]["params"]["turnId"] == runtime["turnId"], "Wrong interrupt target")
        if variant in {"NB-X03:v01", "NB-X03:v02"}:
            publication = runtime["publication"]
            require(publication["exactRequestedText"] is True and publication["onePreparedBatch"] is True
                and publication["oneApply"] is True and publication["durableReceipt"] is True
                and publication["noNewTurnForSave"] is True and publication["factsAndOtherContentUnchanged"] is True,
                "Unproved exact publication")
            if variant == "NB-X03:v02":
                require(publication["turnResourcesExitedBeforeSave"] is True
                    and publication["canonicalUnchangedUntilReturn"] is True, "Unproved deferred publication")
        runtimes.append(runtime)
    require(len({item["threadId"] for item in runtimes}) == len(runtimes)
        and len({item["turnId"] for item in runtimes}) == len(runtimes), "Shared turn context")
    if len(runtimes) > 1:
        require(max(item["startedAt"] for item in runtimes) < min(item["endedAt"] for item in runtimes), "No true overlap")
        starts = [item for item in wire if item["direction"] == "client" and item["frame"].get("method") == "turn/start"]
        require(len(starts) == len(runtimes), "Hidden or missing model turn")
    if any(item["state"] == "cancelled" for item in runtimes):
        cancelled = next(item for item in runtimes if item["state"] == "cancelled")
        stop = next(item for item in wire if item["direction"] == "client" and item["frame"].get("method") == "turn/interrupt")
        require(any(item["direction"] == "server" and item["frame"].get("method") in {"item/tool/call", "item/agentMessage/delta"}
            and item["frame"].get("params", {}).get("threadId") != cancelled["threadId"] and item["at"] > stop["at"] for item in wire),
            "Neighbor did not progress after targeted cancellation")
