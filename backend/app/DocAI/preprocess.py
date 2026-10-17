"""
Turning a stored file into what is sent to the API (05 §4.1).

    prepare(content_type, data) → Prepared: the whole file as one content block, and
                                   one block per page (statements are read page by page)
    ✗ RescanNeeded(reason)        a file that can't be sent: password-protected or
                                   broken PDF, HEIC photo, unreadable image

PDFs go as `document` blocks; JPEG and PNG as `image` blocks; TIFF is converted to PNG.
Very large images are scaled down (the API limits image size).
"""
import base64
import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

MAX_IMAGE_BYTES = 4_500_000
MAX_IMAGE_EDGE = 2400
MAX_REQUEST_BYTES = 30_000_000  # base64 of what is sent must stay under the API's 32 MB request limit


class RescanNeeded(Exception):
    pass


@dataclass
class Prepared:
    page_count: int
    whole: dict          # content block for the whole file
    pages: list[dict]    # one content block per page


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _pdf_block(data: bytes) -> dict:
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": _b64(data)}}


def _image_block(data: bytes, media_type: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": _b64(data)}}


def _image(data: bytes, content_type: str) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise RescanNeeded("The image file is damaged and can't be opened. Upload it again.")
    needs_convert = content_type not in ("image/jpeg", "image/png")
    too_big = len(data) > MAX_IMAGE_BYTES or max(img.size) > 7900
    if not needs_convert and not too_big:
        return data, content_type
    if too_big:
        img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
    out = io.BytesIO()
    if too_big:
        img.convert("RGB").save(out, format="JPEG", quality=90)
        return out.getvalue(), "image/jpeg"
    img.save(out, format="PNG")
    return out.getvalue(), "image/png"


def prepare(content_type: str, data: bytes) -> Prepared:
    if content_type == "image/heic":
        raise RescanNeeded("HEIC photos can't be read automatically. Upload a JPEG or PDF copy, or capture the "
                           "details by hand.")
    if content_type.startswith("image/"):
        image, media_type = _image(data, content_type)
        block = _image_block(image, media_type)
        return Prepared(1, block, [block])
    if content_type != "application/pdf":
        raise RescanNeeded(f"Files of type {content_type} can't be read automatically.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise RescanNeeded("The PDF is password-protected. Ask the client for an unlocked copy (passwords are "
                               "never stored).")
        pages = []
        for page in reader.pages:
            writer = PdfWriter()
            writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            pages.append(_pdf_block(buf.getvalue()))
    except RescanNeeded:
        raise
    except (PdfReadError, ValueError, KeyError, OSError):
        raise RescanNeeded("The PDF is damaged and can't be opened. Upload it again.")
    if not pages:
        raise RescanNeeded("The PDF has no pages.")
    if len(data) * 4 // 3 > MAX_REQUEST_BYTES:
        raise RescanNeeded("The file is too large to send in one piece. Upload a smaller scan.")
    return Prepared(len(pages), _pdf_block(data), pages)
