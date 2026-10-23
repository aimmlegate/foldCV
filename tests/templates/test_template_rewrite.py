"""V7 selected-text rewrite: one counted generation, exact source text, cancellation and failures without edits."""

import asyncio
import contextlib
import threading

import pytest

from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.gui_projects import ProjectFailure
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


class Service(TemplateRewrite):
    def __init__(self, tmp_path, provider):
        self.provider, self.preferences, self.temp_root = provider, None, tmp_path
        self.tasks, self.cancels, self.files = {}, {}, {}

    def provider_factory(self):
        return self.provider, 'scripted-model'

    @contextlib.asynccontextmanager
    async def worker_slot(self, _cancel):
        yield


def test_preview_sends_only_the_selected_text_and_returns_the_plain_reply(tmp_path):
    provider = Provider(reply='Built queue processing.')
    service = Service(tmp_path, provider)
    text = asyncio.run(service.template_rewrite_text('project', 'request-1', 'Make it shorter', 'Implemented queue processing.'))
    assert text == 'Built queue processing.'
    assert len(provider.requests) == 1
    prompt = provider.requests[0].text
    assert 'Make it shorter' in prompt and 'Implemented queue processing.' in prompt
    assert provider.requests[0].policy.allow_repair is False
    assert service.cancels == {} and service.tasks == {}


def test_failure_and_cancellation_report_codes_and_release_the_request(tmp_path):
    failing = Service(tmp_path, Provider(failure='MODEL_DENIED'))
    with pytest.raises(ProjectFailure) as failed:
        asyncio.run(failing.template_rewrite_text('project', 'request-2', 'x', 'text'))
    assert (failed.value.code, failed.value.status) == ('MODEL_DENIED', 502)
    held = threading.Event()
    service = Service(tmp_path, Provider(hold=held))
    async def run():
        task = asyncio.create_task(service.template_rewrite_text('project', 'request-3', 'x', 'text'))
        while not held.is_set():
            await asyncio.sleep(.01)
        assert service.template_rewrite_cancel('project', 'request-3') is True
        with pytest.raises(ProjectFailure) as cancelled:
            await task
        return cancelled.value
    error = asyncio.run(run())
    assert (error.code, error.status) == ('CANCELLED', 409)
    assert service.template_rewrite_cancel('project', 'request-3') is False
    assert service.cancels == {}
