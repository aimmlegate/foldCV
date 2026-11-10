"""Owned operation directories and process groups for CLI and worker runs: create, stop, reap and clean up."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import uuid

from packages.resume_core import host


OWNER = "resume-t00b-v1"
MAX_OUTPUT = 262144


class SpikeError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("non-finite number")

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise SpikeError("INVALID_RESULT") from None


def safe_environment(directory: Path) -> dict[str, str]:
    # Native auth remains CLI-owned. All other inherited runtime overrides vanish.
    if host.WINDOWS:
        return host.windows_environment(directory / "tmp", Path.home())
    env = {"PATH": os.defpath, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    env.update({
        "TMPDIR": str(directory / "tmp"),
        "XDG_CACHE_HOME": str(directory / "cache"),
        "XDG_DATA_HOME": str(directory / "data"),
        "XDG_STATE_HOME": str(directory / "state"),
    })
    return env


def _root(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise SpikeError("UNSAFE_TEMP_ROOT")
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        raise SpikeError("TEMP_FAILED") from None
    return path


INTENT_NAME = re.compile(r"\.cleanup-intent-op-([0-9a-f]{32})\.json\Z")


def _intent_path(root: Path, identifier: str) -> Path:
    return root / f".cleanup-intent-op-{identifier}.json"


def _write_cleanup_intent(root: Path, identifier: str, owner: str) -> Path:
    marker = _intent_path(root, identifier)
    raw = json.dumps({"owner": owner, "id": identifier}, separators=(",", ":")).encode("utf-8")
    if len(raw) > 256:
        raise OSError("cleanup identity too large")
    with marker.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    host.sync_directory(root)
    return marker


def cleanup_intent_ids(root: Path, *, owner: str = OWNER) -> set[str]:
    result = set()
    try:
        entries = list(root.iterdir())
    except OSError:
        raise SpikeError("CLEANUP_FAILED") from None
    for marker in entries:
        match = INTENT_NAME.fullmatch(marker.name)
        # Windows refuses to open a directory; on POSIX the mode check below would skip it.
        if match is None or marker.is_symlink() or marker.is_dir():
            continue
        try:
            descriptor = os.open(marker, os.O_RDONLY | host.O_NOFOLLOW | host.O_NONBLOCK | host.O_BINARY)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size == 0 or info.st_size > 256:
                    continue
                chunks = []
                remaining = info.st_size
                while remaining:
                    chunk = os.read(descriptor, remaining)
                    if not chunk:
                        raise OSError("short cleanup intent")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
                if os.fstat(descriptor).st_size != info.st_size:
                    raise OSError("changed cleanup intent")
            finally:
                os.close(descriptor)
            record = strict_json(raw)
        except SpikeError:
            continue
        except OSError:
            raise SpikeError("CLEANUP_FAILED") from None
        if record == {"owner": owner, "id": match.group(1)}:
            result.add(match.group(1))
    return result


def _remove_owned_directory(root: Path, directory: Path, identifier: str, owner: str) -> None:
    try:
        marker = _write_cleanup_intent(root, identifier, owner)
    except OSError:
        try:
            (directory / ".cleanup-blocked").touch()
        except OSError:
            pass
        raise SpikeError("CLEANUP_FAILED") from None
    try:
        host.remove_tree(directory)
        marker.unlink()
    except OSError:
        raise SpikeError("CLEANUP_FAILED") from None


@contextmanager
def operation(root: Path, *, owner: str = OWNER):
    root = _root(root)
    identifier = uuid.uuid4().hex
    directory = root / f"op-{identifier}"
    try:
        directory.mkdir(mode=0o700)
    except OSError:
        raise SpikeError("TEMP_FAILED") from None
    lock = None
    preserve = False
    try:
        lock = (directory / ".lock").open("xb")
        host.lock(lock.fileno())
        (directory / ".owner").write_text(json.dumps({"owner": owner, "id": identifier}))
        for name in ("tmp", "cache", "data", "state", "logs"):
            (directory / name).mkdir(mode=0o700)
        yield directory
    except SpikeError as error:
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
            preserve = True
            try:
                (directory / ".cleanup-blocked").touch()
            except OSError:
                try:
                    _write_cleanup_intent(root, identifier, owner)
                except OSError:
                    pass
                raise SpikeError("CLEANUP_FAILED") from None
        raise
    except OSError:
        raise SpikeError("TEMP_FAILED") from None
    finally:
        try:
            if lock and host.WINDOWS:
                # Windows cannot delete an open file; one service owns its operations root.
                lock.close()
            if not preserve:
                _remove_owned_directory(root, directory, identifier, owner)
        finally:
            if lock:
                lock.close()


def reap_owned(root: Path, *, owner: str = OWNER) -> int:
    count = 0
    try:
        root = _root(root)
        entries = list(root.iterdir())
        blocked_ids = cleanup_intent_ids(root, owner=owner)
    except OSError:
        raise SpikeError("TEMP_FAILED") from None
    for path in entries:
        if path.is_symlink() or not path.is_dir() or not re.fullmatch(r"op-[0-9a-f]{32}", path.name):
            continue
        if path.name[3:] in blocked_ids:
            continue
        if (path / ".cleanup-blocked").exists():
            continue
        marker, lock_path = path / ".owner", path / ".lock"
        if marker.is_symlink() or lock_path.is_symlink() or not marker.is_file() or not lock_path.is_file():
            continue
        try:
            try:
                if marker.stat().st_size > 256:
                    continue
                record_owner = strict_json(marker.read_bytes())
            except (OSError, SpikeError):
                continue
            if record_owner != {"owner": owner, "id": path.name[3:]}:
                continue
            with lock_path.open("rb") as lock:
                try:
                    host.lock(lock.fileno(), blocking=False)
                except BlockingIOError:
                    continue
                worker = path / ".worker"
                if worker.is_symlink() or worker.exists():
                    if worker.is_symlink() or not worker.is_file() or worker.stat().st_size > 64:
                        (path / ".cleanup-blocked").touch()
                        continue
                    try:
                        record = strict_json(worker.read_bytes())
                    except (OSError, SpikeError):
                        (path / ".cleanup-blocked").touch()
                        continue
                    pid = record.get("pid") if isinstance(record, dict) and set(record) == {"pid"} else None
                    if type(pid) is not int or pid <= 1:
                        (path / ".cleanup-blocked").touch()
                        continue
                    try:
                        if group_members(pid):
                            continue
                    except SpikeError:
                        continue
                if host.WINDOWS:
                    lock.close()
                _remove_owned_directory(root, path, path.name[3:], owner)
                count += 1
        except (OSError, SpikeError):
            raise SpikeError("CLEANUP_FAILED") from None
    return count


def group_members(group_id):
    if host.WINDOWS:
        # A worker's job ends with the service that started it; only the worker itself can be left.
        return [group_id] if host.process_alive(group_id) else []
    try:
        inventory = subprocess.run(
            ["/bin/ps", "-axo", "pid=,pgid=,stat="], capture_output=True, timeout=1,
            env={"PATH": os.defpath, "LC_ALL": "C"},
        )
        if inventory.returncode or len(inventory.stdout) > MAX_OUTPUT:
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        return [int(pid) for pid, group, state in (line.split(maxsplit=2) for line in inventory.stdout.splitlines())
                if int(group) == group_id and not state.startswith(b"Z")]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise SpikeError("PROCESS_CLEANUP_FAILED") from None


def stop_group(process):
    if host.WINDOWS:
        from packages.resume_core import winjob
        try:
            if not winjob.stop(process):
                raise SpikeError("PROCESS_CLEANUP_FAILED")
        except (OSError, subprocess.TimeoutExpired):
            raise SpikeError("PROCESS_CLEANUP_FAILED") from None
        return
    try:
        gone = 0
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                gone += 1
            except PermissionError:
                # macOS may deny group signals after the leader exits. Check
                # only this operation's group, without inspecting command text.
                for pid in group_members(process.pid):
                    try:
                        os.kill(pid, sig)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        raise SpikeError("PROCESS_CLEANUP_FAILED") from None
            if sig == signal.SIGTERM:
                time.sleep(0.05)
        # A group both signals found gone has no member left to list (D153): a probe command that exited on its
        # own costs no process listing, which takes seconds on a loaded machine.
        if gone == 2:
            return
        # A fallback PID snapshot can miss a same-group fork. Reinspect after
        # signaling until no live member can create another child.
        limit = time.monotonic() + 1.5
        while True:
            members = group_members(process.pid)
            if not members:
                break
            if time.monotonic() >= limit:
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            for pid in members:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    raise SpikeError("PROCESS_CLEANUP_FAILED") from None
            time.sleep(0.02)
    finally:
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            raise SpikeError("PROCESS_CLEANUP_FAILED") from None
