from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SPRITE = ROOT / "design/future-editor/visual/icons.svg"
TOKENS = ROOT / "design/future-editor/visual/tokens.css"
COLORS = {"accent": "#58684c", "paper": "#fffefa", "desk": "#f2f0ea",
          "ink": "#30372e", "line": "#dfe2d6", "wash": "#e8eddf"}
MATCH = re.search(r'<symbol id="i-fold"[^>]*><path d="([^"]+)"', SPRITE.read_text())
if MATCH is None:
    raise SystemExit("FoldCV mark was not found")
PATH = MATCH.group(1)


def svg(width: int, height: int, content: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">{content}</svg>\n')


def mark(x: float, y: float, scale: float, color: str, stroke: float = 1.3) -> str:
    return (f'<g transform="translate({x} {y}) scale({scale})"><path d="{PATH}" '
            f'fill="none" stroke="{color}" stroke-width="{stroke}" '
            'stroke-linecap="round" stroke-linejoin="round"/></g>')


def wordmark(x: int, y: int, scale: float = 1, inverse: bool = False) -> str:
    ink = COLORS["paper"] if inverse else COLORS["ink"]
    accent = COLORS["paper"] if inverse else COLORS["accent"]
    return (f'<g transform="translate({x} {y}) scale({scale})">'
            + mark(0, 3, 2.5, accent)
            + f'<text x="77" y="51" fill="{ink}" font-family="Helvetica Neue,Arial,sans-serif" '
              'font-size="53" font-weight="650" letter-spacing="-2.65">FoldCV'
              f'<tspan fill="{accent}">.</tspan></text></g>')


def render(source: Path, target: Path, width: int | None = None) -> None:
    command = ["rsvg-convert", str(source), "-o", str(target)]
    if width is not None:
        command.extend(["-w", str(width)])
    subprocess.run(command, check=True)


def write_source(name: str, content: str, png_width: int | None = None) -> None:
    source = HERE / "source" / f"{name}.svg"
    source.write_text(content)
    render(source, HERE / "png" / f"{name}.png", png_width)


for folder in ("source", "png", "macos/FoldCV.iconset", "web"):
    (HERE / folder).mkdir(parents=True, exist_ok=True)

write_source("app-icon", svg(1024, 1024,
    '<rect x="100" y="100" width="824" height="824" rx="184" fill="#58684c"/>'
    + mark(176, 176, 28, COLORS["paper"])))
write_source("mark", svg(240, 240, mark(0, 0, 10, COLORS["accent"])))
write_source("mark-inverse", svg(240, 240, mark(0, 0, 10, COLORS["paper"])))
write_source("wordmark", svg(600, 136, wordmark(30, 20, 1.5)), 1200)
write_source("wordmark-inverse", svg(600, 136, wordmark(30, 20, 1.5, True)), 1200)

write_source("empty-state", svg(480, 320,
    '<ellipse cx="240" cy="273" rx="110" ry="10" fill="#e8eddf"/>'
    '<g transform="rotate(-9 240 160)"><rect x="153" y="55" width="154" height="200" '
    'rx="7" fill="#f2f0ea" stroke="#dfe2d6" stroke-width="2"/></g>'
    '<rect x="164" y="46" width="154" height="206" rx="7" fill="#fffefa" '
    'stroke="#dfe2d6" stroke-width="2"/>'
    + mark(180, 72, 5, COLORS["accent"], 1.05)
    + '<path d="M201 215h79m-79 13h48" fill="none" stroke="#b5bda9" '
      'stroke-width="4" stroke-linecap="round"/>'), 960)

write_source("dmg-background", svg(660, 440,
    '<rect width="660" height="440" fill="#f2f0ea"/>'
    + wordmark(32, 23, 0.85)
    + '<path d="M32 100h596" stroke="#dfe2d6"/>'
      '<path d="M293 232h74m-13-13 13 13-13 13" fill="none" stroke="#58684c" '
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
      '<text x="330" y="359" text-anchor="middle" font-family="Helvetica Neue,Arial,sans-serif" '
      'font-size="15" fill="#58684c">Перетащите FoldCV в «Программы»</text>'))
render(HERE / "source/dmg-background.svg", HERE / "macos/dmg-background@2x.png", 1320)

for size in (16, 32, 128, 256, 512):
    for density in (1, 2):
        suffix = "@2x" if density == 2 else ""
        render(HERE / "source/app-icon.svg",
               HERE / f"macos/FoldCV.iconset/icon_{size}x{size}{suffix}.png", size * density)
subprocess.run(["iconutil", "-c", "icns", str(HERE / "macos/FoldCV.iconset"),
                "-o", str(HERE / "macos/FoldCV.icns")], check=True)

favicon = HERE / "web/favicon.svg"
favicon.write_text(svg(32, 32,
    '<rect width="32" height="32" rx="7" fill="#58684c"/>'
    + mark(4, 4, 1, COLORS["paper"], 1.7)))
frames = []
for size in (16, 32, 48):
    target = HERE / f"web/favicon-{size}.png"
    render(favicon, target, size)
    frames.append((size, target.read_bytes()))
offset = 6 + 16 * len(frames)
entries = []
for size, data in frames:
    entries.append(struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
(HERE / "web/favicon.ico").write_bytes(struct.pack("<HHH", 0, 1, len(frames))
    + b"".join(entries) + b"".join(data for _, data in frames))


def embedded(name: str, x: int, y: int, width: int, height: int) -> str:
    data = base64.b64encode((HERE / "png" / f"{name}.png").read_bytes()).decode()
    return (f'<image x="{x}" y="{y}" width="{width}" height="{height}" '
            f'href="data:image/png;base64,{data}"/>')


def label(x: int, y: int, text: str, size: int = 14) -> str:
    return (f'<text x="{x}" y="{y}" font-family="Helvetica Neue,Arial,sans-serif" '
            f'font-size="{size}" fill="#767c6f">{text}</text>')


preview = svg(1440, 1020,
    '<rect width="1440" height="1020" fill="#f2f0ea"/>'
    + label(48, 52, "FoldCV / Desktop assets", 22)
    + '<rect x="32" y="82" width="650" height="430" rx="16" fill="#fffefa"/>'
    + label(56, 116, "Application icon")
    + embedded("app-icon", 40, 132, 320, 320)
    + embedded("app-icon", 386, 152, 128, 128)
    + embedded("app-icon", 546, 190, 64, 64)
    + embedded("app-icon", 403, 327, 32, 32)
    + embedded("app-icon", 470, 335, 16, 16)
    + label(386, 307, "128 / 64 px") + label(386, 395, "32 / 16 px")
    + '<rect x="706" y="82" width="702" height="210" rx="16" fill="#fffefa"/>'
    + label(732, 116, "Existing mark and wordmark")
    + embedded("wordmark", 730, 137, 600, 136)
    + '<rect x="706" y="316" width="702" height="196" rx="16" fill="#58684c"/>'
    + embedded("wordmark-inverse", 730, 346, 600, 136)
    + '<rect x="32" y="536" width="650" height="452" rx="16" fill="#fffefa"/>'
    + label(56, 573, "Empty state / transparent PNG + SVG")
    + embedded("empty-state", 117, 616, 480, 320)
    + '<rect x="706" y="536" width="702" height="452" rx="16" fill="#fffefa"/>'
    + label(732, 573, "DMG background / native file icons added by packaging")
    + embedded("dmg-background", 727, 590, 660, 396))
(HERE / "preview.svg").write_text(preview)
render(HERE / "preview.svg", HERE / "preview.png")
(HERE / "preview.svg").unlink()

manifest = {
    "name": "FoldCV desktop assets v1",
    "status": "proposed; not connected to the application",
    "source_mark": {"path": str(SPRITE.relative_to(ROOT)), "symbol": "i-fold", "geometry": PATH},
    "source_palette": str(TOKENS.relative_to(ROOT)),
    "palette": COLORS,
    "font": "System sans-serif; SVG exports use Helvetica Neue with Arial fallback",
    "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (SPRITE, TOKENS)},
    "files": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(HERE.rglob("*")) if p.is_file()
              and p.suffix in (".svg", ".png", ".icns", ".ico")},
}
(HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
with zipfile.ZipFile(HERE / "FoldCV-desktop-assets-v1.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and path.suffix != ".zip":
            archive.write(path, f"FoldCV-desktop-assets-v1/{path.relative_to(HERE)}")
print(f"Exported {len(manifest['files'])} assets to {HERE}")
