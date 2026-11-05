"""The pinned LibreOffice of `tools/install-local-renderer.sh`, for slow tests that convert a DOCX export to PDF.

The pins and the conversion came from the retired legacy render worker: the converter binary hash and version, and
the two app-local Source Sans Pro faces the converter must find.
"""

import hashlib
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOFFICE = ROOT / ".tools/LibreOffice.app/Contents/MacOS/soffice"
APP_FONTS = ROOT / ".tools/LibreOffice.app/Contents/Resources/fonts/truetype"
CONVERTER_SHA256 = "c772a72b6f07e953a34956cebedf5d037b1ea841fad29014b1ee6355775c1d1e"
CONVERTER_VERSION = "26.2.6.3"
FONTS = {"SourceSansPro-Bold.ttf": "8d869f2aeac0220984a430120af819fbcb12a88e8ea4ad72aae4c5f6d6a2b985",
         "SourceSansPro-Regular.ttf": "c6f835b6a6d942b196e2607bf73a7b086407ae8dbdc928c23a2fb4893ec383f6"}


class ConverterUnavailable(Exception):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_converter():
    """The pinned converter and its fonts; ConverterUnavailable names what is missing."""
    if not SOFFICE.is_file():
        raise ConverterUnavailable("CONVERTER_UNAVAILABLE: run tools/install-local-renderer.sh")
    if sha256_file(SOFFICE) != CONVERTER_SHA256:
        raise ConverterUnavailable(f"CONVERTER_MISMATCH: install LibreOffice {CONVERTER_VERSION}")
    for name, expected in FONTS.items():
        installed = APP_FONTS / name
        if not installed.is_file():
            raise ConverterUnavailable("FONT_UNAVAILABLE: " + name)
        if sha256_file(installed) != expected:
            raise ConverterUnavailable("FONT_MISMATCH: " + name)


def clean_environment(workspace):
    locations = {name: workspace / name for name in ("home", "tmp", "cache", "data", "state")}
    for path in locations.values():
        path.mkdir(mode=0o700, exist_ok=True)
    return {"PATH": os.defpath, "HOME": str(locations["home"]), "TMPDIR": str(locations["tmp"]),
            "XDG_CACHE_HOME": str(locations["cache"]), "XDG_DATA_HOME": str(locations["data"]),
            "XDG_STATE_HOME": str(locations["state"]), "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
            "SAL_USE_VCLPLUGIN": "osx"}


def convert(docx_path, workspace):
    """The PDF LibreOffice makes of `docx_path` in a private profile under `workspace`."""
    require_converter()
    output = workspace / "pdf-output"
    output.mkdir(mode=0o700, exist_ok=True)
    profile = (workspace / "lo-profile").as_uri()
    args = [str(SOFFICE), f"-env:UserInstallation={profile}", "--headless",
            "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(output), str(docx_path)]
    result = subprocess.run(args, cwd=workspace, env=clean_environment(workspace), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    converted = output / (Path(docx_path).stem + ".pdf")
    assert result.returncode == 0 and converted.is_file(), "CONVERTER_FAILED"
    return converted


def normalize(value):
    return " ".join(value.split())


def words_in_order(haystack, value):
    position = 0
    for word in value.split():
        found = haystack.find(word, position)
        if found < 0:
            return False
        position = found + len(word)
    return True
