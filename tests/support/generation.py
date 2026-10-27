"""A content provider with controlled replies for rewrite and panel calls, and a frozen clock."""

from datetime import datetime, timezone
import json

from packages.resume_core.rich_panel import RichPanelProposal
from packages.resume_core.rich_sync import RichReconcileProposal, RichRewriteProposal
from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage


def frozen_now():
    return datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class CreationProvider:
    def __init__(self, fail_kind=None):
        self.fail_kind = fail_kind
        self.calls = []

    def generate_queued(self, request, files, cancel, admitted):
        admitted()
        return self.generate(request, files, cancel)

    def generate(self, request, _files, _cancel):
        if request.result_type is PlainTextReply:
            instruction, text = request.text.split("Instruction:\n", 1)[1].split("\n\nSelected text:\n", 1)
            self.calls.append({"task": "rewrite", "input": {"instruction": instruction, "text": text}})
            if instruction == "TEST_ERROR" or self.fail_kind in {"PlainTextReply", "RichRewriteProposal"}:
                raise ContentFailure("MODEL_DENIED")
            reply = PlainTextReply(text="\n\n".join("Clearer: " + part for part in text.split("\n\n")))
            return ContentResult(reply, ReportedUsage(), "fixture", request.policy.model, .01, 1)
        payload = json.loads(request.text)
        self.calls.append(payload)
        assert request.policy.allow_repair is False
        if request.result_type.__name__ == self.fail_kind:
            raise ContentFailure("MODEL_DENIED")
        if request.result_type is RichReconcileProposal:
            return ContentResult(RichReconcileProposal(updates=[]), ReportedUsage(), "fixture", request.policy.model, .01, 1)
        if request.result_type is RichPanelProposal:
            return ContentResult(RichPanelProposal(updates=[]), ReportedUsage(), "fixture", request.policy.model, .01, 1)
        assert request.result_type is RichRewriteProposal, request.result_type
        if payload["input"]["instruction"] == "TEST_ERROR":
            raise ContentFailure("MODEL_DENIED")
        replacements = []
        for block in payload["input"]["selection"]:
            output = json.loads(json.dumps(block))
            cell = output.pop("cellId", None)
            if cell:
                output = {"id": block["id"], "type": "paragraph", "revision": 1, "props": {}, "children": [], "provenance": [],
                    "content": output["content"]}
            if isinstance(output["content"], list):
                output["content"].insert(0, {"type": "text", "text": "Clearer: ", "styles": {}})
            elif isinstance(output["content"], str):
                output["content"] = "Clearer: " + output["content"]
            if "TEST_LIST" in payload["input"]["instruction"]:
                output["type"], output["props"] = "bullet_list", {}
            replacements.append({"blockId": block["id"], "cellId": cell, "blocks": [output]})
        reply = RichRewriteProposal.model_validate({"replacements": replacements})
        return ContentResult(reply, ReportedUsage(), "fixture", request.policy.model, .01, 1)
