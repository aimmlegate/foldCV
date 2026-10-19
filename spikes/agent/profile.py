"""Per-process assistant controls over the existing native login profile."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile, ExperimentalProfileError
from resume_api.cli import distribution


TOKEN_ENV = "FOLDCV_AGENT_MCP_CAPABILITY"
TOOLS = ("get_resume_context", "check_resume", "read_public_page")
PACKAGE = BINARY.parents[3]
CODE_MODE_HOST = PACKAGE / "bin/codex-code-mode-host"
HOST_SHA256 = "2e3871dba48d4a782d6acd209684536c0f4e7761c6792ed76d061d6da31048f0"
PACKAGE_MANIFEST = PACKAGE / "codex-package.json"
MANIFEST_SHA256 = "95ea87bed0ff10cb2cbd9b0541b0e332b4c87f74efd961924029beb33bebb407"
APP_SERVER_PREFIX = ("app-server", "--strict-config", "--listen", "stdio://")


def check_host(package: Path | None = None) -> None:
    host = CODE_MODE_HOST if package is None else package / "bin/codex-code-mode-host"
    manifest = PACKAGE_MANIFEST if package is None else package / "codex-package.json"
    for path, digest in ((host, HOST_SHA256 if package is None else distribution.HOST_SHA256),
                         (manifest, MANIFEST_SHA256)):
        try:
            if any(part.is_symlink() for part in (path, *path.parents)) or not stat.S_ISREG(path.stat().st_mode):
                raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED")
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != digest:
                raise ExperimentalProfileError("AGENT_CODE_MODE_HOST_UNSUPPORTED")
        except OSError as error:
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
        check_host() if self.executable == BINARY else check_host(self.package_root)
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
               allow_web: bool = True) -> list[str]:
        values = [
            'features.code_mode=true',
            'features.code_mode_host=true',
            'features.code_mode_prewarm=true',
            'approvals_reviewer="user"',
            'web_search="live"' if allow_web else 'web_search="disabled"',
            'features.guardian_approval=false',
            'features.daemon_auto_start=false',
            'features.multi_agent=false',
            'features.multi_agent_v2=false',
            'model_auto_compact_token_limit=1000000',
            'model_reasoning_effort="medium"',
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
