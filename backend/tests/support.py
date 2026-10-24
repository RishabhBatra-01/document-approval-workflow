"""Shared test helpers.

Everything here talks to the real Supabase project. There are no mocks, no
patched returns and no fake tokens: tokens are obtained by actually signing in,
and uploads really land in the private bucket.
"""

from __future__ import annotations

import io
import os
import re
import uuid

from django.conf import settings
from pypdf import PdfWriter
from supabase import create_client

from accounts.models import Profile, Role


class TestConfigurationError(RuntimeError):
    """Required test configuration is missing or unsafe. Never skipped silently."""


def project_ref(url: str) -> str:
    match = re.search(r"https://([a-z0-9]+)\.supabase\.co", url)
    return match.group(1) if match else ""


def assert_safe_test_project() -> None:
    """Refuse to run destructive setup against anything but the declared test project.

    The brief's rule: an explicitly configured test project, or stop. This is
    checked before any run creates or deletes provider resources.
    """
    declared = os.environ.get("SUPABASE_TEST_PROJECT_REF", "").strip()
    if not declared:
        raise TestConfigurationError(
            "SUPABASE_TEST_PROJECT_REF is not set. Integration tests create and delete "
            "real Auth users and storage objects, so they refuse to run until the test "
            "project is named explicitly. Set it in backend/.env."
        )

    configured = project_ref(settings.SUPABASE_URL)
    if configured != declared:
        raise TestConfigurationError(
            f"Refusing to run: SUPABASE_URL points at project '{configured}' but "
            f"SUPABASE_TEST_PROJECT_REF is '{declared}'. This guard exists to stop tests "
            f"touching a deployment project."
        )

    deployment = os.environ.get("SUPABASE_DEPLOYMENT_PROJECT_REF", "").strip()
    if deployment and deployment == configured:
        raise TestConfigurationError(
            f"Refusing to run: project '{configured}' is declared as the deployment project."
        )


def admin_client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)


def anon_client():
    """A client with no privileges beyond signing in, like the browser has."""
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not key:
        raise TestConfigurationError(
            "SUPABASE_PUBLISHABLE_KEY is not set in backend/.env. Tests sign in the way "
            "the browser does, which needs the publishable key."
        )
    return create_client(settings.SUPABASE_URL, key)


# --- run-scoped identities -------------------------------------------------
# Every run uses fresh accounts with a unique prefix, so a run only ever removes
# what it created and parallel runs cannot collide.

RUN_ID = uuid.uuid4().hex[:10]


class RealAccount:
    """A genuine Supabase Auth user plus its application Profile."""

    def __init__(self, label: str, role: str, with_profile: bool = True):
        self.email = f"test-{RUN_ID}-{label}@example.com"
        self.password = f"Tp{uuid.uuid4().hex}!9"
        self.role = role
        self.auth_user_id: str | None = None
        self.profile: Profile | None = None
        self._with_profile = with_profile

    def create(self) -> "RealAccount":
        created = admin_client().auth.admin.create_user(
            {"email": self.email, "password": self.password, "email_confirm": True}
        )
        self.auth_user_id = str(created.user.id)
        if self._with_profile:
            self.profile = Profile.objects.create(
                auth_user_id=self.auth_user_id,
                email=self.email,
                display_name=f"Test {self.role.title()} {self.email[:12]}",
                role=self.role,
            )
        return self

    def access_token(self) -> str:
        """A real access token, obtained by really signing in."""
        session = anon_client().auth.sign_in_with_password(
            {"email": self.email, "password": self.password}
        )
        return session.session.access_token

    def auth_header(self) -> dict:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.access_token()}"}

    def destroy(self) -> None:
        if self.auth_user_id:
            try:
                admin_client().auth.admin.delete_user(self.auth_user_id)
            except Exception:  # noqa: BLE001 - cleanup must not mask test results
                pass


def make_submitter(label: str = "sub") -> RealAccount:
    return RealAccount(label, Role.SUBMITTER).create()


def make_reviewer(label: str = "rev") -> RealAccount:
    return RealAccount(label, Role.REVIEWER).create()


# --- real files ------------------------------------------------------------

def real_pdf_bytes(pages: int = 1) -> bytes:
    """A genuine, valid PDF produced by a real PDF writer."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def encrypted_pdf_bytes(password: str = "locked") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def real_image_bytes(fmt: str = "PNG", size=(40, 30), with_exif: bool = False) -> bytes:
    """A genuine image produced by a real encoder."""
    import io as _io

    from PIL import Image

    img = Image.new("RGB", size, (90, 140, 110))
    buffer = _io.BytesIO()
    if fmt == "JPEG" and with_exif:
        exif = Image.Exif()
        exif[0x010F] = "TestCamera"          # Make
        exif[0x9003] = "2026:10:24 12:00:00"  # DateTimeOriginal
        img.save(buffer, format="JPEG", exif=exif)
    else:
        img.save(buffer, format=fmt)
    return buffer.getvalue()


def docx_like_bytes() -> bytes:
    """A real zip container, which is what a .docx actually is."""
    import io as _io
    import zipfile

    buffer = _io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


def upload_file(content: bytes, name: str = "document.pdf"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type="application/pdf")


def cleanup_storage_object(key: str) -> None:
    from integrations.supabase_storage import get_storage

    try:
        get_storage().remove(key)
    except Exception:  # noqa: BLE001
        pass
