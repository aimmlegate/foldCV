"""Independent specification oracle and frozen input grammar; no product imports."""

from __future__ import annotations

from dataclasses import dataclass, field
import random

FIXED_SEEDS = tuple(range(16))
FIXED_TRANSITIONS = 200
INTEGRATED_SEEDS = tuple(range(128))
INTEGRATED_TRANSITIONS = 300
ACTIONS = ("submit", "duplicate", "start", "propose", "runtime_exit", "touch", "undo", "claim",
    "timeout", "input", "deliver", "detach", "attach", "restart", "stop", "delete", "tick")
ORDERS = ("timeout_before_claim", "claim_before_timeout", "runtime_exit_before_publication")


@dataclass
class ReferenceModel:
    """Truth from a chronological operation history, not production transition helpers."""

    capacity: int
    log: list[dict] = field(default_factory=list)
    projects: dict = field(default_factory=lambda: {project: {"deleted": False, "writer": writer,
        "generations": {"X": 0, "Y": 0, "shared": 0}, "values": {"X": "original", "Y": "original", "shared": "read only"},
        "draft": None, "cursor": 0} for project, writer in (("A", 0), ("B", 1))})
    jobs: dict = field(default_factory=dict)
    clock: int = 0

    def step(self, action, project, job, *, read="shared", write=None):
        p = self.projects[project]
        target = write or ("Y" if job == "two" else "X")
        existing = self.jobs.get(job)
        j = existing if existing and existing["project"] == project else None
        result = "rejected"
        if action == "submit" and not p["deleted"] and len(self.jobs) < 3 and existing is None:
            self.jobs[job] = {"project": project, "state": "queued", "proposal": False, "authority": True,
                "reads": read, "writes": target, "captured": {}, "claimed": False, "barrier": False, "saved": False}
            result = "accepted"
        elif action == "duplicate" and j and j["project"] == project:
            result = "replay"
        elif action == "start" and j and j["state"] == "queued" and not p["deleted"]:
            if sum(item["state"] == "running" for item in self.jobs.values()) < self.capacity:
                j["state"] = "running"
                result = "started"
        elif action == "propose" and j and j["state"] == "running" and not j["proposal"] and not p["deleted"]:
            if sum(item["proposal"] for item in self.jobs.values()) < 2:
                j["proposal"] = True
                j["captured"] = {key: p["generations"][key] for key in {j["reads"], j["writes"]}}
                j["barrier"] = True
                result = "stored"
        elif action == "runtime_exit" and j and j["state"] == "running":
            j["state"] = "completed"
            result = "released"
        elif action in {"touch", "undo"} and not p["deleted"]:
            p["generations"][target] += 1
            p["values"][target] = "original" if action == "undo" else "edited"
            p["cursor"] += 1
            result = "touched"
        elif action == "claim" and j and j["project"] == project and j["proposal"] and j["authority"] and not p["deleted"]:
            if all(p["generations"][key] == generation for key, generation in j["captured"].items()) and j["barrier"] and not j["claimed"]:
                j["claimed"] = True
                p["values"][j["writes"]] = "saved-" + job
                p["generations"][j["writes"]] += 1
                result = "claimed"
        elif action == "timeout" and j:
            j["barrier"] = False
            result = "recovering" if j["claimed"] else "revoked"
        elif action == "input" and not p["deleted"]:
            p["cursor"] += 1
            p["draft"] = f"draft-{p['cursor']}"
            result = "checkpointed"
        elif action == "deliver" and j and j["claimed"]:
            if not j["saved"]:
                j["saved"] = True
            result = "saved"
        elif action in {"detach", "attach"} and not p["deleted"]:
            p["writer"] = None if action == "detach" else 1 - (p["writer"] or 0)
            result = "writer_changed"
        elif action == "restart":
            for item in self.jobs.values():
                if item["state"] == "running":
                    item["state"] = "interrupted"
            result = "recovered_without_inference"
        elif action == "stop" and j:
            j["authority"] = False
            j["state"] = "cancelled"
            result = "cancelled"
        elif action == "delete":
            p["deleted"] = True
            for item in self.jobs.values():
                if item["project"] == project:
                    item["authority"] = False
            result = "tombstoned"
        elif action == "tick":
            self.clock += 750
            result = "advanced"
        scoped = self.jobs.get(job)
        self.log.append({"action": action, "project": project, "job": job, "result": result, "clock": self.clock,
            "read": scoped["reads"] if scoped else read, "write": target if action in {"touch", "undo"} else scoped["writes"] if scoped else target})
        if sum(item["state"] == "running" for item in self.jobs.values()) > self.capacity:
            raise AssertionError("oracle capacity violated")
        return result


def reached_orders(log):
    def position(action, job, result):
        return next((i for i, row in enumerate(log) if row["action"] == action and row["job"] == job and row["result"] == result), None)
    orders = []
    for first, first_result, second, second_result, job, label in (
        ("timeout", "revoked", "claim", "rejected", "two", ORDERS[0]),
        ("claim", "claimed", "timeout", "recovering", "one", ORDERS[1]),
        ("runtime_exit", "released", "claim", "claimed", "one", ORDERS[2]),
    ):
        left, right = position(first, job, first_result), position(second, job, second_result)
        if left is not None and right is not None and left < right:
            orders.append(label)
    return orders


def trace(seed: int, transitions: int = FIXED_TRANSITIONS, capacity: int = 1):
    if capacity not in (1, 3) or transitions < 40:
        raise ValueError("invalid frozen corpus")
    oracle = ReferenceModel(capacity)
    prefix = [("submit", "A", "one"), ("duplicate", "A", "one"), ("start", "A", "one"),
        ("propose", "A", "one"), ("runtime_exit", "A", "one"), ("claim", "A", "one"),
        ("timeout", "A", "one"), ("input", "A", "one"), ("deliver", "A", "one"),
        ("touch", "A", "one"), ("undo", "A", "one"), ("detach", "A", "one"), ("attach", "A", "one"),
        ("submit", "B", "two"), ("start", "B", "two"), ("propose", "B", "two"),
        ("timeout", "B", "two"), ("claim", "B", "two"), ("restart", "B", "two"),
        ("submit", "B", "three"), ("stop", "B", "three"), ("tick", "B", "two")]
    rng = random.Random(seed)
    while len(prefix) < transitions - 1:
        prefix.append((rng.choice(ACTIONS[:-2]), rng.choice(("A", "B")), rng.choice(("one", "two", "three"))))
    prefix.append(("delete", "B", "two"))
    for action, project, job in prefix:
        oracle.step(action, project, job)
    reached = sorted({row["action"] for row in oracle.log if row["result"] != "rejected"})
    if set(reached) != set(ACTIONS):
        raise AssertionError("required oracle action was not reached")
    return {"id": f"fixed:{capacity}:{seed}", "seed": seed, "capacity": capacity,
        "transitions": transitions, "actions": reached, "orders": reached_orders(oracle.log), "log": oracle.log,
        "scope": "specification_oracle_only"}
