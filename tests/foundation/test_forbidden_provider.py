"""Paths that must not call a model fail on the shared app fixtures, at the production call shape."""

import asyncio

import pytest

from tests.projects.support import v2_app
from tests.service.app_fixtures import make_app
from tests.support.foundation import ForbiddenContentProvider


def rewrite(app):
    return asyncio.run(app.state.projects.rewrite_text("project", "request", "shorter", "text"))


def test_the_provider_fails_at_the_production_call_shape():
    with pytest.raises(AssertionError, match="unexpected model call"):
        ForbiddenContentProvider().generate(object(), object(), object())


def test_v2_app_refuses_a_model_call_by_default(tmp_path):
    with v2_app(tmp_path) as (_client, app):
        with pytest.raises(AssertionError, match="unexpected model call"):
            rewrite(app)


def test_make_app_refuses_a_model_call_by_default(tmp_path):
    with pytest.raises(AssertionError, match="unexpected model call"):
        rewrite(make_app(tmp_path).app)


def test_a_test_can_still_inject_its_own_provider(tmp_path):
    class Refusing:
        def generate(self, _request, _files, _cancel):
            raise LookupError("injected")

    with v2_app(tmp_path, content_provider=Refusing()) as (_client, app):
        with pytest.raises(LookupError, match="injected"):
            rewrite(app)
