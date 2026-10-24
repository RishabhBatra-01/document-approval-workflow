"""Which files a reviewer can actually be asked to review.

The rule behind every case here: browsers ship a PDF engine and an image
decoder and nothing else. A format the browser cannot draw cannot be reviewed
in the product, so it is refused with an explanation rather than accepted and
left unopenable.

Every file in these tests is produced by a real encoder — a real PDF writer, a
real image encoder, a real zip container — not by hand-written magic bytes.
"""

import io

from django.test import SimpleTestCase
from PIL import Image

from submissions.validation import FileRejected, validate_upload
from tests.support import docx_like_bytes, encrypted_pdf_bytes, real_image_bytes, real_pdf_bytes


class AcceptedTypesTests(SimpleTestCase):
    def test_pdf_is_accepted(self):
        result = validate_upload(real_pdf_bytes(), "report.pdf")
        self.assertEqual(result.kind, "pdf")
        self.assertEqual(result.content_type, "application/pdf")
        self.assertEqual(result.extension, ".pdf")

    def test_png_is_accepted(self):
        result = validate_upload(real_image_bytes("PNG"), "scan.png")
        self.assertEqual(result.kind, "image")
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(result.extension, ".png")

    def test_jpeg_is_accepted(self):
        result = validate_upload(real_image_bytes("JPEG"), "photo.jpg")
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertEqual(result.extension, ".jpg")

    def test_webp_is_accepted(self):
        result = validate_upload(real_image_bytes("WEBP"), "shot.webp")
        self.assertEqual(result.content_type, "image/webp")
        self.assertEqual(result.extension, ".webp")

    def test_a_multipage_pdf_is_accepted(self):
        result = validate_upload(real_pdf_bytes(pages=4), "long.pdf")
        self.assertEqual(result.kind, "pdf")

    def test_the_type_comes_from_the_bytes_not_the_filename(self):
        """A PNG named .pdf is still a PNG, and is stored as one."""
        result = validate_upload(real_image_bytes("PNG"), "definitely-a-report.pdf")
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(result.extension, ".png")


class ExifStrippingTests(SimpleTestCase):
    def test_camera_metadata_is_removed_from_photographs(self):
        """A phone photo carries where it was taken and on what."""
        original = real_image_bytes("JPEG", with_exif=True)
        with Image.open(io.BytesIO(original)) as before:
            self.assertTrue(dict(before.getexif()), "fixture should carry EXIF")

        cleaned = validate_upload(original, "signed-form.jpg").content

        with Image.open(io.BytesIO(cleaned)) as after:
            self.assertEqual(dict(after.getexif()), {}, "EXIF survived the upload")

    def test_the_picture_itself_is_unchanged(self):
        """Metadata goes; the image a reviewer sees does not."""
        original = real_image_bytes("JPEG", size=(64, 48), with_exif=True)
        cleaned = validate_upload(original, "photo.jpg").content

        with Image.open(io.BytesIO(original)) as a, Image.open(io.BytesIO(cleaned)) as b:
            self.assertEqual(a.size, b.size)
            self.assertEqual(list(a.convert("RGB").getdata()), list(b.convert("RGB").getdata()))


class RefusedTypesTests(SimpleTestCase):
    def assert_refused(self, content: bytes, name: str, code: str):
        with self.assertRaises(FileRejected) as caught:
            validate_upload(content, name)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_word_excel_powerpoint_are_refused_with_a_useful_message(self):
        error = self.assert_refused(docx_like_bytes(), "contract.docx", "office_open_xml")
        # The refusal must say what to do next, not merely that it failed.
        self.assertIn("PDF", error.message)

    def test_legacy_office_files_are_refused(self):
        legacy = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
        self.assert_refused(legacy, "old.doc", "legacy_office")

    def test_svg_is_refused_because_it_is_executable(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assert_refused(svg, "diagram.svg", "svg_or_xml")

    def test_html_is_refused(self):
        self.assert_refused(b"<html><body>hi</body></html>", "page.html", "html")

    def test_gif_is_refused_even_though_it_is_a_real_image(self):
        """Accepted formats are an allowlist, not "anything Pillow can open"."""
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), (0, 0, 0)).save(buffer, format="GIF")
        self.assert_refused(buffer.getvalue(), "animation.gif", "unsupported_image")

    def test_plain_text_is_refused(self):
        self.assert_refused(b"Dear reviewer, please approve this.", "note.pdf", "unsupported_file")

    def test_encrypted_pdf_is_still_refused(self):
        self.assert_refused(encrypted_pdf_bytes(), "locked.pdf", "encrypted_pdf")

    def test_truncated_pdf_is_refused(self):
        self.assert_refused(real_pdf_bytes()[:40], "cut-short.pdf", "malformed_pdf")

    def test_pdf_header_with_a_garbage_body_is_refused(self):
        self.assert_refused(b"%PDF-1.7\nnot actually a pdf body", "fake.pdf", "malformed_pdf")

    def test_empty_file_is_refused(self):
        self.assert_refused(b"", "nothing.pdf", "empty_file")

    def test_truncated_image_is_refused(self):
        truncated = real_image_bytes("PNG")[:30]
        with self.assertRaises(FileRejected):
            validate_upload(truncated, "broken.png")

    def test_oversized_file_is_refused_before_anything_is_decoded(self):
        from django.conf import settings

        oversized = real_image_bytes("PNG") + b"\x00" * settings.MAX_UPLOAD_BYTES
        error = self.assert_refused(oversized, "huge.png", "file_too_large")
        self.assertEqual(error.http_status, 413)
