"""Synthetic loopback fixture for the gated two-operation browser path."""

import asyncio
import json
from pathlib import Path
import socket
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from packages.resume_core.drafting import DraftProposal, draft_input, draft_selection, validate_draft
from packages.resume_core.normalization import FactSheet, literal_sheet
from resume_api.app import create_app


class ForbiddenRunner:
    async def run(self, kind, request, files):
        (Path(sys.argv[1]) / "generation-attempt").touch()
        raise AssertionError("unexpected generic generation")


class Semantic:
    def run(self, request, files, cancel):
        if any("FAIL_NORMALIZE" in unit.text for source in request.sources for unit in source.result.units):
            raise ValueError("synthetic normalization failure")
        sheet = literal_sheet(request).model_dump(mode="json", by_alias=True)
        units = [(source.result.source_id, unit) for source in request.sources for unit in source.result.units]
        for index, (source_id, unit) in enumerate(units[:2]):
            fact_id = f"fact_fixture_{index}"
            job_id = "job_fixture_recent" if index == 1 else None
            sheet["facts"].append({"id": fact_id, "revision": 1, "kind": "text",
                                   "value": {"text": unit.text}, "evidence": [{"sourceId": source_id,
                                   "sourceRevision": 1, "unitId": unit.id, "unitRevision": 1}],
                                   "origin": "source", "importance": "essential", "jobId": job_id,
                                   "subprojectId": None})
            account = next(item for item in sheet["units"] if item["sourceId"] == source_id and item["unitId"] == unit.id)
            account["disposition"] = "facts"
            account["factIds"].append(fact_id)
        if len(units) > 1:
            source_id, unit = units[1]
            sheet["employment"] = [{"id": "job_fixture_recent", "employer": "Example Works",
                                    "role": "Developer", "periods": [{"start": {"precision": "year", "year": 2022,
                                    "month": None, "day": None}, "end": {"precision": "year", "year": 2025,
                                    "month": None, "day": None}}], "sourceId": source_id, "unitIds": [unit.id],
                                    "subprojects": [], "factIds": ["fact_fixture_1"], "reviewRequired": True}]
        if any("PRIVATE_FIELD" in unit.text for _, unit in units) and sheet["employment"]:
            private = "contact me at 555-123-4567"
            sheet["facts"].extend([
                {"id": "fact_fixture_private_metric", "revision": 1, "kind": "metric",
                 "value": {"number": 20, "upperNumber": None, "comparator": "exact", "unit": "teams",
                           "period": None, "baseline": None, "result": None, "scope": private,
                           "attribution": "team", "qualifiers": []}, "evidence": [], "origin": "user",
                 "importance": "essential", "jobId": "job_fixture_recent", "subprojectId": None},
                {"id": "fact_fixture_private_mixed", "revision": 1, "kind": "text",
                 "value": {"text": "Built a service for 20 teams. Call 555-123-4567."},
                 "evidence": [], "origin": "user", "importance": "essential",
                 "jobId": "job_fixture_recent", "subprojectId": None},
            ])
            sheet["employment"][0]["factIds"].extend(["fact_fixture_private_metric", "fact_fixture_private_mixed"])
        return FactSheet.model_validate(sheet), {"logicalAttempts": 1, "inputTokens": 10,
                                                "outputTokens": 10, "inferenceCount": None}


class Draft:
    def run(self, request, files, cancel):
        prompt = draft_input(request)
        if any("ALL_PRIVATE" in fact.value.text for fact in request.sheet.facts if fact.kind == "text"):
            (Path(sys.argv[1]) / "provider-started").touch()
        if any("PRIVATE_FIELD" in fact.value.text for fact in request.sheet.facts if fact.kind == "text"):
            guard = {"containsPrivateText": "555-123-4567" in prompt,
                     "containsPrivateIds": "fact_fixture_private_metric" in prompt or
                     "fact_fixture_private_mixed" in prompt}
            (Path(sys.argv[1]) / "draft-payload-guard.json").write_text(json.dumps(guard))
        selection = draft_selection(request)
        proposal = DraftProposal(blocks=[{"blockId": block_id,
            "text": "Drafted: " + " ".join(fact.value.text for fact in facts if fact.kind == "text"),
            "factIds": [fact.id for fact in facts]} for block_id, facts in selection.items()])
        return validate_draft(request, proposal), {"logicalAttempts": 1, "inputTokens": 10,
                                                   "outputTokens": 10, "inferenceCount": None}


async def main():
    root = Path(sys.argv[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-browser-secret-0123456789",
                         temp_root=root / "operations", dist=Path(sys.argv[2]), runner=ForbiddenRunner(),
                         semantic_runner=Semantic(), draft_runner=Draft(), fixture_generation_ready=True)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False,
                                                access_log=False, log_level="critical",
                                                timeout_graceful_shutdown=2))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Fixture server failed")
            await asyncio.sleep(0.01)
        print(origin, flush=True)
        await task


if __name__ == "__main__":
    asyncio.run(main())
