"""The local app log: what it records about CLI runs, connection jobs, tasks and errors, and what it keeps out."""

import logging
import sys
import threading
import time

import pytest

from packages.resume_core.repository.project_tasks import TaskRegistry
from resume_api import app_log
from resume_api.cli.process_runner import ProcessExit, ProcessRunner, command_words
from resume_api.lifecycle import OperationFiles, SpikeError

SCRIPT = """import sys
args = sys.argv[1:]
if args[0] == "--version":
    sys.stderr.write("cannot start: state=one-time-value\\n"); sys.exit(3)
if args[0] == "-p":
    sys.stdin.read(); sys.stderr.write("synthetic resume text\\n"); sys.exit(2)
print("fine")
"""


@pytest.fixture
def cli(tmp_path):
    path = tmp_path / "claude"
    path.write_text("#!" + sys.executable + "\n" + SCRIPT)
    path.chmod(0o700)
    return path


def run(root, cli, arguments, **options):
    with OperationFiles(root).open() as files:
        return ProcessRunner(cli).run(files, arguments, cancel=threading.Event(), deadline=time.monotonic() + 10, **options)


@pytest.mark.parametrize(("arguments", "words"), [
    (("auth", "status", "--json"), "auth status"), (("-p", "--output-format"), "-p --output-format"),
    (("exec", "Rewrite this resume"), "exec"), (("Иванов",), ""), (("--config", 'log_dir="/x"'), "--config"),
    (("-q", "--fail", "https://x"), "-q --fail"), ((), ""),
])
def test_a_run_is_named_by_its_leading_words_only(arguments, words):
    assert command_words(arguments) == words


def test_cli_runs_are_logged_with_outcome_and_only_told_error_output(tmp_path, cli, caplog):
    caplog.set_level(logging.INFO, logger="foldcv")
    assert run(tmp_path / "ok", cli, ("auth", "status"))[0] == b"fine\n"
    with pytest.raises(ProcessExit) as failed:
        run(tmp_path / "version", cli, ("--version",))
    assert failed.value.returncode == 3
    with pytest.raises(ProcessExit):
        run(tmp_path / "generation", cli, ("-p", "--model"), data=b"synthetic prompt")
    with pytest.raises(SpikeError):
        run(tmp_path / "missing", tmp_path / "absent", ("auth", "status"))
    lines = [record.getMessage() for record in caplog.records if record.name == "foldcv.cli"]
    assert lines[0].startswith("claude auth status: ok in ")
    assert lines[1].startswith("claude --version: exit 3 in ") and lines[1].endswith("cannot start: state=…")
    assert lines[2].startswith("claude -p --model: exit 2 in ") and "\n" not in lines[2]
    assert lines[3].startswith("absent auth status: CLI_MISSING")
    text = "\n".join(lines)
    assert "synthetic" not in text and "one-time-value" not in text


def test_failures_name_codes_system_errors_and_what_they_replaced():
    assert app_log.failure(SpikeError("DEADLINE_EXCEEDED")) == "DEADLINE_EXCEEDED"
    error = PermissionError(13, "Permission denied")
    assert app_log.failure(error) == "PermissionError errno=13: Permission denied"
    try:
        try:
            raise ValueError("synthetic resume text")
        except ValueError:
            raise SpikeError("CLI_FAILED") from None
    except SpikeError as replaced:
        assert app_log.failure(replaced) == "CLI_FAILED (from ValueError)"
        assert "synthetic" not in app_log.where(replaced) and "test_failures_name" in app_log.where(replaced)


def test_task_lines_name_kind_project_outcome_and_stage(caplog):
    caplog.set_level(logging.INFO, logger="foldcv")
    tasks = TaskRegistry()
    task = tasks.start("project-1", "import", stage="starting")
    tasks.update(task.id, stage="model")
    tasks.finish(task.id, "failed", error="MODEL_TIMEOUT")
    tasks.finish(task.id, "failed", error="MODEL_TIMEOUT")
    lines = [record.getMessage() for record in caplog.records if record.name == "foldcv.tasks"]
    assert lines[0] == "import_1 started on project project-1"
    assert lines[1].startswith("import_1 on project project-1: failed MODEL_TIMEOUT at stage model after ")
    assert len(lines) == 2


def test_configure_writes_the_file_once_and_keeps_other_info_out(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        app_log.configure(tmp_path)
        app_log.configure(tmp_path)
        added = [handler for handler in root.handlers if handler not in before]
        assert len(added) == 1
        logging.getLogger("httpx").info("HTTP Request: synthetic")
        logging.getLogger("resume_api.projects").warning("catalog unreadable")
        app_log.EVENTS.getChild("cli").info("claude --version: ok in 0.1 s")
        added[0].flush()
        text = (tmp_path / "logs" / app_log.NAME).read_text()
        assert "service started: Python" in text and "claude --version: ok" in text and "catalog unreadable" in text
        assert "HTTP Request" not in text
    finally:
        for handler in [handler for handler in root.handlers if handler not in before]:
            root.removeHandler(handler)
            handler.close()


def test_an_unopenable_log_leaves_the_service_without_it(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("")
    before = list(logging.getLogger().handlers)
    app_log.configure(blocked)
    assert logging.getLogger().handlers == before
