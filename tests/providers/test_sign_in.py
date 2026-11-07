"""The sign-in page address taken from a CLI's output, and the local sign-in log."""

import pytest

from resume_api.lifecycle import SpikeError
from resume_api.providers.sign_in import LOG_BYTES, SignInOutput, sign_in_url

PAGE = "https://claude.com/cai/oauth/authorize?code=true&client_id=c&state=one-time&code_challenge=one-time-too"


@pytest.mark.parametrize(("kind", "raw", "accepted"), [
    ("claude_cli", PAGE, True), ("claude_cli", "https://platform.claude.com/oauth/authorize?x=1", True),
    ("codex_cli", "https://auth.openai.com/oauth/authorize?x=1", True),
    ("codex_cli", PAGE, False), ("claude_cli", "http://claude.com/cai/oauth/authorize", False),
    ("claude_cli", "https://claude.com.example.org/oauth", False), ("claude_cli", "https://evil.test/?claude.com", False),
    ("claude_cli", "https://claude.com:8443/oauth", False), ("claude_cli", "https://user@claude.com/oauth", False),
    ("claude_cli", 'https://claude.com/"onclick', False), ("claude_cli", "https://claude.com/" + "a" * 4096, False),
    ("claude_cli", "https://claude.com:x/", False), ("other", PAGE, False),
])
def test_only_the_providers_own_https_page_is_offered(kind, raw, accepted):
    assert (sign_in_url(kind, raw) == raw) is accepted


def test_the_address_counts_only_once_it_is_printed_in_full():
    output = SignInOutput("claude_cli")
    output.feed("stdout", b"Opening browser to sign in\xe2\x80\xa6\nIf the browser didn't open, visit: https://evil.test/x\n"
                          b"visit: " + PAGE[:30].encode())
    assert output.url is None
    output.feed("stderr", PAGE[30:].encode() + b"\n")
    assert output.url is None
    output.feed("stdout", PAGE[30:].encode() + b"\nPaste code here if prompted > ")
    assert output.url == PAGE
    output.feed("stdout", b"\nhttps://platform.claude.com/other\n")
    assert output.url == PAGE


def test_the_log_records_the_outcome_without_one_time_values(tmp_path):
    log = tmp_path / "logs" / "sign-in.log"
    output = SignInOutput("claude_cli", log)
    with output.recording():
        output.feed("stdout", f"visit: {PAGE}\n".encode())
    output = SignInOutput("claude_cli", log)
    with pytest.raises(SpikeError), output.recording():
        output.feed("stderr", b"Login failed\n")
        raise SpikeError("DEADLINE_EXCEEDED")
    text = log.read_text()
    assert "claude_cli sign-in: OK" in text and "claude_cli sign-in: DEADLINE_EXCEEDED" in text
    assert "page address found: yes" in text and "page address found: no" in text and "--- stderr\nLogin failed" in text
    assert "one-time" not in text and "state=…" in text and "client_id=c" in text


def test_a_full_log_moves_aside_and_an_unwritable_one_is_skipped(tmp_path):
    log = tmp_path / "sign-in.log"
    log.write_bytes(b"x" * LOG_BYTES)
    SignInOutput("codex_cli", log).write("OK")
    assert (tmp_path / "sign-in.log.1").stat().st_size == LOG_BYTES and "codex_cli sign-in: OK" in log.read_text()
    blocked = tmp_path / "file"
    blocked.write_text("")
    SignInOutput("codex_cli", blocked / "sign-in.log").write("OK")
