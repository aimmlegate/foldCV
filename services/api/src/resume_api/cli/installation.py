"""Explicit, cancellable installation of the newest official release into an app-owned directory (D146).

An install or update looks up the newest release first, checks the download against its publisher's record, writes
FoldCV's record next to the files and, when the slot gives a capability check, runs the new CLI through it before the
older release goes. A release that fails that check is not offered again in this run."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import tarfile
import threading
import time
import uuid

from packages.resume_core import host
from ..providers.claude import distribution as claude_distribution
from ..providers.codex import distribution as release
from .process_runner import ProcessExit, ProcessRunner
from .qualification import QualificationError, require_publisher
from .releases import RECORD, VERSION, Record, Release, ReleaseFailure, newer
from ..lifecycle import SpikeError

MARKER = ".foldcv-cli-runtime-v1"
# Codex 0.166.0 unpacks to 427 MB on macOS and 587 MB on Windows; the bound only stops a runaway archive.
MAX_UNPACKED = 2_000_000_000
MAX_MEMBERS = 1000
INSTALLING = frozenset({"downloading", "verifying", "extracting"})
# A found release counts as the newest for this long; Settings looks again when it opens after that.
FRESH_SECONDS = 6 * 3600
CHECK_SECONDS = 45


class InstallationFailure(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def digest(path, check=lambda: None):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check()
            value.update(chunk)
    return value.hexdigest()


def private_directory(path, *, create=False):
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise InstallationFailure("unsafe_directory")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or not host.owned(info) or not host.private_mode(info, 0o700):
        raise InstallationFailure("unsafe_directory")


def curl() -> Path:
    """Windows 10 and later ship curl.exe in System32."""
    if host.WINDOWS:
        return Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "curl.exe"
    return Path("/usr/bin/curl")


class CliInstallation:
    """The Codex package: the release archive with the CLI, its code-mode host and the package manifest.

    `qualify(files, executable, version, cancel)` checks what a new release can do before it replaces the old one; it
    raises InstallationFailure("incompatible_release") when the profile cannot use it."""

    download_name = "codex.tar.gz"
    seconds = 300

    def __init__(self, root, *, qualify=None):
        self.root = Path(os.path.abspath(root))
        self.qualify = qualify
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.checking = threading.Lock()
        self.found: Release | None = None
        self.found_at: float | None = None
        self.refused: set[str] = set()
        self.value = {"state": "idle", "downloadedBytes": 0, "totalBytes": 0, "error": None,
                      "available": (platform.system(), platform.machine()) in {("Darwin", "arm64"),
                                                                                ("Windows", "AMD64")}}

    @property
    def runtime(self):
        return release.runtime(self.root)

    def lookup(self, fetch):
        return release.latest(fetch)

    @property
    def executable(self):
        return self.runtime.executable()

    def installed(self):
        found = self.runtime.current()
        return found[0] if found else None

    def snapshot(self):
        with self.lock:
            value = dict(self.value)
            latest = self.found.version if self.found else None
        installed = self.installed()
        value.update(installed=installed, latest=latest,
                     update=value["state"] not in INSTALLING and latest not in self.refused and newer(latest, installed))
        return value

    def update(self, **values):
        with self.lock:
            self.value.update(values)

    @contextmanager
    def owned(self):
        if self.root.exists() and not (self.root / MARKER).exists():
            raise InstallationFailure("unsafe_directory")
        private_directory(self.root, create=True)
        marker = self.root / MARKER
        if not marker.exists():
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | host.O_NOFOLLOW | host.O_BINARY, 0o600)
            with os.fdopen(descriptor, "w", newline="\n") as stream:
                stream.write("foldcv-cli-runtime-v1\n")
        if (marker.is_symlink() or not host.owned(marker.stat())
                or marker.stat().st_size != 22 or marker.read_text() != "foldcv-cli-runtime-v1\n"):
            raise InstallationFailure("unsafe_directory")
        descriptor = os.open(self.root / ".install.lock", os.O_RDWR | os.O_CREAT | host.O_NOFOLLOW | host.O_BINARY,
                             0o600)
        try:
            if not host.owned(os.fstat(descriptor)) or os.fstat(descriptor).st_nlink != 1:
                raise InstallationFailure("unsafe_directory")
            try:
                host.lock(descriptor, blocking=False)
            except BlockingIOError:
                raise InstallationFailure("busy") from None
            yield
        finally:
            os.close(descriptor)

    def check_cancel(self):
        if self.cancel.is_set():
            raise InstallationFailure("cancelled")

    def fetch(self, files, url, limit, cancel, deadline):
        """One small HTTPS read: a version, a manifest, a signature or a release listing."""
        headers = (("--header", "Accept: application/vnd.github+json", "--header", "X-GitHub-Api-Version: 2022-11-28")
                   if url.startswith("https://api.github.com/") else ())
        try:
            stdout, _ = ProcessRunner(curl()).run(files, (
                "-q", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                "--proto-redir", "=https", "--connect-timeout", "15", "--max-time", "30",
                "--max-filesize", str(limit), *headers, url,
            ), cancel=cancel, deadline=deadline, max_output=limit + 16384, max_stdout=limit)
        except ProcessExit:
            raise ReleaseFailure("download_failed") from None
        except SpikeError as error:
            if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                raise
            raise ReleaseFailure("cancelled" if error.code == "CANCELLED" else "download_failed") from None
        return stdout

    def resolve(self, files, cancel, deadline):
        found = self.lookup(lambda url, limit: self.fetch(files, url, limit, cancel, deadline))
        with self.lock:
            self.found, self.found_at = found, time.monotonic()
        return found

    def check(self, files, cancel):
        """Look for a newer release; a failed look keeps the last answer, and one is enough for FRESH_SECONDS."""
        with self.lock:
            if self.found_at is not None and time.monotonic() - self.found_at < FRESH_SECONDS:
                return
        if not self.checking.acquire(blocking=False):
            return
        try:
            self.resolve(files, cancel, time.monotonic() + CHECK_SECONDS)
        except ReleaseFailure:
            pass
        finally:
            self.checking.release()

    def download(self, files, archive, target):
        deadline = time.monotonic() + self.seconds

        def progress():
            self.check_cancel()
            size = archive.stat().st_size if archive.exists() else 0
            if size > target.size:
                raise InstallationFailure("download_failed")
            self.update(downloadedBytes=size)

        try:
            ProcessRunner(curl()).run(files, (
                "-q", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                "--proto-redir", "=https", "--connect-timeout", "15", "--max-time", str(self.seconds),
                "--max-filesize", str(target.size), "--output", str(archive), target.url,
            ), cancel=self.cancel, deadline=deadline, poll_input=progress, max_output=16384)
        except ProcessExit:
            raise InstallationFailure("download_failed") from None

    def unpack(self, archive, destination):
        total = 0
        names = set()
        with tarfile.open(archive, "r:gz") as source:
            for member in source:
                self.check_cancel()
                name = PurePosixPath(member.name)
                if (name.is_absolute() or ".." in name.parts or not name.parts or "\\" in member.name
                        or not (member.isfile() or member.isdir()) or name in names or len(names) >= MAX_MEMBERS
                        or name.parts[0] == RECORD):
                    raise InstallationFailure("invalid_package")
                names.add(name)
                total += member.size
                if total > MAX_UNPACKED:
                    raise InstallationFailure("invalid_package")
                target = destination.joinpath(*name.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                stream = source.extractfile(member)
                if stream is None:
                    raise InstallationFailure("invalid_package")
                with stream, target.open("xb") as output:
                    while chunk := stream.read(1024 * 1024):
                        self.check_cancel()
                        output.write(chunk)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)

    def publisher(self, package):
        """macOS: OpenAI signed the CLI and its host. Windows has no such check; GitHub's digest stands alone."""
        from ..providers.codex.pins import HOST_IDENTIFIER, IDENTIFIER, TEAM_ID
        if host.WINDOWS:
            return
        for name, identifier in ((release.CLI, IDENTIFIER), (release.HOST, HOST_IDENTIFIER)):
            try:
                require_publisher(package / name, TEAM_ID, identifier)
            except QualificationError:
                raise InstallationFailure("invalid_package") from None

    def verify(self, package, target):
        """The package manifest names this release and target; returns the record of the files every check reads."""
        manifest = package / release.PACKAGE_MANIFEST
        try:
            raw = manifest.read_bytes() if manifest.is_file() and not manifest.is_symlink() else b""
            value = json.loads(raw) if 0 < len(raw) <= 65_536 else None
        except (OSError, ValueError):
            value = None
        if (not isinstance(value, dict) or value.get("version") != target.version or value.get("variant") != "codex"
                or value.get("target") != release.TARGET or value.get("entrypoint") != release.CLI):
            raise InstallationFailure("invalid_package")
        files = {}
        for name in self.runtime.names:
            path = package.joinpath(*PurePosixPath(name).parts)
            if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
                raise InstallationFailure("invalid_package")
            files[name] = digest(path, self.check_cancel)
        self.publisher(package)
        return Record(target.version, files)

    def stage(self, download, staging, target):
        self.unpack(download, staging)
        return self.verify(staging, target)

    def prune(self, keep):
        """Older releases and leftovers go once a new release is in place; a file still open stays until next time."""
        for item in self.root.iterdir():
            name = item.name
            if name == keep or not (VERSION.fullmatch(name) or name.startswith((".staging-", ".previous-"))):
                continue
            try:
                if item.is_dir() and not item.is_symlink():
                    host.remove_tree(item)
            except OSError:
                pass

    def install(self, files):
        staging = None
        previous = None
        committed = False
        target = None
        try:
            if not self.snapshot()["available"]:
                raise InstallationFailure("unsupported_platform")
            with self.owned():
                self.check_cancel()
                self.update(state="downloading", downloadedBytes=0, totalBytes=0, error=None)
                try:
                    target = self.resolve(files, self.cancel, time.monotonic() + CHECK_SECONDS)
                except ReleaseFailure as error:
                    raise InstallationFailure(error.code) from None
                self.check_cancel()
                self.update(totalBytes=target.size)
                archive = files.path / self.download_name
                self.download(files, archive, target)
                self.check_cancel()
                self.update(state="verifying", downloadedBytes=min(archive.stat().st_size, target.size))
                if archive.stat().st_size != target.size or digest(archive, self.check_cancel) != target.sha256:
                    raise InstallationFailure("checksum_failed")
                staging = self.root / (".staging-" + uuid.uuid4().hex)
                staging.mkdir(mode=0o700)
                self.update(state="extracting")
                record = self.stage(archive, staging, target)
                descriptor = os.open(staging / RECORD, os.O_WRONLY | os.O_CREAT | os.O_EXCL | host.O_NOFOLLOW
                                     | host.O_BINARY, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(record.encode())
                self.check_cancel()
                destination = self.root / target.version
                if destination.exists() or destination.is_symlink():
                    private_directory(destination)
                    previous = self.root / (".previous-" + uuid.uuid4().hex)
                    destination.rename(previous)
                try:
                    staging.rename(destination)
                except OSError:
                    if previous is not None:
                        previous.rename(destination)
                        previous = None
                    raise
                staging = None
                executable = destination.joinpath(*PurePosixPath(self.runtime.entry).parts)
                try:
                    if self.qualify is not None:
                        self.qualify(files, executable, target.version, self.cancel)
                    self.check_cancel()
                except BaseException:
                    host.remove_tree(destination)
                    if previous is not None:
                        previous.rename(destination)
                        previous = None
                    raise
                committed = True
                self.prune(target.version)
                self.update(state="ready")
                return executable
        except InstallationFailure as error:
            if error.code == "incompatible_release" and target is not None:
                self.refused.add(target.version)
            self.update(state="cancelled" if error.code == "cancelled" else "failed", error=error.code)
        except SpikeError as error:
            if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                raise
            self.update(state="cancelled" if self.cancel.is_set() else "failed",
                        error="cancelled" if self.cancel.is_set() else "download_failed")
        except (OSError, tarfile.TarError, ValueError):
            self.update(state="failed", error="install_failed")
        finally:
            for path in (staging, previous if committed else None):
                if path is not None and path.exists():
                    host.remove_tree(path)
        return None


class ClaudeInstallation(CliInstallation):
    """One Claude Code binary of the newest release, named by Anthropic's signed manifest (MP02b, D146)."""

    download_name = "claude"
    # The binary is about twice the Codex archive.
    seconds = 600

    @property
    def runtime(self):
        return claude_distribution.runtime(self.root)

    def lookup(self, fetch):
        return claude_distribution.latest(fetch)

    def publisher(self, binary):
        """macOS: the notarized binary Anthropic signed. On Windows the signed manifest's checksum stands alone."""
        from ..providers.claude.profile import IDENTIFIER, TEAM_ID
        if host.WINDOWS:
            return
        try:
            require_publisher(binary, TEAM_ID, IDENTIFIER)
        except QualificationError:
            raise InstallationFailure("invalid_package") from None

    def stage(self, download, staging, target):
        entry = claude_distribution.entry()
        binary = staging.joinpath(*PurePosixPath(entry).parts)
        binary.parent.mkdir(mode=0o700)
        with download.open("rb") as source, binary.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                self.check_cancel()
                output.write(chunk)
        binary.chmod(0o700)
        self.publisher(binary)
        # The download matched the manifest's checksum, so the copy carries it.
        return Record(target.version, {entry: target.sha256})
