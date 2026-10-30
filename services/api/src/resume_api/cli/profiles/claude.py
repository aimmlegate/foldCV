"""FoldCV-owned Claude Code profile: config directory, environment, sandbox and argv (MP00).

On Windows a Job Object takes sandbox-exec's place: no other programs, but no file or network rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil

from packages.resume_core import host
from resume_api.cli.qualification import Compatibility


KIND = "claude_cli"
TEAM_ID = "Q6L2SF6YDW"
IDENTIFIER = "com.anthropic.claude-code"
COMPATIBILITY = Compatibility(floor="2.1.302", last_tested="2.1.308")
# Flags that `--help` lists; `--max-turns` is parsed and documented but hidden from `--help` (2.1.308).
REQUIRED_FLAGS = (
    "--print", "--output-format", "--verbose", "--json-schema", "--model", "--effort", "--restricted",
    "--tools", "--strict-mcp-config", "--mcp-config", "--disable-slash-commands", "--settings",
    "--no-session-persistence", "--permission-mode", "--permission-prompts", "--system-prompt",
    "--allowedTools", "--include-partial-messages",
)
HIDDEN_FLAGS = ("--max-turns",)
ACCEPTED_AUTH = "claude.ai"
STRUCTURED_TOOLS = ("StructuredOutput",)
STRUCTURED_MAX_TURNS = 4
SYSTEM_PROMPT = ("Follow the user's instructions exactly. Return the result only through the structured "
                 "output; do not add commentary.")
# Built-in plugins seen in 2.1.308; a new one fails the system/init check instead of loading silently.
SETTINGS = {"disableAllHooks": True,
            "enabledPlugins": {"cc-plugin-agents-md@builtin": False, "cc-plugin-plugin-authoring@builtin": False}}
STRIPPED = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN")
SWITCHES = {
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1", "CLAUDE_CODE_AUTO_CONNECT_IDE": "false",
    "CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1", "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1",
}
# Kept across operations; everything else in the config directory is wiped after each one.
KEEP = frozenset({".claude.json", ".credentials.json"})
MARKER = ".foldcv-claude-profile-v1"
# The native installer links ~/.local/bin/claude; Homebrew links its own bin. The binary is still qualified later.
INSTALL_LINKS = (Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude"))


def installed_executable() -> Path | None:
    detected = shutil.which("claude")
    for candidate in ((Path(detected),) if detected else ()) + INSTALL_LINKS:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.absolute()
    return None


class ClaudeProfileError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _literal(path: Path | str) -> str:
    return json.dumps(str(path))


def _private_directory(path: Path, *, create: bool) -> Path:
    absolute = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
    if create:
        absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = absolute.stat()
    if not absolute.is_dir() or not host.private_mode(info, 0o700) or not host.owned(info):
        raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
    return absolute.resolve(strict=True)


@dataclass(frozen=True)
class ClaudeCliProfile:
    """The sign-in lives in the macOS keychain entry of this config directory, not the user's one."""

    root: Path
    executable: Path
    home: Path = Path.home()

    @property
    def config_dir(self) -> Path:
        return self.root / "claude"

    @property
    def windows_home(self) -> Path:
        """Home and app data of the CLI on Windows, so it does not read or write the user's own."""
        return self.root / "home"

    def prepare(self) -> None:
        if self.root.exists() and not (self.root / MARKER).is_file():
            raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
        native = {self.home.resolve() / ".claude", self.home.resolve()}
        configured = os.environ.get("CLAUDE_CONFIG_DIR")
        if configured:
            native.add(Path(configured).resolve())
        if Path(os.path.abspath(self.root)) in native or any(
                Path(os.path.abspath(self.config_dir)) == item for item in native):
            raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
        _private_directory(self.root, create=True)
        marker = self.root / MARKER
        if not marker.exists():
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | host.O_NOFOLLOW | host.O_BINARY, 0o600)
            with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
                stream.write("foldcv-claude-profile-v1\n")
        if (marker.is_symlink() or marker.read_text(encoding="ascii") != "foldcv-claude-profile-v1\n"
                or not host.private_mode(marker.stat(), 0o600)):
            raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
        _private_directory(self.config_dir, create=True)
        if host.WINDOWS:
            _private_directory(self.windows_home, create=True)
        elif not Path("/usr/bin/sandbox-exec").is_file():
            raise ClaudeProfileError("CLI_PROFILE_UNSAFE")

    def environment(self, operation: Path, *, temp: Path | None = None) -> dict[str, str]:
        if host.WINDOWS:
            return {**host.windows_environment(temp or operation / "tmp", self.windows_home),
                    "CLAUDE_CODE_TMPDIR": str(operation / "tmp"), "CLAUDE_CONFIG_DIR": str(self.config_dir),
                    **SWITCHES}
        user = os.environ.get("USER") or os.environ.get("LOGNAME")
        if not user:
            raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
        # USER selects the keychain account; without it the CLI reports "not logged in".
        return {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "USER": user, "LOGNAME": user,
                "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "TMPDIR": str(operation / "tmp"),
                "CLAUDE_CODE_TMPDIR": str(operation / "tmp"), "CLAUDE_CONFIG_DIR": str(self.config_dir),
                **SWITCHES}

    def policy(self, operation: Path, args: tuple[str, ...], *, network: bool | str = True) -> str:
        paths = (self.root.resolve(), operation.resolve())
        binary = Path(os.path.realpath(self.executable))
        # The CLI keeps its sign-in in the login keychain and rewrites it on token refresh;
        # `security` sees a denied keychain file as a missing one.
        keychains = "(subpath " + _literal(self.home.resolve() / "Library" / "Keychains") + ")"
        read = " ".join("(subpath " + _literal(path) + ")" for path in paths) + " " + keychains
        write = read
        rules = ["(version 1)", "(allow default)"]
        if network is not True:
            rules.append("(deny network*)")
            if network == "loopback":
                # Dispatch-free assistant gates: FoldCV's MCP listener is reachable, the model API is not.
                rules.append('(allow network-outbound (remote ip "localhost:*"))')
        rules += [
            '(deny file-read-data (subpath "/Users") (subpath "/Volumes") (subpath "/Network") '
            '(subpath "/private/tmp") (subpath "/private/var") (subpath "/tmp") (subpath "/var"))',
            # Without the time zone database the runtime spins at startup.
            '(allow file-read-data (subpath "/private/var/db/timezone") (subpath "/private/var/db/mds"))',
            "(allow file-read-data " + read + " (literal " + _literal(binary) + "))",
            "(deny file-write*)",
            "(allow file-write* " + write + ' (literal "/dev/null"))',
            "(deny process-exec)",
            "(allow process-exec (literal " + _literal(binary) + ') (literal "/usr/bin/security"))',
        ]
        if args[:2] == ("auth", "login"):
            rules.append('(allow process-exec (literal "/usr/bin/open"))')
        return "\n".join(rules)

    def structured_arguments(self, schema: str | None, model: str, effort: str | None, *,
                             max_turns: int = STRUCTURED_MAX_TURNS) -> tuple[str, ...]:
        return structured_arguments(schema, model, effort, max_turns=max_turns)

    def launch(self, executable: Path, args: tuple[str, ...], operation: Path, *, network: bool | str = True
               ) -> tuple[Path, tuple[str, ...], dict[str, str]]:
        self.prepare()
        if executable != self.executable:
            raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
        owned = _private_directory(operation, create=False)
        _private_directory(owned / "tmp", create=False)
        if host.WINDOWS:
            if network is not True:
                # A Job Object cannot take the network away; only the macOS sandbox runs these checks.
                raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
            if args[:2] != ("auth", "login"):
                return host.Confined(executable), args, self.environment(owned)
            # A browser the sign-in starts inherits the folder and temp folder, so neither may be the operation's.
            temp = self.windows_home / "AppData" / "Local" / "Temp"
            temp.mkdir(parents=True, exist_ok=True)
            return (host.Confined(executable, breakaway=True, cwd=self.root), args,
                    self.environment(owned, temp=temp))
        command = ("-p", self.policy(owned, args, network=network), os.path.realpath(executable), *args)
        return Path("/usr/bin/sandbox-exec"), command, self.environment(owned)

    def wipe(self) -> list[str]:
        """Remove sessions, caches, logs and backups; keep only the config file and credentials."""
        removed = []
        for entry in sorted(self.config_dir.iterdir()):
            if entry.name in KEEP and entry.is_file() and not entry.is_symlink():
                continue
            if entry.is_dir() and not entry.is_symlink():
                host.remove_tree(entry)
            else:
                entry.unlink()
            removed.append(entry.name)
        return removed


