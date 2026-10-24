"""Server-side file validation.

A filename extension and the browser's Content-Type are both supplied by the
client, so neither is evidence. Every check here reads the bytes.

What is accepted is decided by one question: **can a reviewer read it in the
browser?** Browsers ship a PDF engine and an image decoder and nothing else, so
those are the formats a reviewer can actually review. A Word file would have to
be downloaded and opened elsewhere, which breaks the review loop — it is
refused with an explanation rather than accepted and left unreadable.

This is structural validation, not malware scanning. A well-formed PDF can
still be malicious; real scanning is listed as production work in the README.
"""

from __future__ import annotations

import io

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"

# Formats a browser renders natively. The extension is ours, not the user's —
# it is derived from what the bytes turn out to be.
ACCEPTED_IMAGES = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}

# Recognised on sight purely so the refusal can say something useful.
KNOWN_UNSUPPORTED = [
    (b"PK\x03\x04", "office_open_xml", "Word, Excel and PowerPoint files"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "legacy_office", "Older Office files (.doc, .xls, .ppt)"),
    (b"<?xml", "svg_or_xml", "SVG and XML files"),
    (b"<svg", "svg_or_xml", "SVG files"),
    (b"<!DOCTYPE html", "html", "HTML files"),
    (b"<html", "html", "HTML files"),
    (b"Rar!", "archive", "Archives"),
    (b"\x1f\x8b", "archive", "Archives"),
]

EXPORT_HINT = "Export it as a PDF and submit that instead."


class FileRejected(Exception):
    """The uploaded bytes are not something a reviewer could read."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ValidatedFile:
    """What the bytes actually turned out to be."""

    def __init__(self, kind: str, content_type: str, extension: str, content: bytes):
        self.kind = kind  # "pdf" or "image"
        self.content_type = content_type
        self.extension = extension
        self.content = content  # may differ from the upload: see strip_exif


def validate_upload(content: bytes, declared_name: str) -> ValidatedFile:
    """Raise FileRejected unless `content` is a readable PDF or image."""
    if not content:
        raise FileRejected("empty_file", "The selected file is empty.")

    if len(content) > settings.MAX_UPLOAD_BYTES:
        limit_mib = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise FileRejected(
            "file_too_large",
            f"The file is larger than the {limit_mib} MiB limit.",
            http_status=413,
        )

    if content.startswith(PDF_MAGIC):
        _check_pdf(content)
        return ValidatedFile("pdf", "application/pdf", ".pdf", content)

    image = _try_image(content)
    if image is not None:
        return image

    _refuse_with_a_useful_message(content)


def _check_pdf(content: bytes) -> None:
    try:
        reader = PdfReader(io.BytesIO(content))
    except (PdfReadError, Exception) as exc:  # noqa: BLE001 - pypdf raises varied errors
        raise FileRejected(
            "malformed_pdf", "That PDF could not be read. It may be damaged."
        ) from exc

    if reader.is_encrypted:
        # Rejected because a reviewer could not open it, and because the bytes
        # cannot be inspected.
        raise FileRejected(
            "encrypted_pdf",
            "Password-protected PDFs cannot be reviewed. Submit an unprotected copy.",
        )

    try:
        page_count = len(reader.pages)
    except Exception as exc:  # noqa: BLE001
        raise FileRejected(
            "malformed_pdf", "That PDF could not be read. It may be damaged."
        ) from exc

    if page_count < 1:
        raise FileRejected("empty_pdf", "That PDF has no pages.")


def _try_image(content: bytes) -> ValidatedFile | None:
    """Decode the image to prove it is one, then strip its metadata."""
    try:
        with Image.open(io.BytesIO(content)) as probe:
            fmt = probe.format
            # verify() checks structural integrity but leaves the file unusable
            # afterwards, so anything else must happen on a fresh handle.
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return None

    if fmt not in ACCEPTED_IMAGES:
        raise FileRejected(
            "unsupported_image",
            f"{fmt or 'That'} images cannot be reviewed. Submit a PNG, JPEG or WebP.",
        )

    content_type, extension = ACCEPTED_IMAGES[fmt]

    try:
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
            if width < 1 or height < 1:
                raise FileRejected("empty_image", "That image has no content.")
            cleaned = _strip_metadata(img, fmt)
    except FileRejected:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FileRejected(
            "malformed_image", "That image could not be read. It may be damaged."
        ) from exc

    return ValidatedFile("image", content_type, extension, cleaned)


def _strip_metadata(img: Image.Image, fmt: str) -> bytes:
    """Re-save without EXIF.

    Photographs routinely carry GPS coordinates, the device that took them and
    a timestamp. Someone submitting a phone photo of a signed form is unlikely
    to realise they are also submitting where they were standing, so it is
    removed rather than stored and shown.

    For JPEG this uses `quality="keep"`, which reuses the original quantization
    tables instead of re-compressing — the visible image is bit-for-bit what
    was uploaded, only the metadata segments are gone. The stored bytes differ
    from the upload, which is a deliberate trade: the submitter's privacy is
    worth more here than byte-exactness, and the picture itself is unchanged.
    """
    buffer = io.BytesIO()
    if fmt == "JPEG":
        img.save(buffer, format="JPEG", quality="keep")
    elif fmt == "PNG":
        img.save(buffer, format="PNG", optimize=False)
    else:
        img.save(buffer, format=fmt)
    return buffer.getvalue()


def _refuse_with_a_useful_message(content: bytes) -> None:
    """Name the format where we can, so the person knows what to do next."""
    head = content[:16]
    for magic, code, label in KNOWN_UNSUPPORTED:
        if head.startswith(magic):
            if code in {"office_open_xml", "legacy_office"}:
                raise FileRejected(
                    code,
                    f"{label} cannot be reviewed in the browser. {EXPORT_HINT}",
                )
            raise FileRejected(code, f"{label} cannot be submitted for review.")

    raise FileRejected(
        "unsupported_file",
        "That file cannot be reviewed. Submit a PDF, PNG, JPEG or WebP.",
    )
