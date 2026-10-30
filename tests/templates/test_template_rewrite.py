"""V7 selected-text rewrite: one counted generation, exact source text, cancellation and failures without edits."""

import asyncio
import contextlib
import threading

import pytest

from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.projects.errors import ProjectFailure
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage
from resume_api.template_rewrite import TemplateRewrite


class Provider:
    def __init__(self, reply=None, failure=None, hold=None):
        self.requests, self.reply, self.failure, self.hold = [], reply, failure, hold

    def generate(self, request, _files, cancel):
        self.requests.append(request)
        if self.hold is not None:
            self.hold.set()
            while not cancel.wait(.01):
                pass
            raise ContentFailure('CANCELLED')
        if self.failure:
            raise ContentFailure(self.failure)
        return ContentResult(PlainTextReply(text=self.reply), ReportedUsage(), 'scripted', request.policy.model, 0, 1)


@contextlib.asynccontextmanager
async def worker_slot(_cancel):
    yield


def Service(tmp_path, provider):
    return TemplateRewrite(lambda: (provider, 'scripted-model'), preferences=None, temp_root=tmp_path,
        worker_slot=worker_slot, cleanup_error=lambda _error: None)


def test_preview_sends_only_the_selected_text_and_returns_the_plain_reply(tmp_path):
    provider = Provider(reply='Built queue processing.')
    service = Service(tmp_path, provider)
    text = asyncio.run(service.text('project', 'request-1', 'Make it shorter', 'Implemented queue processing.'))
    assert text == 'Built queue processing.'
    assert len(provider.requests) == 1
    prompt = provider.requests[0].text
    assert 'Make it shorter' in prompt and 'Implemented queue processing.' in prompt
    assert provider.requests[0].policy.allow_repair is False
    assert service.cancels == {} and service.tasks == {}


def test_failure_and_cancellation_report_codes_and_release_the_request(tmp_path):
    failing = Service(tmp_path, Provider(failure='MODEL_DENIED'))
    with pytest.raises(ProjectFailure) as failed:
        asyncio.run(failing.text('project', 'request-2', 'x', 'text'))
    assert (failed.value.code, failed.value.status) == ('MODEL_DENIED', 502)
    held = threading.Event()
    service = Service(tmp_path, Provider(hold=held))
    async def run():
        task = asyncio.create_task(service.text('project', 'request-3', 'x', 'text'))
        assert await asyncio.to_thread(held.wait, 5)
        assert service.cancel('project', 'request-3') is True
        with pytest.raises(ProjectFailure) as cancelled:
            await task
        return cancelled.value
    error = asyncio.run(run())
    assert (error.code, error.status) == ('CANCELLED', 409)
    # A cancel for a request that is not registered is remembered as an early cancel, so it is never refused.
    assert service.cancel('project', 'request-3') is True
    assert service.cancels == {}
