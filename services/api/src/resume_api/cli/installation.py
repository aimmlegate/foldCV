"""Explicit, cancellable installation into an app-owned directory."""

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import tarfile
import threading
import time
import uuid

from . import claude_distribution, distribution as release
from .process_runner import ProcessExit, ProcessRunner
from ..lifecycle import SpikeError

MARKER = ".foldcv-cli-runtime-v1"
MAX_UNPACKED = 400_000_000


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
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise InstallationFailure("unsafe_directory")


class CliInstallation:
    """The Codex package: one pinned archive with the CLI, its code-mode host and the package manifest."""

    download_name = "codex.tar.gz"
    seconds = 300

    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.value = {"state": "idle", "downloadedBytes": 0, "totalBytes": self.size,
                      "version": self.release, "error": None,
                      "available": platform.system() == "Darwin" and platform.machine() == "arm64"}

    # Read on each use, so a test can patch the pinned module values.
    @property
    def release(self):
        return release.RELEASE

    @property
    def url(self):
        return release.ARCHIVE_URL

    @property
    def size(self):
        return release.ARCHIVE_BYTES

    @property
    def sha256(self):
        return release.ARCHIVE_SHA256

    @property
    def executable(self):
        return release.managed_executable(self.root)

    def snapshot(self):
        with self.lock:
            return dict(self.value)

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
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write("foldcv-cli-runtime-v1\n")
        if (marker.is_symlink() or marker.stat().st_uid != os.getuid()
                or marker.stat().st_size != 22 or marker.read_text() != "foldcv-cli-runtime-v1\n"):
            raise InstallationFailure("unsafe_directory")
        descriptor = os.open(self.root / ".install.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(descriptor).st_uid != os.getuid() or os.fstat(descriptor).st_nlink != 1:
                raise InstallationFailure("unsafe_directory")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InstallationFailure("busy") from None
            yield
        finally:
            os.close(descriptor)

    def check_cancel(self):
        if self.cancel.is_set():
            raise InstallationFailure("cancelled")

    def download(self, files, archive):
        deadline = time.monotonic() + self.seconds

        def progress():
            self.check_cancel()
            size = archive.stat().st_size if archive.exists() else 0
            if size > self.size:
                raise InstallationFailure("download_failed")
            self.update(downloadedBytes=size)

        try:
            ProcessRunner(Path("/usr/bin/curl")).run(files, (
                "-q", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                "--proto-redir", "=https", "--connect-timeout", "15", "--max-time", str(self.seconds),
                "--max-filesize", str(self.size), "--output", str(archive), self.url,
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
                        or not (member.isfile() or member.isdir()) or name in names or len(names) >= 200):
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

    def verify(self, package):
        for name, expected in (("bin/codex", release.CLI_SHA256),
                               ("bin/codex-code-mode-host", release.HOST_SHA256),
                               ("codex-package.json", release.MANIFEST_SHA256)):
            path = package / name
            if (any(part.is_symlink() for part in (path, *path.parents))
                    or not path.is_file() or digest(path, self.check_cancel) != expected):
                raise InstallationFailure("invalid_package")

    def stage(self, download, staging):
        self.unpack(download, staging)
        self.verify(staging)

    def install(self, files):
        staging = None
        previous = None
        committed = False
        try:
            if not self.snapshot()["available"]:
                raise InstallationFailure("unsupported_platform")
            with self.owned():
                self.check_cancel()
                archive = files.path / self.download_name
                self.update(state="downloading", downloadedBytes=0, error=None)
                self.download(files, archive)
                self.check_cancel()
                self.update(state="verifying", downloadedBytes=min(archive.stat().st_size, self.size))
                if archive.stat().st_size != self.size or digest(archive, self.check_cancel) != self.sha256:
                    raise InstallationFailure("checksum_failed")
                staging = self.root / (".staging-" + uuid.uuid4().hex)
                staging.mkdir(mode=0o700)
                self.update(state="extracting")
                self.stage(archive, staging)
                self.check_cancel()
                destination = self.executable.parent.parent
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
                committed = True
                self.update(state="ready")
                return self.executable
        except InstallationFailure as error:
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
                    shutil.rmtree(path)
        return None


class ClaudeInstallation(CliInstallation):
    """One notarized Claude Code binary, pinned from the signed release manifest (MP02b)."""

    download_name = "claude"
    # The binary is about twice the Codex archive.
    seconds = 600

    @property
    def release(self):
        return claude_distribution.RELEASE

    @property
    def url(self):
        return claude_distribution.BINARY_URL

    @property
    def size(self):
        return claude_distribution.BINARY_BYTES

    @property
    def sha256(self):
        return claude_distribution.BINARY_SHA256

    @property
    def executable(self):
        return claude_distribution.managed_executable(self.root)

    def stage(self, download, staging):
        target = staging / "bin/claude"
        target.parent.mkdir(mode=0o700)
        with download.open("rb") as source, target.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                self.check_cancel()
                output.write(chunk)
        target.chmod(0o700)
