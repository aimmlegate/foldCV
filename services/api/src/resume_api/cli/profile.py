"""Pinned controls and explicit gaps; these are not a production provider profile."""

from dataclasses import dataclass
from pathlib import Path
import json
import re

from resume_api.cli.qualification import Compatibility, QualificationError, Status, Version


VERSION = "codex-cli 0.162.0-alpha.2"
FIXTURE_VERSION = "codex-cli 0.162.0-alpha.2-fixture"
GAPS = (
    "No verified deny-all control for every built-in tool.",
    "No verified global skill/instruction discovery isolation with native auth.",
    "No success/failure/cancellation canary audit of all CLI content writes.",
    "No verified absence of auxiliary inference inside this CLI version.",
)
REQUIRED_FLAGS = (
    "--ephemeral", "--ignore-user-config", "--ignore-rules", "--json",
    "--output-schema", "--skip-git-repo-check",
)
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "shell_snapshot", "view_image",
    "browser_use", "browser_use_external", "computer_use", "apps", "plugins",
    "remote_plugin", "hooks", "memories", "multi_agent", "multi_agent_v2",
    "image_generation", "artifact", "code_mode", "code_mode_host",
    "skill_search", "skill_mcp_dependency_install", "sleep_tool", "goals",
    "daemon_auto_start", "in_app_local_automation", "tool_suggest",
    "unbounded_connection_retries",
)


# Section 5 of the multi-provider plan: publisher and a version table instead of exact pins.
TEAM_ID = "2DC432GLL2"
IDENTIFIER = "codex"
HOST_IDENTIFIER = "codex-code-mode-host"
COMPATIBILITY = Compatibility(floor="0.162.0-alpha.2", last_tested="0.163.0-alpha.11.1")
# `features list` reports unified_exec on even with `--disable unified_exec` (0.163.0-alpha.11.1);
# the exec grammar aborts on any tool item instead.
REQUIRED_OFF = tuple(name for name in DISABLED_FEATURES if name != "unified_exec")
_FEATURE = re.compile(r"([a-z0-9_.]+)\s+\S.*?\s+(true|false)\s*")


def qualify(banner: str) -> Status:
    """Status of a `codex-cli <semver>` banner; below the floor or broken is unsupported."""
    if len(banner) > 80 or not banner.startswith("codex-cli "):
        raise QualificationError("CLI_UNSUPPORTED")
    status = COMPATIBILITY.status(Version.parse(banner.removeprefix("codex-cli ")))
    if status in {"unsupported", "broken"}:
        raise QualificationError("CLI_UNSUPPORTED")
    return status


def check_features(listing: str) -> None:
    """`codex features list` under the profile overrides must report every required feature off."""
    effective = {}
    for line in listing.splitlines():
        match = _FEATURE.fullmatch(line)
        if match:
            effective[match.group(1)] = match.group(2) == "true"
    if not effective or any(effective.get(name) for name in REQUIRED_OFF):
        raise QualificationError("CLI_PROFILE_UNSAFE")


@dataclass(frozen=True)
class Profile:
    version: str
    generation_verified: bool


REAL_PROFILE = Profile(VERSION, False)
# The fake advertises a different version and checks its own restrictions.
FIXTURE_PROFILE = Profile(FIXTURE_VERSION, True)


def overrides(directory: Path) -> list[str]:
    values = [
        'model_provider="openai"', 'forced_login_method="chatgpt"',
        'approval_policy="never"', 'web_search="disabled"',
        'history.persistence="none"', 'project_doc_max_bytes=0',
        'developer_instructions=""', 'mcp_servers={}',
        'analytics.enabled=false', 'otel.log_user_prompt=false',
        'shell_environment_policy.inherit="none"',
        f"log_dir={json.dumps(str(directory / 'logs'))}",
        f"sqlite_home={json.dumps(str(directory / 'state'))}",
    ]
    values += [f"features.{name}=false" for name in DISABLED_FEATURES]
    return [part for value in values for part in ("--config", value)]


def exec_arguments(directory: Path, model: str) -> list[str]:
    return [
        "exec", "--strict-config", "--ignore-user-config", "--ignore-rules",
        "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
        "--json", "--color", "never", "--model", model,
        "--output-schema", str(directory / "schema.json"),
        *overrides(directory), "-",
    ]