def structured_arguments(schema: str | None, model: str, effort: str | None, *,
                         max_turns: int = STRUCTURED_MAX_TURNS) -> tuple[str, ...]:
    """One argv for structured generation; without a schema the final text is the answer."""
    return (
        "-p", "--output-format", "stream-json", "--verbose",
        *(("--json-schema", schema) if schema is not None else ()),
        "--model", model, *(("--effort", effort) if effort else ()),
        "--restricted", "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
        "--settings", json.dumps(SETTINGS, separators=(",", ":")), "--no-session-persistence",
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--max-turns", str(max_turns), "--system-prompt", SYSTEM_PROMPT,
    )


def agent_arguments(mcp_config: Path, model: str, effort: str | None, tools: tuple[str, ...], system_prompt: str, *,
                    max_turns: int) -> tuple[str, ...]:
    """One assistant run (plan 8.1): only the FoldCV MCP tools, the bearer token expanded from the environment."""
    return (
        "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        "--model", model, *(("--effort", effort) if effort else ()),
        "--restricted", "--tools", "", "--strict-mcp-config", "--mcp-config", str(mcp_config),
        "--allowedTools", ",".join(tools), "--disable-slash-commands",
        "--settings", json.dumps(SETTINGS, separators=(",", ":")), "--no-session-persistence",
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--max-turns", str(max_turns), "--system-prompt", system_prompt,
    )


def check_init(event: dict, *, model: str, version: str, tools: tuple[str, ...],
               mcp_servers: tuple[dict, ...] = ()) -> None:
    """The CLI's own report of the session must match the profile before any output is trusted."""
    expected = {"tools": sorted(tools), "mcp_servers": list(mcp_servers), "slash_commands": [],
                "skills": [], "plugins": [], "permissionMode": "dontAsk", "model": model,
                "apiKeySource": "none", "claude_code_version": version}
    actual = {key: sorted(event.get(key) or []) if key == "tools" else event.get(key) for key in expected}
    # 2.1.308 adds `"source": "dynamic"` to each server; the name and the status are what is checked.
    servers = event.get("mcp_servers")
    if isinstance(servers, list):
        actual["mcp_servers"] = [{"name": item.get("name"), "status": item.get("status")} if isinstance(item, dict)
                                 else item for item in servers]
    if event.get("type") != "system" or event.get("subtype") != "init":
        raise ClaudeProfileError("INVALID_RESULT")
    if actual != expected:
        raise ClaudeProfileError("CLI_PROFILE_UNSAFE")
