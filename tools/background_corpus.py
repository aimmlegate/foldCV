"""Run every frozen production trace in bounded, independent pytest processes."""

import json
from pathlib import Path
import signal
import subprocess

WORKERS = 4


def production_nodes(spec):
    return sorted({row["nodeId"] for row in spec["requiredTraces"].values()
        if row["scope"] == "production_integration"})


def run_shards(python, nodes, *, context, root: Path, cwd: Path, env, coverage_arguments, retained):
    groups = [nodes[index::WORKERS] for index in range(min(WORKERS, len(nodes)))]
    plan, running, failures = [], [], []
    try:
        for index, targets in enumerate(groups):
            name = f"corpus-{index}"
            report = root / ("execution-" + name + ".json")
            context_file = root / ("context-" + name + ".json")
            context_file.write_text(json.dumps({**context, "reportPath": str(report)}))
            worker_env = {**env, "COVERAGE_FILE": str(root / (".coverage-" + name)),
                "FOLDCV_BACKGROUND_CONTEXT": str(context_file)}
            log_path = root / (name + ".log")
            output = log_path.open("w")
            try:
                process = subprocess.Popen([str(python), "-m", "pytest", "-q", *targets, "-p", "tools.background_pytest",
                    *coverage_arguments, "--cov-report=json:" + str(root / ("branches-" + name + ".json"))],
                    cwd=cwd, env=worker_env, stdout=output, stderr=subprocess.STDOUT)
            except BaseException:
                output.close()
                raise
            running.append((process, output))
            plan.append(dict(worker=index, pid=process.pid, nodes=targets, report=str(report), log=str(log_path)))
        for directory in retained:
            (directory / "corpus-plan.json").write_text(json.dumps(dict(workers=plan,
                scope="Independent offline stores; every product supervisor remains at capacity one."), indent=2) + "\n")
        print(f"NB production corpus: {len(nodes)} exact tests across {len(groups)} isolated workers", flush=True)
        for index, (process, _output) in enumerate(running):
            code = process.wait()
            print(f"NB corpus worker {index}: exit {code}; {len(groups[index])} exact tests", flush=True)
            if code:
                failures.append(code)
    finally:
        for process, _output in running:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for process, output in running:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
            output.close()
    if failures:
        raise subprocess.CalledProcessError(failures[0], "NB production corpus workers")


def retain_raw(root, directories):
    names = {"context.json", "context-python.json", "execution-python.json", "branches.json", "branches-base.json"}
    for pattern in ("context-corpus-*.json", "execution-corpus-*.json", "branches-corpus-*.json", "corpus-*.log"):
        names.update(path.name for path in root.glob(pattern))
    for directory in directories:
        for name in names:
            path = root / name
            if path.is_file():
                (directory / name).write_bytes(path.read_bytes())
