"""Parse one operation-owned source inside the managed process group."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.resume_core.extraction.parser import ExtractFailure, extract

VM_HEADROOM = 256 * 1024**2


def limit_virtual_memory() -> None:
    if sys.platform == "win32":
        return  # The service's job caps this worker's memory there.
    import resource

    result = subprocess.run(("/bin/ps", "-o", "vsz=", "-p", str(os.getpid())), capture_output=True,
                            timeout=1, check=False, text=True)
    if result.returncode or not result.stdout.strip().isdigit():
        raise ExtractFailure("EXTRACT_MONITOR_UNAVAILABLE")
    baseline = int(result.stdout.strip()) * 1024
    limit = baseline + VM_HEADROOM
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def main() -> int:
    workspace = Path.cwd()
    try:
        limit_virtual_memory()
        metadata = json.loads((workspace / "extract-input.json").read_text(encoding="utf-8"))
        data = (workspace / "source.bin").read_bytes()
        result = extract(data, metadata["name"], metadata["pasted"])
        output = result.model_dump_json(by_alias=True).encode("utf-8")
        if len(output) > 4 * 1024 * 1024:
            raise ExtractFailure("EXTRACT_TEXT_LIMIT")
        (workspace / "extract-output.json").write_bytes(output)
        return 0
    except ExtractFailure as error:
        code = error.code
    except (OSError, ValueError, MemoryError):
        code = "EXTRACT_FAILED"
    (workspace / "extract-status.json").write_text(json.dumps({"code": code}), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
