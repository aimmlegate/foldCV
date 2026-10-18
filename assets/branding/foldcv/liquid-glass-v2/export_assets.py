from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SPRITE = ROOT / "design/future-editor/visual/icons.svg"
MATCH = re.search(r'<symbol id="i-fold"[^>]*><path d="([^"]+)"', SPRITE.read_text())
if MATCH is None:
    raise SystemExit("FoldCV mark was not found")
PATH = MATCH.group(1)


def svg(width: int, height: int, content: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">{content}</svg>\n')


def mark(color: str, x: int = 176, y: int = 176, scale: float = 28,
         stroke: float = 1.3) -> str:
    return (f'<g transform="translate({x} {y}) scale({scale})">'
            f'<path d="{PATH}" fill="none" stroke="{color}" stroke-width="{stroke}" '
            'stroke-linecap="round" stroke-linejoin="round"/></g>')


def render(source: Path, target: Path, width: int | None = None) -> None:
    command = ["rsvg-convert", str(source), "-o", str(target)]
    if width is not None:
        command.extend(["-w", str(width)])
    subprocess.run(command, check=True)


def save(name: str, content: str, width: int | None = None) -> None:
    source = HERE / "source" / f"{name}.svg"
    source.write_text(content)
    render(source, HERE / "png" / f"{name}.png", width)


def glass_icon(clear: bool = False) -> str:
    colors = ("#f7f9f2", "#e0e7d7", "#c6d1ba") if clear else ("#8e9e7f", "#58684c", "#36472f")
    glyph = ("#70845f", "#4b603d", "#3c5031") if clear else ("#ffffff", "#f5f8ed", "#c8d8b7")
    definitions = f'''<defs>
      <linearGradient id="body" x1="0" y1="0" x2="0.8" y2="1">
        <stop stop-color="{colors[0]}"/><stop offset=".55" stop-color="{colors[1]}"/>
        <stop offset="1" stop-color="{colors[2]}"/></linearGradient>
      <radialGradient id="light" cx=".18" cy="0" r="1.05">
        <stop stop-color="#fffefa" stop-opacity=".4"/>
        <stop offset=".65" stop-color="#fffefa" stop-opacity="0"/></radialGradient>
      <radialGradient id="lowerLight" cx=".9" cy="1" r=".85">
        <stop stop-color="#dcebc6" stop-opacity=".3"/>
        <stop offset="1" stop-color="#dcebc6" stop-opacity="0"/></radialGradient>
      <linearGradient id="rim" x1="0" y1="0" x2=".8" y2="1">
        <stop stop-color="#ffffff" stop-opacity=".95"/>
        <stop offset=".4" stop-color="#fffefa" stop-opacity=".15"/>
        <stop offset=".76" stop-color="#fffefa" stop-opacity=".12"/>
        <stop offset="1" stop-color="#fffefa" stop-opacity=".65"/></linearGradient>
      <linearGradient id="glyph" x1="0" y1="0" x2=".7" y2="1">
        <stop stop-color="{glyph[0]}"/><stop offset=".52" stop-color="{glyph[1]}"/>
        <stop offset="1" stop-color="{glyph[2]}"/></linearGradient>
      <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
        <stop stop-color="#ffffff" stop-opacity=".18"/>
        <stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
      <filter id="shadow" x="-.3" y="-.3" width="1.6" height="1.8" color-interpolation-filters="sRGB">
        <feGaussianBlur stdDeviation="12"/></filter>
      <filter id="glyphShadow" x="-.3" y="-.3" width="1.6" height="1.8" color-interpolation-filters="sRGB">
        <feGaussianBlur stdDeviation="6"/></filter>
      <clipPath id="tile"><rect x="100" y="100" width="824" height="824" rx="184"/></clipPath>
    </defs>'''
    opacity = ".9" if clear else "1"
    return svg(1024, 1024, definitions
        + '<rect x="112" y="120" width="800" height="800" rx="177" '
          'fill="#27311d" opacity=".2" filter="url(#shadow)"/>'
        + f'<g opacity="{opacity}"><rect x="100" y="100" width="824" height="824" '
          'rx="184" fill="url(#body)"/>'
          '<rect x="100" y="100" width="824" height="824" rx="184" fill="url(#light)"/>'
          '<rect x="100" y="100" width="824" height="824" rx="184" fill="url(#lowerLight)"/></g>'
          '<g clip-path="url(#tile)"><path d="M90 90H934V350C690 480 345 475 90 625Z" '
          'fill="url(#sheen)"/></g>'
          '<rect x="104" y="104" width="816" height="816" rx="180" fill="none" '
          'stroke="url(#rim)" stroke-width="7"/>'
          '<rect x="114" y="114" width="796" height="796" rx="172" fill="none" '
          'stroke="#fffefa" stroke-opacity=".09" stroke-width="2"/>'
          '<g opacity=".24" filter="url(#glyphShadow)">'
        + mark("#293520", y=187) + '</g>' + mark("url(#glyph)"))


for folder in ("source", "png", "layers", "macos"):
    (HERE / folder).mkdir(parents=True, exist_ok=True)
save("app-icon-olive-glass", glass_icon())
save("app-icon-frosted-glass", glass_icon(True))

# Composer receives clean layers so the system can supply the material effects.
layer_sources = {
    "background-olive": svg(1024, 1024, '<rect width="1024" height="1024" fill="#58684c"/>'),
    "background-light": svg(1024, 1024, '<rect width="1024" height="1024" fill="#e8eddf"/>'),
    "mark-paper": svg(1024, 1024, mark("#fffefa")),
    "mark-olive": svg(1024, 1024, mark("#58684c")),
}
for name, content in layer_sources.items():
    source = HERE / "layers" / f"{name}.svg"
    source.write_text(content)
    render(source, HERE / "layers" / f"{name}.png")

save("empty-state-glass", svg(480, 320, '''<defs>
    <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="#ffffff" stop-opacity=".94"/>
      <stop offset="1" stop-color="#e8eddf" stop-opacity=".72"/></linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="#ffffff"/><stop offset="1" stop-color="#b7c3a9"/></linearGradient>
    <filter id="blur" x="-.5" y="-.5" width="2" height="2"><feGaussianBlur stdDeviation="8"/></filter>
    </defs>
    <ellipse cx="240" cy="268" rx="85" ry="8" fill="#58684c" opacity=".18" filter="url(#blur)"/>
    <g transform="rotate(-10 240 160)"><rect x="152" y="57" width="154" height="200"
      rx="14" fill="#a7b699" opacity=".35" stroke="#c4ceba"/></g>
    <rect x="163" y="48" width="154" height="206" rx="14" fill="url(#paper)" stroke="url(#edge)" stroke-width="2"/>
    <path d="M176 65h128" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>
    ''' + mark("#58684c", x=180, y=73, scale=5, stroke=1.05)
    + '<path d="M201 217h79m-79 13h48" fill="none" stroke="#a3b095" '
      'stroke-width="4" stroke-linecap="round"/>'), 960)

save("dmg-background-glass", svg(660, 440, '''<defs>
    <linearGradient id="desk" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="#f7f7f0"/><stop offset="1" stop-color="#e8eddf"/></linearGradient>
    <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
      <stop stop-color="#ffffff" stop-opacity=".7"/><stop offset="1" stop-color="#fffefa" stop-opacity=".32"/>
    </linearGradient></defs>
    <rect width="660" height="440" fill="url(#desk)"/>
    <rect x="30" y="114" width="600" height="200" rx="32" fill="url(#panel)" stroke="#fffefa"/>
    ''' + mark("#58684c", x=28, y=22, scale=2.1)
    + '<text x="94" y="64" font-family="Helvetica Neue,Arial,sans-serif" font-size="39" '
      'font-weight="650" letter-spacing="-1.95" fill="#30372e">FoldCV<tspan fill="#58684c">.</tspan></text>'
      '<path d="M293 232h74m-13-13 13 13-13 13" fill="none" stroke="#58684c" '
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
      '<text x="330" y="359" text-anchor="middle" font-family="Helvetica Neue,Arial,sans-serif" '
      'font-size="15" fill="#58684c">Перетащите FoldCV в «Программы»</text>'))
render(HERE / "source/dmg-background-glass.svg", HERE / "macos/dmg-background-glass@2x.png", 1320)

for name in ("olive", "frosted"):
    iconset = HERE / "macos" / f"FoldCV-{name}-glass.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for density in (1, 2):
            suffix = "@2x" if density == 2 else ""
            render(HERE / f"source/app-icon-{name}-glass.svg",
                   iconset / f"icon_{size}x{size}{suffix}.png", size * density)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o",
                    str(HERE / "macos" / f"FoldCV-{name}-glass.icns")], check=True)


