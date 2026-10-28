"""One atomic Markdown Rules file, with immutable captured revisions."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .models.settings import Rules
from .storage import StorageFailure, atomic_write, data_root, locked_root, private_file


PRESET_HEADINGS = {"shorten": "## Preset: shorten", "clarify": "## Preset: clarify"}
MAX_RULE_BYTES = 32_768
HEADER = re.compile(r"<!-- foldcv-rules:v1 revision=([1-9][0-9]*) sha256=([a-f0-9]{64}) -->\n")
DEFAULT_RULES = Path(__file__).with_name("default_rules.md").read_text(encoding="utf-8")
FIRST_PRESET = re.compile(r"^## Preset: (?:shorten|clarify)$", re.M)
# SHA-256 of the editorial text that earlier defaults put before the presets (49b4c406, its NE01 form, 4cc6523e).
# Nothing reads it since V7; the template holds those rules (D111). Text a user wrote stays.
LEGACY_EDITORIAL = {
    "107deec7a56114463d04b764cdbbaee12b4d30baa5ffdf712e4c4fbd6a4c7cd0",
    "4bde44ff8097b80ada583980e59c73789b1242966c32e00a1565261e493550ca",
    "db07951b27142a644e15fdd9e7eb79d458ca9aa56c59da6ac8c96e05ee2eb566",
}


class RulesFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def without_legacy_editorial(markdown: str) -> str:
    match = FIRST_PRESET.search(markdown)
    if match is None or hashlib.sha256(markdown[:match.start()].encode()).hexdigest() not in LEGACY_EDITORIAL:
        return markdown
    return markdown[match.start():]


def normalize_markdown(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    try:
        size = len(text.encode("utf-8", "strict"))
    except UnicodeError:
        raise RulesFailure("RULES_INVALID_TEXT") from None
    if size > MAX_RULE_BYTES:
        raise RulesFailure("RULES_TOO_LARGE")
    if not text.strip() or any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise RulesFailure("RULES_INVALID_TEXT")
    return text


def presets(markdown: str) -> dict[str, str]:
    bodies: dict[str, list[str]] = {}
    active: str | None = None
    fence: str | None = None
    for line in markdown.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            if active is not None:
                bodies[active].append(line)
            continue
        if fence is None and line.startswith("## "):
            active = next((key for key, heading in PRESET_HEADINGS.items() if line == heading), None)
            if active is not None:
                if active in bodies:
                    raise RulesFailure("RULES_PRESETS_REQUIRED")
                bodies[active] = []
            continue
        if active is not None:
            bodies[active].append(line)
    result = {key: "\n".join(lines).strip() for key, lines in bodies.items()}
    if set(result) != set(PRESET_HEADINGS) or not all(result.values()):
        raise RulesFailure("RULES_PRESETS_REQUIRED")
    return result


def captured_rules(markdown: str, revision: int) -> Rules:
    text = normalize_markdown(markdown)
    presets(text)
    return Rules.model_validate({"markdown": text, "revision": revision,
                                "sha256": hashlib.sha256(text.encode()).hexdigest()})


class RulesStore:
    def __init__(self, root: Path | None = None):
        self.root = data_root(root)
        self.path = self.root / "rules.md"

    def _read(self) -> Rules:
        if not self.path.exists():
            result = captured_rules(DEFAULT_RULES, 1)
            self._write(result)
            return result
        private_file(self.path)
        if self.path.stat().st_size > MAX_RULE_BYTES + 200:
            raise RulesFailure("RULES_TOO_LARGE")
        content = self.path.read_text(encoding="utf-8")
        match = HEADER.match(content)
        if match is None:
            raise RulesFailure("RULES_LOAD_FAILED")
        result = captured_rules(content[match.end():], int(match.group(1)))
        if result.sha256 != match.group(2):
            raise RulesFailure("RULES_LOAD_FAILED")
        trimmed = without_legacy_editorial(result.markdown)
        if trimmed != result.markdown:
            result = captured_rules(trimmed, result.revision + 1)
            self._write(result)
        return result

    def _write(self, rules: Rules) -> None:
        header = f"<!-- foldcv-rules:v1 revision={rules.revision} sha256={rules.sha256} -->\n"
        atomic_write(self.path, (header + rules.markdown).encode("utf-8"))

    def load(self) -> Rules:
        try:
            with locked_root(self.root, ".rules.lock"):
                return self._read()
        except StorageFailure:
            raise RulesFailure("RULES_UNSAFE_STORAGE") from None
        except (OSError, UnicodeError):
            raise RulesFailure("RULES_LOAD_FAILED") from None

    def save(self, markdown: str, base_revision: int) -> Rules:
        text = normalize_markdown(markdown)
        presets(text)
        try:
            with locked_root(self.root, ".rules.lock"):
                current = self._read()
                if base_revision != current.revision:
                    raise RulesFailure("RULES_STALE")
                if text == current.markdown:
                    return current
                result = captured_rules(text, current.revision + 1)
                self._write(result)
                return result
        except StorageFailure:
            raise RulesFailure("RULES_UNSAFE_STORAGE") from None
        except (OSError, UnicodeError):
            raise RulesFailure("RULES_SAVE_FAILED") from None
