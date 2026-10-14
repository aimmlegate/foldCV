"""Measure an explicit design PDF without publishing its personal text."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/format-resume/assets"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def font_inventory() -> list[dict]:
    result = []
    for path in sorted((ASSETS / "fonts").glob("SourceSansPro-*.ttf")):
        with TTFont(path) as font:
            names = font["name"]
            result.append({"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes()),
                           "size": path.stat().st_size, "family": names.getDebugName(1),
                           "style": names.getDebugName(2), "fullName": names.getDebugName(4),
                           "postscriptName": names.getDebugName(6), "preferredFamily": names.getDebugName(16),
                           "preferredStyle": names.getDebugName(17), "weight": font["OS/2"].usWeightClass,
                           "fsType": font["OS/2"].fsType, "glyphCount": len(font.getBestCmap())})
    return result


def rgb_hash(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    white = Image.new("RGBA", rgba.size, "white")
    return digest(Image.alpha_composite(white, rgba).convert("RGB").tobytes())


def decoded_image(document: pymupdf.Document, xref: int, smask: int) -> Image.Image:
    pix = pymupdf.Pixmap(document, xref)
    image = Image.frombytes("RGBA" if pix.alpha else "RGB", (pix.width, pix.height), pix.samples)
    if smask:
        mask = pymupdf.Pixmap(document, smask)
        # Combining Pixmaps premultiplies color; Pillow expects straight alpha.
        image.putalpha(Image.frombytes("L", (mask.width, mask.height), mask.samples))
    return image


def measure(source: Path, expected_sha: str, output: Path) -> dict:
    raw = source.read_bytes()
    if digest(raw) != expected_sha:
        raise ValueError("reference PDF hash mismatch")
    if output.is_symlink():
        raise ValueError("unsafe private output")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    if output.stat().st_uid != os.getuid():
        raise ValueError("private output ownership mismatch")
    (output / "reference.pdf").write_bytes(raw)
    (output / "reference.pdf").chmod(0o600)
    fonts = font_inventory()
    by_pdf_name = {item["postscriptName"]: ROOT / item["path"] for item in fonts}
    images = []
    for path in sorted(ASSETS.rglob("*.png")):
        with Image.open(path) as image:
            images.append((str(path.relative_to(ROOT)), image.size, rgb_hash(image)))
    pages = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        for page in document:
            spans = [span for block in page.get_text("dict")["blocks"] if block["type"] == 0
                     for line in block["lines"] for span in line["spans"]]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            draw = ImageDraw.Draw(image)
            page_drawings = page.get_drawings()
            safe_spans = []
            for index, span in enumerate(spans):
                bbox = span["bbox"]
                font_name = re.sub(r"^[A-Z]{6}\+", "", span["font"])
                safe_spans.append({"id": f"p{page.number + 1}-s{index + 1}", "bbox": list(bbox),
                                   "origin": list(span["origin"]), "font": font_name,
                                   "size": span["size"], "color": span["color"], "flags": span["flags"],
                                   "characters": len(span["text"]), "ascender": span["ascender"], "descender": span["descender"]})
                if span["text"].strip() in {"•", "·", "-", "–"}:
                    continue
                rect = tuple(round(value * 2) for value in bbox)
                background = (255, 255, 255)
                for graphic in page_drawings:
                    if graphic["fill"] is not None and graphic["rect"].contains(pymupdf.Rect(bbox)):
                        background = tuple(round(channel * 255) for channel in graphic["fill"])
                draw.rectangle(rect, fill=background)
                font_path = by_pdf_name.get(font_name, Path("/System/Library/Fonts/Helvetica.ttc"))
                font = ImageFont.truetype(str(font_path), max(1, round(span["size"] * 2)))
                color = tuple((span["color"] >> shift) & 255 for shift in (16, 8, 0))
                anonymous = []
                for char in span["text"]:
                    if char.isspace() or not char.isalnum():
                        anonymous.append(char)
                    elif char.isdigit():
                        anonymous.append("0")
                    else:
                        alphabet = "NMWIOHX" if char.isupper() else "nmwiox"
                        anonymous.append(min(alphabet, key=lambda value: abs(font.getlength(value) - font.getlength(char))))
                draw.text(tuple(round(value * 2) for value in span["origin"]), "".join(anonymous),
                          font=font, fill=color, anchor="ls")
            page_images = []
            for item in page.get_images(full=True):
                xref, smask = item[:2]
                decoded = decoded_image(document, xref, smask)
                matches = [path for path, size, checksum in images if size == decoded.size and checksum == rgb_hash(decoded)]
                page_images.append({"xref": xref, "width": decoded.width, "height": decoded.height,
                                    "rgbSha256": rgb_hash(decoded), "matches": matches,
                                    "placements": [list(rect) for rect in page.get_image_rects(xref)]})
            drawings = []
            for index, drawing in enumerate(page_drawings):
                drawings.append({"id": f"p{page.number + 1}-drawing-{index + 1}", "type": drawing["type"],
                                 "rect": list(drawing["rect"]), "fill": drawing["fill"],
                                 "color": drawing["color"], "width": drawing["width"],
                                 "fillOpacity": drawing["fill_opacity"], "strokeOpacity": drawing["stroke_opacity"],
                                 "items": [[item[0], *[list(value) if isinstance(value, (pymupdf.Point, pymupdf.Rect)) else value
                                                       for value in item[1:]]] for item in drawing["items"]]})
            image_path = output / f"page-{page.number + 1}-anonymous.png"
            image.save(image_path)
            image_path.chmod(0o600)
            pages.append({"page": page.number + 1, "width": page.rect.width, "height": page.rect.height,
                          "spans": safe_spans, "drawings": drawings, "images": page_images,
                          "anonymousFrame": str(image_path)})
    word_path = Path("/Applications/Microsoft Word.app/Contents/Info.plist")
    word = plistlib.loads(word_path.read_bytes()) if word_path.is_file() else {}
    result = {"sourceSha256": expected_sha, "sourceBytes": len(raw), "pages": pages, "fonts": fonts,
              "fontLicenseSha256": digest((ASSETS / "fonts/LICENSE.txt").read_bytes()),
              "word": {"version": word.get("CFBundleShortVersionString"), "build": word.get("CFBundleVersion")},
              "helvetica": {"path": "/System/Library/Fonts/Helvetica.ttc", "exists": Path("/System/Library/Fonts/Helvetica.ttc").is_file(), "redistributed": False}}
    target = output / "measurements.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    target.chmod(0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.source, args.sha256, args.private_output)
    print(json.dumps({"pages": len(result["pages"]), "fonts": len(result["fonts"]), "word": result["word"]}))


if __name__ == "__main__":
    main()
