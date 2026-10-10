"""Small POSIX process experiment. Real generation fails closed pending evidence."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import threading
import time
import uuid

from spikes.cli.profile import (
    FIXTURE_PROFILE, GAPS, REAL_PROFILE, REQUIRED_FLAGS, exec_arguments, overrides,
)


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"summary": {"type": "string", "minLength": 1, "maxLength": 400}},
    "required": ["summary"],
}
OWNER = "resume-t00b-v1"
MAX_INPUT = 8192
MAX_OUTPUT = 262144
MAX_LINE = 65536
MODEL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


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


def provider_error(raw: str, code: str | None = None) -> str:
    mapped = {
        "rate_limit_exceeded": "RATE_LIMITED",
        "authentication_error": "AUTH_REQUIRED",
        "model_not_supported": "MODEL_DENIED",
    }
    if code in mapped:
        return mapped[code]
    # Stderr is untrusted and may echo the prompt. Only a whole CLI diagnostic counts.
    text = raw.strip().lower()
    if text == "not logged in":
        return "AUTH_REQUIRED"
    return "CLI_FAILED"


def safe_environment(directory: Path) -> dict[str, str]:
    # Native auth remains CLI-owned. All other inherited runtime overrides vanish.
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
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return marker


def cleanup_intent_ids(root: Path, *, owner: str = OWNER) -> set[str]:
    result = set()
    try:
        entries = list(root.iterdir())
    except OSError:
        raise SpikeError("CLEANUP_FAILED") from None
    for marker in entries:
        match = INTENT_NAME.fullmatch(marker.name)
        if match is None or marker.is_symlink():
            continue
        try:
            descriptor = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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
        shutil.rmtree(directory)
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
        fcntl.flock(lock, fcntl.LOCK_EX)
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
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
                _remove_owned_directory(root, path, path.name[3:], owner)
                count += 1
        except (OSError, SpikeError):
            raise SpikeError("CLEANUP_FAILED") from None
    return count


def group_members(group_id):
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
    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
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


@dataclass(frozen=True)
class Probe:
    version: str
    auth_mode: str
    generation_ready: bool
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    summary: str
    version: str
    model: str
    elapsed_seconds: float
    usage: dict | None
    generation_starts: int = 1
    internal_inference_count: None = None

    def metadata(self):
        result = asdict(self)
        del result["summary"]
        result["status"] = "completed"
        return result


class Events:
    def __init__(self):
        self.thread = False
        self.turn = False
        self.complete = False
        self.text = None
        self.usage = None

    def accept(self, raw):
        event = strict_json(raw)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise SpikeError("INVALID_RESULT")
        kind = event["type"]
        if self.complete:
            raise SpikeError("INVALID_RESULT")
        if kind == "thread.started" and not self.thread and not self.turn:
            self.thread = True
        elif kind == "turn.started" and self.thread and not self.turn:
            self.turn = True
        elif kind in ("item.started", "item.updated", "item.completed") and self.turn:
            item = event.get("item")
            if not isinstance(item, dict):
                raise SpikeError("INVALID_RESULT")
            if item.get("type") not in ("reasoning", "agent_message"):
                raise SpikeError("UNEXPECTED_TOOL_ACTIVITY")
            if kind == "item.completed" and item["type"] == "agent_message":
                if self.text is not None or not isinstance(item.get("text"), str):
                    raise SpikeError("INVALID_RESULT")
                self.text = item["text"]
        elif kind == "turn.completed" and self.turn and self.text is not None:
            self.complete = True
            usage = event.get("usage")
            if usage is not None:
                keys = ("input_tokens", "cached_input_tokens", "output_tokens")
                if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in keys):
                    raise SpikeError("INVALID_RESULT")
                self.usage = {key: usage[key] for key in keys}
        elif kind in ("error", "turn.failed"):
            error = event.get("error", event)
            message = error.get("message", "") if isinstance(error, dict) else ""
            code = error.get("code") if isinstance(error, dict) else None
            raise SpikeError(provider_error(message if isinstance(message, str) else "",
                                            code if isinstance(code, str) else None))
        else:
            raise SpikeError("INVALID_RESULT")

    def result(self):
        if not self.complete:
            raise SpikeError("INCOMPLETE_STREAM")
        value = strict_json(self.text)
        if not isinstance(value, dict) or set(value) != {"summary"}:
            raise SpikeError("INVALID_RESULT")
        summary = value["summary"]
        if not isinstance(summary, str) or not 1 <= len(summary) <= 400:
            raise SpikeError("INVALID_RESULT")
        try:
            summary.encode("utf-8")
        except UnicodeError:
            raise SpikeError("INVALID_RESULT") from None
        return summary


class Runner:
    def __init__(self, executable=None, *, root=None, clock=time.monotonic):
        executable = str(executable) if executable is not None else shutil.which("codex")
        if not executable:
            raise SpikeError("CLI_MISSING")
        self.executable = str(Path(executable).absolute())
        self.root = Path(root or "experiments/gui-cli-spike/operations")
        self.clock = clock
        self.generation_starts = 0
        self.last_version = None
        self.last_metadata = None
        reap_owned(self.root)

    def _process(self, arguments, directory, *, data=b"", timeout=10, cancel=None,
                 on_line=None, interactive=False, deadline=None):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise SpikeError("INVALID_LIMIT")
        cancel = cancel or threading.Event()
        if cancel.is_set():
            raise SpikeError("CANCELLED")
        deadline = min(self.clock() + timeout, deadline) if deadline is not None else self.clock() + timeout
        process = None
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        pending = bytearray(data)
        line = bytearray()
        close_input = not interactive
        try:
            # A crash after spawn must leave an unverified marker, not an
            # apparently inactive operation directory.
            (directory / ".worker").write_text('{"state":"spawning"}')
            self._check(deadline, cancel)
            process = subprocess.Popen(
                [self.executable, *arguments], cwd=directory, env=safe_environment(directory),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, shell=False,
            )
            if arguments[0] == "exec" and "--help" not in arguments:
                self.generation_starts += 1
            (directory / ".worker").write_text(json.dumps({"pid": process.pid}))
            with selectors.DefaultSelector() as selector:
                for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr"), (process.stdin, "stdin")):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_WRITE if name == "stdin" else selectors.EVENT_READ, name)
                while selector.get_map() or process.poll() is None:
                    self._check(deadline, cancel)
                    for key, _ in selector.select(0.02):
                        name, stream = key.data, key.fileobj
                        if name == "stdin":
                            if pending:
                                try:
                                    sent = os.write(stream.fileno(), pending[:4096])
                                    del pending[:sent]
                                except BrokenPipeError:
                                    pending.clear()
                                    close_input = True
                            if not pending:
                                selector.unregister(stream)
                                if close_input:
                                    stream.close()
                            continue
                        chunk = os.read(stream.fileno(), 4096)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        buffers[name].extend(chunk)
                        if sum(map(len, buffers.values())) > MAX_OUTPUT:
                            raise SpikeError("OUTPUT_TOO_LARGE")
                        if name == "stdout" and on_line:
                            line.extend(chunk)
                            while b"\n" in line:
                                raw, _, remainder = line.partition(b"\n")
                                line = bytearray(remainder)
                                if not raw or len(raw) > MAX_LINE:
                                    raise SpikeError("INVALID_RESULT")
                                reply = on_line(bytes(raw))
                                if reply is not None:
                                    pending.extend(reply)
                                    close_input = not reply
                                    if process.stdin.closed:
                                        raise SpikeError("INVALID_RESULT")
                                    if process.stdin not in [entry.fileobj for entry in selector.get_map().values()]:
                                        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
                            if len(line) > MAX_LINE:
                                raise SpikeError("OUTPUT_TOO_LARGE")
                self._check(deadline, cancel)
                if line:
                    raise SpikeError("INCOMPLETE_STREAM")
                if process.returncode:
                    raise SpikeError(provider_error(buffers["stderr"].decode("utf-8", errors="replace")))
                return bytes(buffers["stdout"]), bytes(buffers["stderr"])
        except FileNotFoundError:
            raise SpikeError("CLI_MISSING") from None
        except (OSError, ValueError):
            raise SpikeError("CLI_FAILED") from None
        finally:
            if process:
                try:
                    stop_group(process)
                    (directory / ".worker").unlink(missing_ok=True)
                finally:
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if not stream.closed:
                            stream.close()

    def _check(self, deadline, cancel):
        if cancel.is_set():
            raise SpikeError("CANCELLED")
        if self.clock() >= deadline:
            raise SpikeError("DEADLINE_EXCEEDED")

    def probe(self, *, deadline=None, cancel=None) -> Probe:
        with operation(self.root) as directory:
            stdout, _ = self._process(["--version"], directory, deadline=deadline, cancel=cancel)
            version = stdout.decode("utf-8", errors="replace").strip()
            if version not in (REAL_PROFILE.version, FIXTURE_PROFILE.version):
                raise SpikeError("CLI_UNSUPPORTED")
            profile = REAL_PROFILE if version == REAL_PROFILE.version else FIXTURE_PROFILE
            self.last_version = version
            stdout, _ = self._process(["exec", "--help"], directory, deadline=deadline, cancel=cancel)
            help_text = stdout.decode("utf-8", errors="replace")
            if any(flag not in help_text for flag in REQUIRED_FLAGS):
                raise SpikeError("CLI_PROFILE_UNSAFE")
            stdout, stderr = self._process(["login", "status"], directory, deadline=deadline, cancel=cancel)
            status = (stdout + stderr).decode("utf-8", errors="replace").lower()
            if "logged in using chatgpt" in status:
                mode = "chatgpt"
            elif "api key" in status or "api-key" in status:
                raise SpikeError("AUTH_MODE_MISMATCH")
            else:
                raise SpikeError("AUTH_REQUIRED")
            return Probe(version, mode, profile.generation_verified, () if profile.generation_verified else GAPS)

    def metadata(self):
        """A metadata-only app-server connection. Never create a thread or turn."""
        self.probe()
        state = {"id": 0, "auth_mode": None, "models": []}

        def request(identifier, method, params):
            return (json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode()

        def accept(raw):
            event = strict_json(raw)
            if not isinstance(event, dict):
                raise SpikeError("UNEXPECTED_METADATA_EVENT")
            if "method" in event:
                if event["method"] == "account/updated" and "id" not in event:
                    params = event.get("params")
                    if not isinstance(params, dict) or params.get("authMode") != "chatgpt":
                        raise SpikeError("AUTH_MODE_MISMATCH")
                    return None
                if event["method"] == "remoteControl/status/changed" and "id" not in event:
                    return None
                raise SpikeError("UNEXPECTED_METADATA_EVENT")
            if event.get("id") != state["id"] or "error" in event or not isinstance(event.get("result"), dict):
                raise SpikeError("METADATA_FAILED")
            value = event["result"]
            if state["id"] == 0:
                state["id"] = 1
                return b'{"method":"initialized"}\n' + request(1, "account/read", {"refreshToken": False})
            if state["id"] == 1:
                account = value.get("account")
                if not isinstance(account, dict) or account.get("type") != "chatgpt":
                    raise SpikeError("AUTH_MODE_MISMATCH")
                state["auth_mode"] = "chatgpt"
                state["id"] = 2
                return request(2, "model/list", {"includeHidden": False, "limit": 100})
            if state["id"] != 2:
                raise SpikeError("METADATA_FAILED")
            models = value.get("data")
            if not isinstance(models, list):
                raise SpikeError("METADATA_FAILED")
            for item in models:
                slug = item.get("model") if isinstance(item, dict) else None
                if not isinstance(slug, str) or not MODEL.fullmatch(slug):
                    raise SpikeError("METADATA_FAILED")
                state["models"].append(slug)
            state["catalog_complete"] = value.get("nextCursor") is None
            state["id"] = 3
            return b""

        with operation(self.root) as directory:
            self._process(
                ["app-server", "--strict-config", *overrides(directory)], directory,
                data=request(0, "initialize", {"clientInfo": {"name": "resume_t00b", "version": "0.1.0"}}),
                on_line=accept, interactive=True, timeout=15,
            )
        if state["id"] != 3:
            raise SpikeError("INCOMPLETE_STREAM")
        return {key: value for key, value in state.items() if key != "id"}

    def generate(self, prompt, *, model, timeout=60, cancel=None) -> Result:
        start = self.clock()
        before = self.generation_starts
        try:
            result = self._generate(prompt, model=model, timeout=timeout, cancel=cancel)
            self.last_metadata = result.metadata()
            return result
        except SpikeError as error:
            self.last_metadata = {
                "status": "failed", "code": error.code, "version": self.last_version,
                "model": model if isinstance(model, str) and MODEL.fullmatch(model) else None,
                "elapsed_seconds": self.clock() - start,
                "generation_starts": self.generation_starts - before,
                "usage": None, "internal_inference_count": None,
            }
            raise

    def _generate(self, prompt, *, model, timeout=60, cancel=None) -> Result:
        if not isinstance(prompt, str):
            raise SpikeError("INVALID_INPUT")
        try:
            data = prompt.encode("utf-8")
        except UnicodeError:
            raise SpikeError("INVALID_INPUT") from None
        if not data:
            raise SpikeError("INVALID_INPUT")
        if len(data) > MAX_INPUT:
            raise SpikeError("INPUT_TOO_LARGE")
        if not isinstance(model, str) or not MODEL.fullmatch(model):
            raise SpikeError("MODEL_DENIED")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise SpikeError("INVALID_LIMIT")
        cancel = cancel or threading.Event()
        if cancel.is_set():
            raise SpikeError("CANCELLED")
        start = self.clock()
        deadline = start + timeout
        probe = self.probe(deadline=deadline, cancel=cancel)
        self._check(deadline, cancel)
        if not probe.generation_ready:
            raise SpikeError("CLI_PROFILE_UNSAFE")
        events = Events()
        with operation(self.root) as directory:
            (directory / "schema.json").write_text(json.dumps(SCHEMA))
            self._process(exec_arguments(directory, model), directory, data=data,
                          timeout=timeout, deadline=deadline, cancel=cancel, on_line=events.accept)
            summary = events.result()
        self._check(deadline, cancel)
        return Result(summary, probe.version, model, self.clock() - start, events.usage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "metadata", "live", "cleanup"))
    parser.add_argument("--executable")
    parser.add_argument("--root", type=Path, default=Path("experiments/gui-cli-spike/operations"))
    args = parser.parse_args()
    try:
        if args.action == "cleanup":
            result = {"removed_owned_directories": reap_owned(args.root)}
        else:
            runner = Runner(args.executable, root=args.root)
            if args.action == "probe":
                result = asdict(runner.probe())
            elif args.action == "metadata":
                result = runner.metadata()
            else:
                # At most one start per explicit action, no retry or model fallback.
                if not runner.probe().generation_ready:
                    raise SpikeError("CLI_PROFILE_UNSAFE")
                catalog = runner.metadata()
                if "gpt-6-luna" not in catalog["models"]:
                    raise SpikeError("MODEL_DENIED")
                canary = "T00B_SYNTHETIC_" + uuid.uuid4().hex
                result = runner.generate(
                    f"Return a short summary about fictional engineer Alex Example. Include {canary}.",
                    model="gpt-6-luna", timeout=60,
                ).metadata()
        print(json.dumps(result, ensure_ascii=True))
    except SpikeError as error:
        print(json.dumps({"status": "failed", "code": error.code}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
