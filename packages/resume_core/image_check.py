"""The images a user adds (D187): the cropped photo of a résumé and an own Focus icon. The client crops and scales;
Python checks the result again before it stores it. A stored image holds no EXIF, XMP, text or other metadata."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

PHOTO_PIXELS = 800
PHOTO_BYTES = 3 * 1024 * 1024
ICON_PIXELS = 256
ICON_BYTES = 1024 * 1024
# Pillow's info keys that are no metadata of a person or a device: the colour profile and the pixel density.
HARMLESS = frozenset({'dpi', 'jfif', 'jfif_version', 'jfif_unit', 'jfif_density', 'icc_profile', 'gamma', 'srgb',
                      'transparency', 'aspect', 'progressive', 'progression', 'adobe', 'adobe_transform'})


@dataclass(frozen=True)
class CheckedImage:
    data: bytes
    mime_type: str
    width: int
    height: int


def check_image(data, kind):
    """The image if it is a real, still, square PNG or JPEG of the kind's size and holds no metadata; else ValueError
    with a public code. `kind`: 'photo' (JPEG or PNG, at most 800 px) or 'icon' (PNG, 256 px)."""
    from PIL import Image, UnidentifiedImageError
    limit, pixels, formats = (PHOTO_BYTES, PHOTO_PIXELS, {'JPEG', 'PNG'}) if kind == 'photo' else (ICON_BYTES, ICON_PIXELS, {'PNG'})
    if not data:
        raise ValueError('IMAGE_INVALID')
    if len(data) > limit:
        raise ValueError('IMAGE_TOO_LARGE')
    if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('IMAGE_INVALID')
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image.format not in formats:
                raise ValueError('IMAGE_INVALID')
            if getattr(image, 'is_animated', False) or getattr(image, 'n_frames', 1) > 1:
                raise ValueError('IMAGE_ANIMATED')
            if set(image.info) - HARMLESS or image.getexif():
                raise ValueError('IMAGE_METADATA')
            width, height = image.size
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError('IMAGE_INVALID') from None
    if image.format == 'JPEG' and _jpeg_metadata(data):
        raise ValueError('IMAGE_METADATA')
    if width != height or not 1 <= width <= pixels or (kind == 'icon' and width != ICON_PIXELS):
        raise ValueError('IMAGE_SIZE')
    return CheckedImage(data, 'image/jpeg' if image.format == 'JPEG' else 'image/png', width, height)


def _jpeg_metadata(data):
    """Whether a JPEG holds an EXIF, XMP, IPTC or comment segment; Pillow does not report each of them."""
    index = 2
    while index + 4 <= len(data) and data[index] == 0xFF:
        marker = data[index + 1]
        if marker in (0xD9, 0xDA):
            return False
        length = int.from_bytes(data[index + 2:index + 4], 'big')
        if marker in (0xE1, 0xED, 0xFE):
            return True
        index += 2 + length
    return False


def rounded(data, radius_ratio):
    """The photo as a PNG with rounded corners, for a DOCX: Word draws no clip of its own on a floating picture."""
    from PIL import Image, ImageDraw
    with Image.open(BytesIO(data)) as source:
        image = source.convert('RGBA')
    mask = Image.new('L', image.size, 0)
    radius = round(min(image.size) * radius_ratio)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.size[0] - 1, image.size[1] - 1], radius=radius, fill=255)
    image.putalpha(mask)
    raw = BytesIO()
    image.save(raw, format='PNG')
    return raw.getvalue()
