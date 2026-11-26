"""The images a user adds (D187): the cropped photo of a résumé and an own Focus icon. The client crops and scales;
Python checks the result again before it stores it. An image whose metadata can name a person, a place, a device or a
time is refused; the structural EXIF a browser canvas writes (colour space, pixel size) is allowed and, like every
metadata segment, left out of the stored file, so a stored image holds no EXIF, XMP, text or other metadata."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

PHOTO_PIXELS = 800
PHOTO_BYTES = 3 * 1024 * 1024
ICON_PIXELS = 256
ICON_BYTES = 1024 * 1024
# Pillow's info keys that are no metadata of a person or a device: the colour profile and the pixel density; EXIF and a
# JPEG's resource block are checked tag by tag below.
HARMLESS = frozenset({'exif', 'photoshop', 'dpi', 'jfif', 'jfif_version', 'jfif_unit', 'jfif_density', 'icc_profile', 'gamma', 'srgb',
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
            if set(image.info) - HARMLESS or not _structural(image):
                raise ValueError('IMAGE_METADATA')
            width, height = image.size
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError('IMAGE_INVALID') from None
    if width != height or not 1 <= width <= pixels or (kind == 'icon' and width != ICON_PIXELS):
        raise ValueError('IMAGE_SIZE')
    jpeg = image.format == 'JPEG'
    return CheckedImage(_stripped_jpeg(data) if jpeg else _stripped_png(data), 'image/jpeg' if jpeg else 'image/png', width, height)


# EXIF tags a canvas or an image library writes about the picture itself: the IFD pointers, orientation, resolution, colour
# space and pixel size. Any other tag (camera, place, time, author, software, comment) is metadata the app refuses.
BASE_TAGS = frozenset({0x8769, 0x0112, 0x011A, 0x011B, 0x0128, 0x0213})
EXIF_TAGS = frozenset({0xA001, 0xA002, 0xA003})


def _structural(image):
    exif = image.getexif()
    if set(exif) - BASE_TAGS or set(exif.get_ifd(0x8769)) - EXIF_TAGS or exif.get_ifd(0x8825):
        return False
    # A JPEG resource block may hold an IPTC record (names, places); a canvas writes at most an empty one.
    resources = image.info.get('photoshop') or {}
    return all(len(value) <= 64 for value in resources.values()) if isinstance(resources, dict) else not resources


def _stripped_png(data):
    """The PNG without its metadata chunks (eXIf, text, time); pixel and colour chunks stay byte for byte."""
    out, index = [data[:8]], 8
    while index + 12 <= len(data):
        length = int.from_bytes(data[index:index + 4], 'big')
        kind = data[index + 4:index + 8]
        chunk = data[index:index + 12 + length]
        if kind not in {b'eXIf', b'tEXt', b'iTXt', b'zTXt', b'tIME'}:
            out.append(chunk)
        index += 12 + length
        if kind == b'IEND':
            break
    return b''.join(out)


def _stripped_jpeg(data):
    """The JPEG without its EXIF, XMP, resource and comment segments; the image data stays byte for byte."""
    out, index = [data[:2]], 2
    while index + 4 <= len(data) and data[index] == 0xFF:
        marker = data[index + 1]
        if marker == 0xDA:
            out.append(data[index:])
            return b''.join(out)
        length = int.from_bytes(data[index + 2:index + 4], 'big')
        if marker not in (0xE1, 0xED, 0xFE):
            out.append(data[index:index + 2 + length])
        index += 2 + length
    return b''.join(out)


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
