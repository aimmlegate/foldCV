"""Fail-closed scripted providers shared by fixture creation and the UIR service."""

import hashlib
import json
import threading

from packages.resume_core.models.agent import AgentWebSource
from packages.resume_core.resume_assessment import ResumeAssessment
from resume_api.agent.runtime import RuntimeResult
from resume_api.connection import Metadata, Quota
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage
from tests.recovery.generation_fixtures import CreationProvider
from spikes.uir.fixtures import extraction_reply, NOW


class ScriptedConnection:
    def __init__(self): self.calls = []
    def inspect(self, _files, _cancel, *, full=True):
        self.calls.append("inspect")
        return Metadata("uir-scripted", ("uir-processing", "uir-assistant"), "plus", Quota("available", 0))
    def login(self, *_args, **_kwargs):
        self.calls.append("scripted_login")
        return None
    def detach(self, *_args, **_kwargs): self.calls.append("scripted_detach")


class ScriptedContent(CreationProvider):
    def __init__(self):
        super().__init__()
        self.pause_type = None
        self.entered = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.attempts = []

    def generate(self, request, files, cancel):
        kind = request.result_type.__name__
        self.attempts.append(kind)
        if kind == self.pause_type:
            self.entered.set()
            while not self.release.wait(.02):
                if cancel.is_set():
                    raise ContentFailure("CANCELLED")
        if kind == self.fail_kind:
            raise ContentFailure("MODEL_DENIED")
        if request.result_type in {ResumeAssessment} or request.result_type.__name__ in {
                "RichRewriteProposal", "RichReconcileProposal", "RichPanelProposal"}:
            return super().generate(request, files, cancel)
        if request.result_type.__name__ != "GuiSemanticProposal":
            raise ContentFailure("UIR_UNSCRIPTED_PROVIDER_PATH")
        payload = json.loads(request.text)
        self.calls.append(payload)
        return ContentResult(extraction_reply(payload), ReportedUsage(), "uir-scripted", request.policy.model, 0, 1)


class StoredWeb:
    def __init__(self): self.calls = []
    async def fetch(self, url, _cancel):
        self.calls.append(url)
        text = "Synthetic UIR stored page. No external retrieval."
        return AgentWebSource(id="uir-stored-page", runId="unbound", requestedUrl=url, finalUrl=url,
            title="Synthetic UIR page", retrievedAt=NOW, contentSha256=hashlib.sha256(text.encode()).hexdigest(),
            text=text, truncated=False, originalBytes=len(text.encode()))


async def scripted_agent(_value, _cancel, _emit):
    raise AssertionError("UIR00–UIR01 must not send assistant requests")
