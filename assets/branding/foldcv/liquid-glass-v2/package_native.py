from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


HERE = Path(__file__).resolve().parent
APPEARANCES = ("Default", "Dark", "ClearLight", "ClearDark", "TintedLight", "TintedDark")


def source_image(variant: str, appearance: str = "Default") -> Path:
    return (HERE / "macos" / f"FoldCV-{variant}-glass Exports"
            / f"FoldCV-{variant}-glass-iOS-{appearance}-1024@1x.png")


def image(path: Path, x: int, y: int, size: int) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return (f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
            f'href="data:image/png;base64,{data}"/>')


def text(x: int, y: int, value: str, size: int = 16, color: str = "#767c6f") -> str:
    return (f'<text x="{x}" y="{y}" font-family="Helvetica Neue,Arial,sans-serif" '
            f'font-size="{size}" fill="{color}">{value}</text>')


def svg(width: int, height: int, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">{body}</svg>\n')


for variant in ("olive", "frosted"):
    for appearance in APPEARANCES:
        if not source_image(variant, appearance).exists():
            raise SystemExit(f"Missing Composer export: {variant}/{appearance}")
    master = HERE / "source" / f"native-{variant}-fallback.svg"
    master.write_text(svg(1024, 1024, image(source_image(variant), 100, 100, 824)))
    subprocess.run(["rsvg-convert", str(master), "-o", str(HERE / "png" / f"native-{variant}-fallback.png")], check=True)
    iconset = HERE / "macos" / f"FoldCV-native-{variant}.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for density in (1, 2):
            suffix = "@2x" if density == 2 else ""
            subprocess.run(["rsvg-convert", str(master), "-w", str(size * density), "-o",
                            str(iconset / f"icon_{size}x{size}{suffix}.png")], check=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o",
                    str(HERE / "macos" / f"FoldCV-native-{variant}.icns")], check=True)

preview = '<rect width="1440" height="1100" fill="#f2f0ea"/>'
preview += text(48, 52, "FoldCV / Native Liquid Glass", 28, "#30372e")
preview += text(48, 83, "Rendered in Apple Icon Composer 27.0 / existing FoldCV geometry", 16)
cards = (("Current flat", HERE.parent / "desktop-v1/png/app-icon.png"),
         ("Olive / native", HERE / "png/native-olive-fallback.png"),
         ("Frosted / native", HERE / "png/native-frosted-fallback.png"))
for index, (title, path) in enumerate(cards):
    x = 32 + index * 472
    preview += f'<rect x="{x}" y="116" width="432" height="430" rx="20" fill="#fffefa"/>'
    preview += text(x + 26, 155, title, 19, "#30372e")
    preview += image(path, x + 16, 151, 400)
for index, variant in enumerate(("olive", "frosted")):
    y = 570 + index * 248
    preview += f'<rect x="32" y="{y}" width="1376" height="224" rx="20" fill="#252d22"/>'
    preview += text(58, y + 33, f"{variant.capitalize()} / system appearances", 16, "#c6d0bb")
    for column, appearance in enumerate(APPEARANCES):
        x = 75 + column * 220
        preview += image(source_image(variant, appearance), x + 13, y + 55, 122)
        preview += text(x, y + 202, appearance, 14, "#c6d0bb")
preview += text(48, 1080, "Editable .icon sources + native PNG appearances + static .icns fallback", 15)
temporary = HERE / "native-preview.svg"
temporary.write_text(svg(1440, 1100, preview))
subprocess.run(["rsvg-convert", str(temporary), "-o", str(HERE / "native-preview.png")], check=True)
temporary.unlink()

manifest_path = HERE / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["status"] = "native sources and appearance renders verified in Icon Composer; not connected to the application"
manifest["native"] = {
    "tool": "Apple Icon Composer 27.0",
    "appearance_exports": list(APPEARANCES),
    "platform": "shared square (iOS, macOS); Composer names shared-square PNGs iOS",
    "sources": [f"macos/FoldCV-{variant}-glass.icon" for variant in ("olive", "frosted")],
    "fallback": "macos/FoldCV-native-*.icns uses the Apple-rendered Default appearance with macOS transparent margins",
    "acceptance": "Both sources opened and all six appearances exported. Packaged Electron integration and Dock appearance are not tested.",
}
manifest["files"] = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(HERE.rglob("*")) if p.is_file() and p != manifest_path
                     and p.suffix in (".svg", ".png", ".icns", ".json")}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
with zipfile.ZipFile(HERE / "FoldCV-liquid-glass-v2.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and path.suffix != ".zip":
            archive.write(path, f"FoldCV-liquid-glass-v2/{path.relative_to(HERE)}")
print("Packaged native icon sources, 12 appearance renders and ICNS fallbacks.")
