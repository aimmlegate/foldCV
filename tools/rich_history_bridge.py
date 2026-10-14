"""Stateless typed fact/inverse bridge for the nonbrowser NE03A proof."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import TypeAdapter

from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.models.rich_mutations import PutRecord, RemoveRecord
from packages.resume_core.rich_fact_mutations import apply_record_mutations


def main() -> None:
    request = json.loads(sys.stdin.buffer.read(1024 * 1024 + 1))
    facts = WorkingFacts.model_validate(request["facts"])
    steps = TypeAdapter(list[PutRecord | RemoveRecord]).validate_python(request["steps"])
    action_id = request["actionId"]
    if not isinstance(action_id, str) or not action_id:
        raise ValueError("action identity required")
    result = apply_record_mutations(facts, steps, action_id)
    print(json.dumps({"facts": result.facts.model_dump(by_alias=True),
                      "inverse": [step.model_dump(by_alias=True) for step in result.inverse]}))


if __name__ == "__main__":
    main()
