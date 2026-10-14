from io import BytesIO

from PIL import Image
import pymupdf

from tools.measure_reference_template import decoded_image, rgb_hash


def test_reference_image_alpha_is_compared_without_double_premultiplication():
    image = Image.new("RGBA", (8, 4), (240, 30, 15, 128))
    image.putpixel((1, 1), (20, 200, 40, 255))
    raw = BytesIO()
    image.save(raw, format="PNG")
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_image(pymupdf.Rect(10, 10, 90, 50), stream=raw.getvalue())
        xref, smask = page.get_images()[0][:2]
        assert smask > 0
        decoded = decoded_image(document, xref, smask)
        assert rgb_hash(decoded) == rgb_hash(image)
        pixel = decoded.getpixel((0, 0))
        assert pixel[3] == 128
        assert all(abs(actual - expected) <= 1 for actual, expected in zip(pixel[:3], (240, 30, 15)))
