"""GET and PUT /v1/settings/rules: session, origin and body guards, stale saves, and no model work."""

import httpx
import pytest

from resume_api.app import create_app
from packages.resume_core.project_limits import REWRITE_INSTRUCTION_CHARS
from packages.resume_core.rules import PRESET_HEADINGS, RulesStore, captured_rules, presets
from packages.resume_core.storage import locked_root

ORIGIN = "http://127.0.0.1:39329"
SECRET = "synthetic-rules-startup-secret-0123456789"


class ForbiddenProvider:
    def generate(self, *_args):
        raise AssertionError("a rule save must not call a model")

    def generate_queued(self, *_args):
        raise AssertionError("a rule save must not call a model")


@pytest.fixture
def app(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("synthetic")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                      data_root=tmp_path / "FoldCV", content_provider=ForbiddenProvider())


async def login(client):
    await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})


@pytest.mark.asyncio
async def test_rule_settings_roundtrip_requires_session_and_stale_save_is_safe(app, tmp_path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await client.get("/v1/settings/rules")).status_code == 401
        assert not (tmp_path / "FoldCV").exists()
        await login(client)
        initial = (await client.get("/v1/settings/rules")).json()
        assert set(initial["presets"]) == {"shorten", "clarify"}
        assert "Сократи" in initial["presets"]["shorten"]
        changed = initial["markdown"].replace("лишние слова", "вводные слова")
        saved = await client.put("/v1/settings/rules", headers={"Origin": ORIGIN},
                                 json={"markdown": changed, "baseRevision": initial["revision"]})
        assert saved.status_code == 200 and saved.json()["revision"] == 2
        assert saved.headers["cache-control"] == "no-store"
        stale = await client.put("/v1/settings/rules", headers={"Origin": ORIGIN},
                                 json={"markdown": changed + "\nOutdated", "baseRevision": 1})
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "RULES_STALE"
        invalid = await client.put("/v1/settings/rules", headers={"Origin": ORIGIN},
                                   json={"markdown": "Private marker without presets", "baseRevision": 2})
        assert invalid.status_code == 422
        assert invalid.json()["requiredHeadings"] == ["## Preset: shorten", "## Preset: clarify"]
        assert "Private marker" not in invalid.text
        assert RulesStore(tmp_path / "FoldCV").load().revision == 2


@pytest.mark.asyncio
async def test_rules_keep_host_origin_body_and_duplicate_json_guards(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await login(client)
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        assert (await client.put("/v1/settings/rules", json={})).status_code == 403
        assert (await client.get("/v1/settings/rules", headers={"Host": "localhost:39329"})).status_code == 403
        assert (await client.put("/v1/settings/rules", headers=headers, content=b'{"markdown":"one","markdown":"two","baseRevision":1}')).status_code == 422
        assert (await client.put("/v1/settings/rules", headers={"Origin": ORIGIN}, content=b"text")).status_code == 415
        assert (await client.put("/v1/settings/rules", headers=headers, content=b"x" * 1_048_577)).status_code == 413
        bad = await client.put("/v1/settings/rules", headers=headers, json={"markdown": "marker", "baseRevision": 1, "command": "private marker"})
        assert bad.status_code == 422 and "private marker" not in bad.text
        assert (await client.get("/v1/settings/rules?marker=private")).status_code == 403


@pytest.mark.asyncio
async def test_many_rule_saves_need_no_model_and_hit_no_operation_cap(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await login(client)
        current = (await client.get("/v1/settings/rules")).json()
        for index in range(22):
            saved = await client.put("/v1/settings/rules", headers={"Origin": ORIGIN},
                                     json={"markdown": current["markdown"] + f"\nPolicy {index}",
                                           "baseRevision": current["revision"]})
            assert saved.status_code == 200
            current = saved.json()
        assert current["revision"] == 23


def with_shorten(markdown, length):
    """Rules whose `shorten` preset has this many characters."""
    shorten, clarify = PRESET_HEADINGS["shorten"], PRESET_HEADINGS["clarify"]
    return markdown[:markdown.index(shorten)] + shorten + "\n" + "я" * length + "\n\n" + clarify + "\nЯсно\n"


@pytest.mark.asyncio
async def test_a_preset_that_cannot_be_sent_as_an_instruction_is_refused_at_save(app, tmp_path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await login(client)
        initial = (await client.get("/v1/settings/rules")).json()
        too_long = await client.put("/v1/settings/rules", headers={"Origin": ORIGIN}, json={
            "markdown": with_shorten(initial["markdown"], REWRITE_INSTRUCTION_CHARS + 1), "baseRevision": initial["revision"]})
        assert too_long.status_code == 422 and too_long.json()["error"]["code"] == "RULES_PRESET_TOO_LONG"
        fits = await client.put("/v1/settings/rules", headers={"Origin": ORIGIN}, json={
            "markdown": with_shorten(initial["markdown"], REWRITE_INSTRUCTION_CHARS), "baseRevision": initial["revision"]})
        assert fits.status_code == 200 and len(fits.json()["presets"]["shorten"]) == REWRITE_INSTRUCTION_CHARS


def test_a_longer_preset_already_saved_stays_readable(tmp_path):
    store = RulesStore(tmp_path / "FoldCV")
    current = store.load()
    long = captured_rules(with_shorten(current.markdown, REWRITE_INSTRUCTION_CHARS + 1), current.revision + 1)
    with locked_root(store.root, ".rules.lock"):
        store._write(long)
    assert len(presets(store.load().markdown)["shorten"]) == REWRITE_INSTRUCTION_CHARS + 1
