from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from packages.resume_core.rendering.rich_template import MANIFEST_PATH, PACKAGE_SHA256, ROOT, require_rich_template
from packages.resume_core.rendering.template import PACKAGE_SHA256 as LEGACY_HASH, RenderFailure


def test_rich_template_matches_all_pages_fonts_and_fixed_roles():
    package = require_rich_template()
    spec = package.specification
    assert package.manifest.id == "foldcv-reference" and PACKAGE_SHA256 != LEGACY_HASH
    assert spec["page"]["width"] == 596 and spec["page"]["height"] == 842
    assert spec["regions"]["main"] == {"x": 160.76, "width": 420}
    assert spec["regions"]["sidebar"] == {"x": 26.5, "width": 118}
    assert spec["regions"]["gap"] == pytest.approx(16.26)
    assert spec["focus"]["referenceLogoEntries"] == 8 and spec["focus"]["referenceTextOnlyEntries"] == 2
    assert spec["focus"]["entryCountLimit"] is None
    assert {font["weight"] for font in spec["fonts"]} == {300, 400, 600, 700, 900}
    assert all(font["fsType"] == 0 and font["embedFullFace"] for font in spec["fonts"])
    assert {font["face"]: (font["wordFamily"], font["wordBold"]) for font in spec["fonts"]} == {
        "regular": ("Source Sans Pro", False), "bold": ("Source Sans Pro", True),
        "light": ("Source Sans Pro Light", False), "semibold": ("Source Sans Pro Semibold", False),
        "black": ("Source Sans Pro Black", False),
    }
    measurements = json.loads((ROOT / "templates/foldcv-reference/reference-measurements.json").read_text())
    assert [len(page["drawings"]) for page in measurements["pages"]] == [2, 0, 3]
    assert [len(page["images"]) for page in measurements["pages"]] == [9, 0, 0]
    assert {image["role"] for image in spec["assetRoles"]["referenceImages"]} == {"brand", "technology_logo"}
    assert all(len(image["matches"]) == 1 for image in measurements["pages"][0]["images"])
    assert spec["helvetica"]["redistributed"] is False
    assert not spec["fontEmbedding"]["installOsFonts"] and spec["fontEmbedding"]["manualWordRequired"]


def copy_package(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    for relative in (*manifest["assets"], "templates/foldcv-reference/manifest.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path / "templates/foldcv-reference/manifest.json"


def test_rich_template_detects_changed_geometry_and_owned_asset_symlinks(tmp_path):
    manifest = copy_package(tmp_path)
    spec_path = tmp_path / "templates/foldcv-reference/spec.json"
    raw = spec_path.read_bytes()
    spec_path.write_bytes(raw + b" ")
    with pytest.raises(RenderFailure, match="RICH_TEMPLATE_ASSET_MISMATCH"):
        require_rich_template(tmp_path, manifest)
    spec_path.write_bytes(raw)
    font = tmp_path / "skills/format-resume/assets/fonts/SourceSansPro-Semibold.ttf"
    font.unlink()
    font.symlink_to(ROOT / "skills/format-resume/assets/fonts/SourceSansPro-Semibold.ttf")
    with pytest.raises(RenderFailure, match="RICH_TEMPLATE_UNSAFE_ASSET"):
        require_rich_template(tmp_path, manifest)


def test_rich_template_rejects_legacy_identity_and_has_no_converter_dependency():
    package = require_rich_template()
    assert not json.loads(MANIFEST_PATH.read_text())["runtimeConverterRequired"]
    with pytest.raises(RenderFailure, match="RICH_TEMPLATE_MISMATCH"):
        require_rich_template(manifest_path=ROOT / "templates/generic/manifest.json")
    assert sha256(MANIFEST_PATH.read_bytes()).hexdigest() == package.manifest.package_sha256