def picture(path: Path, x: int, y: int, width: int, height: int) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return (f'<image x="{x}" y="{y}" width="{width}" height="{height}" '
            f'href="data:image/png;base64,{data}"/>')


def label(x: int, y: int, text: str, size: int = 16, color: str = "#767c6f") -> str:
    return (f'<text x="{x}" y="{y}" font-family="Helvetica Neue,Arial,sans-serif" '
            f'font-size="{size}" fill="{color}">{text}</text>')


variants = [("Current flat", HERE.parent / "desktop-v1/png/app-icon.png"),
            ("Olive glass", HERE / "png/app-icon-olive-glass.png"),
            ("Frosted glass", HERE / "png/app-icon-frosted-glass.png")]
preview = '<rect width="1440" height="1190" fill="#f2f0ea"/>'
preview += label(48, 53, "FoldCV / Liquid Glass study", 27, "#30372e")
preview += label(48, 83, "Existing mark. Same palette. Layered material.", 15)
for index, (name, path) in enumerate(variants):
    x = 32 + index * 472
    preview += f'<rect x="{x}" y="118" width="432" height="418" rx="20" fill="#fffefa"/>'
    preview += label(x + 26, 154, name, 18, "#30372e")
    preview += picture(path, x + 40, 166, 352, 352)
