"""Measure fixed synthetic extraction and real local rendering."""

from __future__ import annotations

import asyncio
from io import BytesIO
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from packages.resume_core.extraction.parser import extract
from packages.resume_core.rendering.models import RenderDocument, RenderIdentity, RenderRequest, snapshot_digest
from packages.resume_core.rendering.template import PACKAGE_SHA256, renderer_sha256, require_template
from resume_api.lifecycle import OperationFiles
from resume_api.launcher import trusted_temp_root
from resume_api.rendering import DocumentRenderer


def percentile(samples: list[float], percent: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int((len(ordered) * percent + 99) // 100) - 1))
    return round(ordered[index], 2)


def request_for(stem: str) -> RenderRequest:
    data = json.loads((ROOT / "spikes/render/fixtures" / f"{stem}.json").read_text(encoding="utf-8"))
    document = RenderDocument.model_validate(data, by_name=True)
    identity = RenderIdentity.model_construct(id=stem, project_revision=1, snapshot_sha256="0" * 64,
                                              template_id="generic", template_version="1.0.0",
                                              template_package_sha256=PACKAGE_SHA256, renderer_version="1.0.0",
                                              renderer_sha256=renderer_sha256())
    request = RenderRequest.model_construct(base_revision=1, snapshot=identity, document=document)
    request.snapshot.snapshot_sha256 = snapshot_digest(request)
    return RenderRequest.model_validate_json(request.model_dump_json(by_alias=True))


async def main() -> None:
    require_template()
    extraction = {}
    for name in ("mixed-columns.pdf", "rich.docx", "unicode.txt"):
        data = (ROOT / "tests/fixtures/synthetic/import" / name).read_bytes()
        samples = []
        for _ in range(9):
            start = time.perf_counter()
            result = extract(data, name)
            samples.append((time.perf_counter() - start) * 1000)
            assert result.byte_length == len(data)
        extraction[name] = {"bytes": len(data), "units": len(result.units),
                            "samplesMs": [round(value, 2) for value in samples],
                            "medianMs": round(statistics.median(samples), 2),
                            "p95Ms": percentile(samples, 95)}
    renders = {}
    temp_parent = trusted_temp_root()
    temp_parent.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="foldcv-T17-perf-", dir=temp_parent) as directory:
        root = Path(directory)
        for stem in ("short", "long-main", "long-sidebar"):
            request = request_for(stem)
            samples = []
            pages = None
            for index in range(4):
                files = OperationFiles(root / f"{stem}-{index}")
                start = time.perf_counter()
                with files.open():
                    output = await DocumentRenderer().render(request, files)
                samples.append((time.perf_counter() - start) * 1000)
                with ZipFile(BytesIO(output)) as archive:
                    meta = json.loads(archive.read("render.json"))
                    pages = meta["pageCount"]
                    assert archive.read("resume.pdf").startswith(b"%PDF")
                    assert archive.read("resume.docx").startswith(b"PK")
            renders[stem] = {"pages": pages, "firstMs": round(samples[0], 2),
                             "warmSamplesMs": [round(value, 2) for value in samples[1:]],
                             "warmP95Ms": percentile(samples[1:], 95)}
    output = {"scope": "fixed synthetic local processing; no inference", "host": platform.platform(),
              "python": platform.python_version(), "extraction": extraction, "render": renders,
              "renderFirstMeaning": "first run in this sequence, with OS caches already in use; not fresh-machine cold",
              "sampleCounts": {"extractionPerFixture": 9, "renderPerFixture": 4}}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
