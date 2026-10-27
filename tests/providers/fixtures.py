"""A fake Codex CLI in a hostile temporary path, and the small request it answers. No live provider is invoked."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from pydantic import BaseModel, ConfigDict, Field
import pytest

from resume_api.providers.content import ContentInput, GenerationPolicy


PROMPT = "Synthetic Alex; 'quotes' ☃ $() `inert` synthetic-secret"
SOURCE = Path(__file__).parent


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=400)


def install_fake_cli(directory: Path) -> Path:
    """Copy the fake CLI with this interpreter as its shebang; returns the executable."""
    cli = directory / "codex fixture"
    cli.write_text("#!" + sys.executable + "\n" + (SOURCE / "fake_cli.py").read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    shutil.copyfile(SOURCE / "fake_cli_success.jsonl", directory / "success.jsonl")
    return cli


@pytest.fixture
def fake(tmp_path: Path):
    directory = tmp_path / "fake CLI 'quoted' Юникод $(inert)"
    directory.mkdir()
    cli = install_fake_cli(directory)
    root = tmp_path / "operations with spaces ' ☃ $()"
    root.mkdir()
    keep = root / "unrelated.txt"
    keep.write_text("keep")

    def configure(case: str = "valid", **extra: object) -> None:
        (directory / "fixture.json").write_text(json.dumps({"case": case, "prompt": PROMPT, **extra}))

    def starts() -> int:
        audit = directory / "audit.jsonl"
        return sum(json.loads(line).get("generation", False) for line in audit.read_text().splitlines()) if audit.exists() else 0

    configure()
    return cli, root, keep, configure, starts


def request(*, timeout: float = 60, max_total_input_bytes: int = 16_384) -> ContentInput[Summary]:
    return ContentInput(PROMPT, Summary, GenerationPolicy("gpt-6-luna", timeout_seconds=timeout,
                                                        max_total_input_bytes=max_total_input_bytes))
