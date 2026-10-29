"""Opt-in, pinned macOS CLI environment for the personal experiment."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from resume_api.cli import profile as codex
from resume_api.cli.profile import overrides
from resume_api.cli.qualification import QualificationError, require_publisher
from . import distribution


# Only the runtime FoldCV downloaded keeps hash pins; a user-installed CLI is qualified by its
# publisher signature and the version table (multi-provider plan section 5).
BINARY = Path("/Users/fostral/.codex/plugins/.plugin-appserver/codex-cli/CodexCLI.app/Contents/MacOS/codex")
SYSTEM_SKILLS = ("imagegen", "openai-docs", "skill-creator", "skill-installer")
MARKER = ".foldcv-cli-experiment-v1"
SYSTEM_CA = Path("/private/etc/ssl/cert.pem")
_system_certificates = False


class ExperimentalProfileError(Exception):
    pass


def use_system_certificates() -> None:
    """Point every CLI launch of this process at the system PEM bundle; TLS checks stay on.

    The macOS app needs it: native trust discovery failed the CLI token exchange on a macOS 14 Mac (2026-10-20).
    """
    global _system_certificates
    _system_certificates = True


def system_certificates() -> str:
    try:
        info = SYSTEM_CA.lstat()
        if (any(path.is_symlink() for path in SYSTEM_CA.parents) or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0 or info.st_mode & 0o022 or not 0 < info.st_size <= 4 * 1024 * 1024):
            raise ExperimentalProfileError("CLI_CA_UNAVAILABLE")
    except OSError:
        raise ExperimentalProfileError("CLI_CA_UNAVAILABLE") from None
    return str(SYSTEM_CA)


def _literal(path: Path) -> str:
    return json.dumps(str(path))


def _safe_directory(path: Path, *, create: bool) -> Path:
    absolute = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")
    if create:
        absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (not absolute.is_dir() or stat.S_IMODE(absolute.stat().st_mode) != 0o700
            or absolute.stat().st_uid != os.getuid()):
        raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")
    return absolute.resolve(strict=True)


@dataclass(frozen=True)
class ExperimentalCliProfile:
    """Native credentials live only in this mode's CLI-owned home."""

    root: Path
    executable: Path = BINARY

    @property
    def managed(self) -> bool:
        return self.executable == distribution.managed_executable(self.root.parent / "cli-runtime")

    @property
    def package_root(self) -> Path:
        return self.executable.parents[3] if self.executable == BINARY else self.executable.parent.parent

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def codex_home(self) -> Path:
        return self.root / "codex"

    @property
    def workdir(self) -> Path:
        """One empty working directory for every CLI call: the CLI names its cwd in the model's context, and a
        per-call directory made every prompt prefix unique (D116: no prompt cache hits across calls)."""
        return self.root / "cwd"

    def prepare(self) -> None:
        self.prepare_directories()
        self.check_binary()

    def prepare_directories(self) -> None:
        if self.root.exists() and not (self.root / MARKER).is_file():
            raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")
        native_home = Path.home().resolve()
        native_codex = Path(os.environ.get("CODEX_HOME", native_home / ".codex")).resolve()
        if self.root.resolve() in {native_home, native_codex} or self.root.resolve().is_relative_to(native_codex):
            raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")
        _safe_directory(self.root, create=True)
        marker = self.root / MARKER
        if not marker.exists():
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write("foldcv-cli-experiment-v1\n")
        if (marker.is_symlink() or marker.read_text(encoding="ascii") != "foldcv-cli-experiment-v1\n"
                or marker.stat().st_uid != os.getuid() or stat.S_IMODE(marker.stat().st_mode) != 0o600):
            raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")
        _safe_directory(self.home, create=True)
        _safe_directory(self.codex_home, create=True)
        _safe_directory(self.workdir, create=True)
        sandbox = Path("/usr/bin/sandbox-exec")
        if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
            raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")

    def check_binary(self) -> None:
        if (not self.executable.is_file() or not os.access(self.executable, os.X_OK)
                or any(part.is_symlink() for part in (self.executable, *self.executable.parents))):
            raise ExperimentalProfileError("CLI_UNSUPPORTED")
        if not self.managed:
            try:
                require_publisher(self.executable, codex.TEAM_ID, codex.IDENTIFIER)
            except QualificationError:
                raise ExperimentalProfileError("CLI_UNSUPPORTED") from None
            return
        with self.executable.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != distribution.CLI_SHA256:
            raise ExperimentalProfileError("CLI_UNSUPPORTED")

    def config(self, operation: Path) -> list[str]:
        skills = [{"path": str(self.codex_home / "skills" / ".system" / name / "SKILL.md"),
                   "enabled": False} for name in SYSTEM_SKILLS]
        entries = "[" + ",".join("{path=" + json.dumps(skill["path"]) + ",enabled=false}"
                                  for skill in skills) + "]"
        return [*overrides(operation), "--config", "features.skip_host_skill_discovery=true",
                "--config", "skills.config=" + entries]

    def _policy(self, operation: Path, args: tuple[str, ...]) -> str:
        app = self.executable.parents[2] if self.executable == BINARY else self.package_root
        paths = (self.root, operation)
        read = " ".join("(subpath " + _literal(path) + ")" for path in (*paths, app))
        write = " ".join("(subpath " + _literal(path) + ")" for path in paths)
        operations = [
            "(version 1)", "(allow default)",
            '(deny file-read-data (subpath "/Users") (subpath "/Volumes") '
            '(subpath "/Network") (subpath "/private/tmp") '
            '(subpath "/private/var") (subpath "/tmp") (subpath "/var"))',
            "(allow file-read-data " + read + ")",
            "(deny file-write*)",
            "(allow file-write* " + write + ' (literal "/dev/null"))',
            "(deny process-exec)",
            "(allow process-exec (literal " + _literal(self.executable) + "))",
        ]
        if args and args[0] == "login" and args != ("login", "status"):
            operations.append('(allow process-exec (literal "/usr/bin/open"))')
        return "\n".join(operations)

    def exec_arguments(self, operation: Path, model: str) -> tuple[str, ...]:
        return (
            "exec", "--strict-config", "--ignore-user-config", "--ignore-rules",
            "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--json", "--color", "never", "--model", model,
            "--output-schema", str(operation / "schema.json"),
            *self.config(operation), "-",
        )

    def launch(self, executable: Path, args: tuple[str, ...], operation: Path
               ) -> tuple[Path, tuple[str, ...], dict[str, str]]:
        self.prepare()
        if executable != self.executable:
            raise ExperimentalProfileError("CLI_PROFILE_UNSAFE")
        owned = _safe_directory(operation, create=False)
        for name in ("tmp", "cache", "data", "state", "logs"):
            _safe_directory(owned / name, create=False)
        env = {"PATH": os.defpath, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
               "HOME": str(self.home), "CODEX_HOME": str(self.codex_home),
               "TMPDIR": str(owned / "tmp"), "XDG_CACHE_HOME": str(owned / "cache"),
               "XDG_DATA_HOME": str(owned / "data"), "XDG_STATE_HOME": str(owned / "state")}
        if _system_certificates:
            env["CODEX_CA_CERTIFICATE"] = system_certificates()
        command = ("-p", self._policy(owned, args), str(executable), *args)
        return Path("/usr/bin/sandbox-exec"), command, env


def installed_profile(root: Path, *, managed_only: bool = False) -> ExperimentalCliProfile:
    """The macOS app passes managed_only: it uses only the runtime it installs, on every Mac the same way."""
    import shutil
    from resume_api.agent.host_profile import check_host

    managed = distribution.managed_executable(root.parent / "cli-runtime")
    if managed_only:
        return ExperimentalCliProfile(root, managed)
    candidates = [managed, BINARY]
    detected = shutil.which("codex")
    if detected is not None:
        candidates.append(Path(detected).resolve())
    for executable in candidates:
        profile = ExperimentalCliProfile(root, executable)
        try:
            profile.check_binary()
            check_host() if executable == BINARY else check_host(profile.package_root, managed=profile.managed)
            return profile
        except (OSError, ExperimentalProfileError):
            continue
    return ExperimentalCliProfile(root, managed)
