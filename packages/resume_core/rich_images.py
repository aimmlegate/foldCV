"""Validate local image bytes before publishing an owned asset."""

import hashlib
from io import BytesIO
import warnings

from PIL import Image, ImageOps

from .models.rich_workspace import LocalImageAsset
from .rich_limits import IMAGE_BYTES, IMAGE_PIXELS, RETAINED_IMAGE_BYTES


class ImageFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def normalize_image(raw: bytes, asset_id: str):
    if not raw or len(raw) > IMAGE_BYTES:
        raise ImageFailure("IMAGE_INPUT_LIMIT")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ImageFailure("IMAGE_FORMAT_UNSUPPORTED")
                if getattr(image, "n_frames", 1) != 1 or getattr(image, "is_animated", False):
                    raise ImageFailure("IMAGE_ANIMATED")
                if image.width * image.height > IMAGE_PIXELS:
                    raise ImageFailure("IMAGE_PIXEL_LIMIT")
                image.load()
                chosen = ImageOps.exif_transpose(image)
                output = BytesIO()
                # Strip input metadata and normalize once; later readers use these exact bytes.
                jpeg = image.format == "JPEG"
                chosen.convert("RGB" if jpeg else "RGBA").save(output, format="JPEG" if jpeg else "PNG")
                content = output.getvalue()
                width, height = chosen.size
        if len(content) > RETAINED_IMAGE_BYTES:
            raise ImageFailure("IMAGE_RETAINED_LIMIT")
        checksum = hashlib.sha256(content).hexdigest()
        extension = "jpg" if jpeg else "png"
        return LocalImageAsset(id=asset_id, sha256=checksum, path=f"images/{checksum}.{extension}",
            mimeType="image/jpeg" if jpeg else "image/png", size=len(content), width=width, height=height), content
    except ImageFailure:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ImageFailure("IMAGE_PIXEL_LIMIT") from None
    except (OSError, ValueError, SyntaxError):
        raise ImageFailure("IMAGE_INVALID") from None


def verify_image_bytes(asset: LocalImageAsset, raw: bytes) -> None:
    if len(raw) != asset.size or hashlib.sha256(raw).hexdigest() != asset.sha256:
        raise ImageFailure("IMAGE_BYTES_MISMATCH")
    try:
        with Image.open(BytesIO(raw)) as image:
            expected = "PNG" if asset.mime_type == "image/png" else "JPEG"
            if image.format != expected or image.size != (asset.width, asset.height) or getattr(image, "n_frames", 1) != 1:
                raise ImageFailure("IMAGE_BYTES_MISMATCH")
            image.verify()
    except ImageFailure:
        raise
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ImageFailure("IMAGE_BYTES_MISMATCH") from None