preview += '<rect x="32" y="558" width="1376" height="236" rx="20" fill="#252d22"/>'
preview += label(58, 592, "On a dark background / 128, 64, 32, 16 px", 15, "#c6d0bb")
for index, (_, path) in enumerate(variants):
    x = 57 + index * 472
    for offset, size in ((0, 128), (162, 64), (260, 32), (324, 16)):
        preview += picture(path, x + offset, 632 + (128 - size) // 2, size, size)
preview += '<rect x="32" y="818" width="432" height="340" rx="20" fill="#fffefa"/>'
preview += label(58, 855, "Supporting illustration", 16)
preview += picture(HERE / "png/empty-state-glass.png", 44, 873, 408, 272)
preview += '<rect x="504" y="818" width="904" height="340" rx="20" fill="#fffefa"/>'
preview += label(530, 855, "Installer background / native icons added during packaging", 16)
preview += picture(HERE / "png/dmg-background-glass.png", 717, 871, 420, 280)
preview_file = HERE / "preview.svg"
preview_file.write_text(svg(1440, 1190, preview))
render(preview_file, HERE / "preview.png")
preview_file.unlink()

manifest = {
    "name": "FoldCV Liquid Glass study v2",
    "status": "static study and clean Composer inputs; native .icon pending Apple license consent",
    "source_mark": {"path": str(SPRITE.relative_to(ROOT)), "symbol": "i-fold", "geometry": PATH,
                    "sha256": hashlib.sha256(SPRITE.read_bytes()).hexdigest()},
    "native_source": "layers/ contains unmasked backgrounds and transparent foregrounds without material effects",
    "static_exports": "png/ and macos/*.icns contain baked lighting for visual review and fallback use",
    "guidance": ["https://developer.apple.com/icon-composer/",
                 "https://developer.apple.com/design/human-interface-guidelines/app-icons/"],
    "files": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(HERE.rglob("*")) if p.is_file() and p.suffix in (".svg", ".png", ".icns")},
}
(HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
with zipfile.ZipFile(HERE / "FoldCV-liquid-glass-v2.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and path.suffix != ".zip":
            archive.write(path, f"FoldCV-liquid-glass-v2/{path.relative_to(HERE)}")
print(f"Exported {len(manifest['files'])} assets to {HERE}")
if all((HERE / "macos" / f"FoldCV-{name}-glass.icon").exists() for name in ("olive", "frosted")):
    subprocess.run([sys.executable, str(HERE / "package_native.py")], check=True)
