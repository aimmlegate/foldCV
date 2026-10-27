"""Admitted generation counts one attempt per call and never repairs, unlike the provider's own default."""

from dataclasses import replace
import threading

import pytest

from resume_api.lifecycle import OperationFiles
from resume_api.providers.admitted import generate_admitted
from resume_api.providers.codex_cli import CodexCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure, ContentResult, GenerationPolicy, ReportedUsage
from tests.providers.fixtures import Summary, fake, request  # noqa: F401 (fake is a fixture)

# The fake CLI starts five child processes per call; a generous deadline keeps a loaded machine from failing them.
TIMEOUT = 60


@pytest.mark.parametrize("admitted,attempts,starts", [(True, 1, 1), (False, 2, 2)])
def test_admitted_invalid_result_never_repairs_but_the_provider_default_does(fake, admitted, attempts, starts):
    cli, root, keep, configure, count = fake
    configure("repair")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        if admitted:
            with pytest.raises(ContentFailure) as error:
                generate_admitted(provider, request(timeout=TIMEOUT), files, threading.Event())
            assert error.value.code == "INVALID_RESULT"
            assert error.value.logical_attempts == attempts
            assert error.value.usage.input_tokens == 100
        else:
            result = provider.generate(request(timeout=TIMEOUT), files, threading.Event())
            assert result.logical_attempts == attempts
            assert result.usage.input_tokens == 200
    assert count() == starts
    assert list(root.iterdir()) == [keep]


@pytest.mark.parametrize("code", ["AUTH_REQUIRED", "MODEL_DENIED", "CLI_UNSUPPORTED"])
@pytest.mark.parametrize("reported", [0, 1, 2])
def test_admitted_failure_counts_once_without_adding_to_provider_count(tmp_path, code, reported):
    class Provider:
        def generate(self, content, _files, _cancel):
            assert content.policy.allow_repair is False
            raise ContentFailure(code, logical_attempts=reported)

    with pytest.raises(ContentFailure) as error:
        generate_admitted(Provider(), request(timeout=TIMEOUT), OperationFiles(tmp_path), threading.Event())
    assert error.value.logical_attempts == max(1, reported)
    assert error.value.usage.input_tokens is None
    assert error.value.usage.output_tokens is None
    assert not error.value.usage.complete


@pytest.mark.parametrize("admitted", [True, False])
def test_real_adapter_early_model_denial_has_one_admitted_attempt_but_no_inference(fake, admitted):
    cli, root, keep, _configure, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    content = replace(request(timeout=TIMEOUT), policy=GenerationPolicy("denied-model", timeout_seconds=TIMEOUT))
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure) as error:
        if admitted:
            generate_admitted(provider, content, files, threading.Event())
        else:
            provider.generate(content, files, threading.Event())
    assert error.value.code == "MODEL_DENIED"
    assert error.value.logical_attempts == (1 if admitted else 0)
    assert starts() == 0
    assert list(root.iterdir()) == [keep]


def test_admitted_cancelled_before_dispatch_and_busy_count_zero(tmp_path):
    class Forbidden:
        def generate(self, *_args):
            raise AssertionError("cancelled input reached provider")

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ContentFailure) as error:
        generate_admitted(Forbidden(), request(timeout=TIMEOUT), OperationFiles(tmp_path), cancelled)
    assert error.value.code == "CANCELLED" and error.value.logical_attempts == 0

    class Busy:
        def generate(self, *_args):
            raise ContentFailure("BUSY")

    with pytest.raises(ContentFailure) as error:
        generate_admitted(Busy(), request(timeout=TIMEOUT), OperationFiles(tmp_path), threading.Event())
    assert error.value.code == "BUSY" and error.value.logical_attempts == 0


@pytest.mark.parametrize("reported", [0, 1, 2])
def test_admitted_success_preserves_usage_and_does_not_double_count(tmp_path, reported):
    class Provider:
        def generate(self, content, _files, _cancel):
            assert content.policy.allow_repair is False
            return ContentResult(Summary(summary="Synthetic"), ReportedUsage(), "fixture", content.policy.model,
                                 0.25, reported)

    result = generate_admitted(Provider(), request(timeout=TIMEOUT), OperationFiles(tmp_path), threading.Event())
    assert result.logical_attempts == max(1, reported)
    assert result.internal_inference_count is None
    assert result.usage.input_tokens is None
    assert result.elapsed_seconds == 0.25


@pytest.mark.parametrize("repair", [True, False])
def test_repair_setting_does_not_remove_runtime_timeout_ceiling(repair):
    assert GenerationPolicy("fixture", timeout_seconds=180, allow_repair=repair).timeout_seconds == 180
    for seconds in [180.01, 0, float("inf"), float("nan")]:
        with pytest.raises(ValueError, match="generation limits"):
            GenerationPolicy("fixture", timeout_seconds=seconds, allow_repair=repair)


@pytest.mark.parametrize("case,code", [("missing_login", "AUTH_REQUIRED"), ("bad_help", "CLI_PROFILE_UNSAFE")])
@pytest.mark.parametrize("admitted", [True, False])
def test_real_adapter_probe_failure_has_one_admitted_attempt_without_generation(fake, case, code, admitted):
    cli, root, keep, configure, starts = fake
    configure(case)
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure) as error:
        if admitted:
            generate_admitted(provider, request(timeout=TIMEOUT), files, threading.Event())
        else:
            provider.generate(request(timeout=TIMEOUT), files, threading.Event())
    assert error.value.code == code
    assert error.value.logical_attempts == (1 if admitted else 0)
    assert error.value.usage.input_tokens is None
    assert starts() == 0
    assert list(root.iterdir()) == [keep]
