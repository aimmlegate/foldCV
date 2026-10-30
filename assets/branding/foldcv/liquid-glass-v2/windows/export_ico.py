"""Build FoldCV.ico for the Windows app from the native olive render that the macOS icns uses.

Run with any Python that has Pillow: `python export_ico.py`. The macOS canvas keeps 100 px transparent margins on
1024 px; Windows icons fill their canvas, so the 824 px icon square is cropped out before scaling.
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "macos/FoldCV-native-olive.iconset/icon_512x512@2x.png"
SIZES = (256, 128, 64, 48, 32, 24, 16)

with Image.open(SOURCE) as source:
    icon = source.convert("RGBA").crop((100, 100, 924, 924))
frames = [icon.resize((size, size), Image.Resampling.LANCZOS) for size in SIZES]
frames[0].save(HERE / "FoldCV.ico", format="ICO", sizes=[(size, size) for size in SIZES], append_images=frames[1:])
