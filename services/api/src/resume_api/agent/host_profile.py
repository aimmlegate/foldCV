"""Per-process assistant controls over the existing native login profile."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile, ExperimentalProfileError
from resume_api.cli import distribution, profile as codex
from resume_api.cli.qualification import QualificationError, require_publisher


TOKEN_ENV = "FOLDCV_AGENT_MCP_CAPABILITY"
TOOLS = ("get_resume_context", "check_resume", "read_public_page")
PACKAGE = BINARY.parents[3]
CODE_MODE_HOST = PACKAGE / "bin/codex-code-mode-host"
PACKAGE_MANIFEST = PACKAGE / "codex-package.json"
APP_SERVER_PREFIX = ("app-server", "--strict-config", "--listen", "stdio://")


def check_host(package: Path | None = None, *, managed: bool = False) -> None:
    """The managed runtime keeps its release pins; a user-installed package needs the publisher's
    signed host and a manifest that names a qualifying version."""
    host = CODE_MODE_HOST if package is None else package / "bin/codex-code-mode-host"
    manifest = PACKAGE_MANIFEST if package is None else package / "codex-package.json"
    try:
        for path in (host, manifest):
            if any(part.is_symlink() for part in (path, *path.parents)) or not stat.S_ISREG(path.stat().st_mode):
                raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED")
        if managed:
            for path, digest in ((host, distribution.HOST_SHA256), (manifest, distribution.MANIFEST_SHA256)):
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED")
        else:
            require_publisher(host, codex.TEAM_ID, codex.HOST_IDENTIFIER)
            raw = manifest.read_bytes()
            value = json.loads(raw) if len(raw) <= 4096 else None
            if not isinstance(value, dict) or value.get("variant") != "codex" or not isinstance(value.get("version"), str):
                raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED")
            codex.qualify("codex-cli " + value["version"])
    except (OSError, ValueError, QualificationError) as error:
        raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED") from error
    if not os.access(host, os.X_OK):
        raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED")


class AgentProofProfile(ExperimentalCliProfile):
    @property
    def host_path(self) -> Path:
        return CODE_MODE_HOST if self.executable == BINARY else self.package_root / "bin/codex-code-mode-host"

    @property
    def manifest_path(self) -> Path:
        return PACKAGE_MANIFEST if self.executable == BINARY else self.package_root / "codex-package.json"

    def launch(self, executable: Path, args: tuple[str, ...], operation: Path
               ) -> tuple[Path, tuple[str, ...], dict[str, str]]:
        if (args[:4] != APP_SERVER_PREFIX or (len(args) - 4) % 2
                or any(arg != "--config" for arg in args[4::2])):
            raise ExperimentalProfileError("AGENT_RUNTIME_ONLY")
        check_host() if self.executable == BINARY else check_host(self.package_root, managed=self.managed)
        return super().launch(executable, args, operation)

    def _policy(self, operation: Path, args: tuple[str, ...]) -> str:
        policy = super()._policy(operation, args)
        if args[:4] != APP_SERVER_PREFIX:
            return policy
        # D086 permits only the pinned companion, never its surrounding directory.
        return policy + "\n" + "\n".join((
            '(allow file-read-data (literal ' + json.dumps(str(self.host_path))
            + ') (literal ' + json.dumps(str(self.manifest_path)) + '))',
            '(allow process-exec (literal ' + json.dumps(str(self.host_path)) + '))',
        ))

    def config(self, operation: Path, *, url: str | None = None,
               allow_web: bool = True, effort: str = "medium") -> list[str]:
        values = [
            'features.code_mode=true',
            'features.code_mode_host=true',
            'features.code_mode_prewarm=true',
            'approvals_reviewer="user"',
            # Decision 12: web access is the FoldCV read_public_page tool on every provider, never native search.
            'web_search="disabled"',
            'features.guardian_approval=false',
            'features.daemon_auto_start=false',
            'features.multi_agent=false',
            'features.multi_agent_v2=false',
            'model_auto_compact_token_limit=1000000',
            'model_reasoning_effort=' + json.dumps(effort),
            'model_reasoning_summary="none"',
        ]
        if url is not None:
            tools = TOOLS if allow_web else TOOLS[:2]
            values.append('mcp_servers={foldcv={url=' + json.dumps(url)
                          + ',bearer_token_env_var="' + TOKEN_ENV
                          + '",required=true,enabled=true,enabled_tools='
                          + json.dumps(tools) + ',default_tools_approval_mode="approve"'
                          + ',startup_timeout_sec=10,tool_timeout_sec=20}}')
        return [*super().config(operation),
                *(part for value in values for part in ("--config", value))]
