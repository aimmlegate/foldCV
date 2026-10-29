"""Smoke check of a built `FoldCV Helper.app` on synthetic data: its resources, the extract and fetch workers, and the
live service from the page to a DOCX export through the frozen render worker.

Usage: `<build python> tools/desktop/check_helper.py <FoldCV Helper.app>`. Everything runs in a temporary root.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from packages.resume_core.project_repository import ProjectRepository  # noqa: E402
from tests.templates.storage_fixtures import workspace  # noqa: E402

SOURCES = ROOT / "tests/fixtures/synthetic/import"


def run(helper: Path, mode: str, cwd: Path, data: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([str(helper), mode], cwd=cwd, input=data, capture_output=True, timeout=120,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), "LANG": "en_US.UTF-8"})


def call(origin: str, method: str, path: str, body=None, cookie: str | None = None):
    connection = http.client.HTTPConnection(origin.removeprefix("http://"), timeout=120)
    headers = {"Origin": origin, **({"Content-Type": "application/json"} if body is not None else {}),
               **({"Cookie": cookie} if cookie else {})}
    connection.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
    response = connection.getresponse()
    return response.status, response.getheader("Set-Cookie"), response.read()


def check_workers(helper: Path, work: Path) -> None:
    for name in ("rich.docx", "mixed-columns.pdf"):
        operation = work / ("extract-" + name)
        operation.mkdir()
        shutil.copyfile(SOURCES / name, operation / "source.bin")
        (operation / "extract-input.json").write_text(json.dumps({"name": name, "pasted": False}))
        result = run(helper, "extract", operation)
        assert result.returncode == 0, (name, result.stderr.decode()[-2000:])
        assert json.loads((operation / "extract-output.json").read_bytes()), name
    # Malformed input answers without the network; this loads the fetch worker's modules.
    fetch = run(helper, "public-fetch", work, b"{}")
    assert fetch.returncode == 0 and json.loads(fetch.stdout) == {"error": "AGENT_SOURCE_UNAVAILABLE"}, fetch.stderr


def check_service(helper: Path, root: Path) -> None:
    papers, sources = workspace()
    ProjectRepository(root).create(papers, blobs=[("sources", key, raw, hashlib.sha256(raw).hexdigest())
                                                  for key, raw in sources.items()])
    process = subprocess.Popen([str(helper), "serve", str(root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "HOME": str(root.parent)})
    assert process.stdin and process.stdout and process.stderr
    try:
        ready, _, _ = select.select([process.stdout], [], [], 120)
        line = process.stdout.readline() if ready else b""
        assert line, "service did not start: " + process.stderr.read1().decode()[-2000:]
        started = json.loads(line)
        origin = started["origin"]
        status, _, page = call(origin, "GET", "/")
        assert status == 200 and b'id="root"' in page, status
        status, cookie, _ = call(origin, "POST", "/v1/session/exchange", {"secret": started["secret"]})
        assert status == 200 and cookie, status
        cookie = cookie.split(";", 1)[0]
        assert call(origin, "GET", "/v1/settings/preferences", cookie=cookie)[0] == 200
        status, _, opened = call(origin, "POST", f"/v2/projects/{papers.project_id}/open", {}, cookie)
        assert status == 200, opened[:500]
        opened = json.loads(opened)
        status, _, content = call(origin, "POST", f"/v2/projects/{papers.project_id}/export", {"schemaVersion": 1,
            "editorToken": opened["editorToken"], "snapshot": opened["response"]["snapshot"]}, cookie)
        assert status == 200, content[:500]
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            assert "word/document.xml" in archive.namelist()
        process.stdin.close()
        assert process.wait(timeout=30) == 0, process.stderr.read().decode()[-2000:]
        assert started["secret"] not in process.stderr.read().decode()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def main(bundle: Path) -> None:
    helper = bundle / "Contents/MacOS/foldcv-helper"
    work = Path(tempfile.mkdtemp(prefix="foldcv-helper-check-", dir="/private/tmp"))
    try:
        result = run(helper, "check", work)
        assert result.returncode == 0, result.stderr.decode()[-2000:]
        resources = json.loads(result.stdout)
        check_workers(helper, work)
        root = work / "root"
        root.mkdir(mode=0o700)
        check_service(helper, root)
        print(json.dumps({"helper": "passed", **resources}))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
