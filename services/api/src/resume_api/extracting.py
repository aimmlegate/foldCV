"""Bounded one-part upload and managed extraction worker."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys

from packages.resume_core.extraction.models import ExtractResult
from packages.resume_core.extraction.parser import MAX_SOURCE

from .lifecycle import OperationFiles

WORKER = Path(__file__).resolve().parents[4] / "packages/resume_core/extraction/worker.py"
MAX_BODY = MAX_SOURCE + 8192
MAX_RESULT = 4 * 1024 * 1024
MAX_RSS_KB = 512 * 1024
BOUNDARY = re.compile(rb"^[A-Za-z0-9'()+_,./:=?-]{1,70}$")
ALLOWED_ERRORS = frozenset({"EXTRACT_EMPTY", "INPUT_TOO_LARGE", "EXTRACT_ENCODING", "EXTRACT_UNSUPPORTED",
                           "EXTRACT_MALFORMED", "EXTRACT_ENCRYPTED", "EXTRACT_PAGE_LIMIT", "EXTRACT_TEXT_LIMIT",
                           "EXTRACT_UNIT_LIMIT", "EXTRACT_ARCHIVE_LIMIT", "EXTRACT_UNSAFE_ARCHIVE",
                           "EXTRACT_UNSAFE_XML", "EXTRACT_EXTERNAL_LINK", "EXTRACT_MEMORY_LIMIT",
                           "EXTRACT_MONITOR_UNAVAILABLE"})


class UploadFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def parse_one_part(body: bytes, content_type: str) -> tuple[bytes, str, bool]:
    match = re.fullmatch(r"multipart/form-data;\s*boundary=(?:\"([^\"]+)\"|([^;\s]+))", content_type, re.I)
    if not match:
        raise UploadFailure("INVALID_REQUEST")
    boundary = (match.group(1) or match.group(2) or "").encode("ascii", "strict")
    if not BOUNDARY.fullmatch(boundary):
        raise UploadFailure("INVALID_REQUEST")
    marker = b"--" + boundary
    if not body.startswith(marker + b"\r\n") or not body.endswith(b"\r\n" + marker + b"--\r\n"):
        raise UploadFailure("INVALID_REQUEST")
    content = body[len(marker) + 2:-(len(marker) + 6)]
    if b"\r\n" + marker in content:
        raise UploadFailure("INVALID_REQUEST")
    header_bytes, separator, data = content.partition(b"\r\n\r\n")
    if not separator or len(header_bytes) > 2048:
        raise UploadFailure("INVALID_REQUEST")
    try:
        headers = header_bytes.decode("utf-8", "strict").split("\r\n")
    except UnicodeDecodeError:
        raise UploadFailure("INVALID_REQUEST") from None
    if len(headers) > 3 or any("\r" in line or "\n" in line for line in headers):
        raise UploadFailure("INVALID_REQUEST")
    disposition = next((line for line in headers if line.lower().startswith("content-disposition:")), "")
    file_match = re.fullmatch(r'Content-Disposition:\s*form-data;\s*name="file";\s*filename="([^"\\]*)"', disposition, re.I)
    paste_match = re.fullmatch(r'Content-Disposition:\s*form-data;\s*name="paste";\s*filename="pasted.txt"', disposition, re.I)
    if file_match:
        name, pasted = file_match.group(1), False
    elif paste_match:
        name, pasted = "pasted.txt", True
    else:
        raise UploadFailure("INVALID_REQUEST")
    if (not name or len(name) > 255 or any(ord(char) < 32 for char in name) or
            "/" in name or "\\" in name or not data or len(data) > MAX_SOURCE):
        raise UploadFailure("INPUT_TOO_LARGE" if len(data) > MAX_SOURCE else "INVALID_REQUEST")
    return data, name, pasted


def _rss_kb(pid: int) -> int | None:
    try:
        result = subprocess.run(("/bin/ps", "-o", "rss=", "-p", str(pid)), capture_output=True,
                                timeout=0.5, check=False, text=True)
        return int(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip().isdigit() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


async def run_extract(data: bytes, name: str, pasted: bool, files: OperationFiles) -> ExtractResult:
    if files.path is None:
        raise UploadFailure("EXTRACT_FAILED")
    workspace = files.path
    (workspace / "source.bin").write_bytes(data)
    (workspace / "extract-input.json").write_text(json.dumps({"name": name, "pasted": pasted}, ensure_ascii=False), encoding="utf-8")
    process = files.spawn(Path(sys.executable), (str(WORKER),), capture=False)
    try:
        while process.poll() is None:
            rss = await asyncio.to_thread(_rss_kb, process.pid)
            if rss is None and process.poll() is None:
                files.stop_worker()
                raise UploadFailure("EXTRACT_MONITOR_UNAVAILABLE")
            if rss is not None and rss > MAX_RSS_KB:
                files.stop_worker()
                raise UploadFailure("EXTRACT_MEMORY_LIMIT")
            await asyncio.sleep(0.05)
        code = process.returncode
    finally:
        files.stop_worker()
    if code:
        try:
            status = json.loads((workspace / "extract-status.json").read_text(encoding="utf-8"))
            error = status["code"]
        except (OSError, ValueError, KeyError, TypeError):
            error = "EXTRACT_FAILED"
        raise UploadFailure(error if error in ALLOWED_ERRORS else "EXTRACT_FAILED")
    try:
        output = workspace / "extract-output.json"
        if output.stat().st_size > MAX_RESULT:
            raise UploadFailure("EXTRACT_TEXT_LIMIT")
        return ExtractResult.model_validate_json(output.read_bytes())
    except (OSError, ValueError):
        raise UploadFailure("EXTRACT_FAILED") from None
