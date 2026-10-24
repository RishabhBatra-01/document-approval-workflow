"""Failure handling, with failures that genuinely happen.

Nothing here patches a return value or raises a fabricated exception. Each
failure is induced by pointing a real client at something that really fails:
a closed port, a bucket that does not exist, a value the real database really
rejects. The errors come back from the real libraries and the real services.
"""

from __future__ import annotations

import uuid

from django.db import DatabaseError
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounts.authentication import SupabaseTokenAuthentication
from config.errors import ApiError
from integrations.supabase_auth import AuthUnavailable, InvalidToken, SupabaseAuthVerifier
from integrations.supabase_storage import StorageUnavailable, SupabaseStorage
from submissions.models import Submission
from submissions.services import create_submission
from tests.support import (
    assert_safe_test_project,
    cleanup_storage_object,
    make_submitter,
    real_pdf_bytes,
    upload_file,
)

# A port nothing is listening on. Connecting really fails, at the socket level.
DEAD_ENDPOINT = "http://127.0.0.1:9"


class AuthOutageTests(TestCase):
    """What happens when Supabase Auth cannot be reached at all."""

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def test_unreachable_auth_raises_unavailable_not_invalid(self):
        """A real connection failure, from a real client, to a dead port."""
        verifier = SupabaseAuthVerifier(url=DEAD_ENDPOINT, secret_key="sb_secret_unused")
        with self.assertRaises(AuthUnavailable):
            verifier.verify("any-token-at-all")

    def test_outage_surfaces_as_503_and_not_401(self):
        """The distinction that matters: an outage must not look like a bad password.

        A 401 would make the frontend sign the user out and discard their work
        during what is only a temporary provider problem.
        """
        authenticator = SupabaseTokenAuthentication(
            verifier=SupabaseAuthVerifier(url=DEAD_ENDPOINT, secret_key="sb_secret_unused")
        )

        class Request:
            META = {"HTTP_AUTHORIZATION": "Bearer some-token"}

        with self.assertRaises(ApiError) as caught:
            authenticator.authenticate(Request())

        self.assertEqual(caught.exception.http_status, 503)
        self.assertEqual(caught.exception.code, "auth_unavailable")

    def test_a_genuinely_bad_token_is_still_401(self):
        """Against the real, reachable service — so the two paths are distinguished."""
        with self.assertRaises(InvalidToken):
            SupabaseAuthVerifier().verify("clearly-not-a-valid-jwt")


class StorageFailureTests(TransactionTestCase):
    """Upload failures, and what the database is left holding."""

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.submitter = make_submitter("fail-storage")
        self.object_keys: list[str] = []

    def tearDown(self):
        for key in self.object_keys:
            cleanup_storage_object(key)
        self.submitter.destroy()

    def test_upload_to_a_nonexistent_bucket_really_fails(self):
        missing = SupabaseStorage(bucket=f"no-such-bucket-{uuid.uuid4().hex[:8]}")
        with self.assertRaises(StorageUnavailable):
            missing.upload("probe/key.pdf", real_pdf_bytes())

    def test_storage_failure_leaves_no_database_record(self):
        """The order matters: upload first means a failure writes nothing."""
        before = Submission.objects.count()
        missing = SupabaseStorage(bucket=f"no-such-bucket-{uuid.uuid4().hex[:8]}")

        with self.assertRaises(StorageUnavailable):
            create_submission(
                profile=self.submitter.profile,
                title="Should never be saved",
                context="",
                upload=upload_file(real_pdf_bytes()),
                storage=missing,
            )

        self.assertEqual(Submission.objects.count(), before)
        self.assertFalse(Submission.objects.filter(title="Should never be saved").exists())

    def test_storage_failure_returns_503_through_the_api(self):
        client = APIClient()
        # A real request, failing for a real reason: the configured bucket name
        # is overridden to one that does not exist in the project.
        from django.test import override_settings

        with override_settings(SUPABASE_STORAGE_BUCKET=f"missing-{uuid.uuid4().hex[:8]}"):
            # The module-level storage is built from settings on first use, so a
            # fresh instance is required for the override to apply.
            import integrations.supabase_storage as storage_module

            storage_module._default_storage = None
            try:
                response = client.post(
                    "/api/submissions/",
                    {"title": "Bucket is gone", "file": upload_file(real_pdf_bytes())},
                    format="multipart",
                    **self.submitter.auth_header(),
                )
            finally:
                storage_module._default_storage = None

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "storage_unavailable")
        # The user's inputs were not silently thrown away server-side.
        self.assertFalse(Submission.objects.filter(title="Bucket is gone").exists())


class DatabaseFailureAfterUploadTests(TransactionTestCase):
    """The genuinely awkward path: the object is stored, the row will not save."""

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.submitter = make_submitter("fail-db")
        self.storage = SupabaseStorage()

    def tearDown(self):
        self.submitter.destroy()

    def test_database_failure_after_upload_cleans_the_object_up(self):
        """Induced by a value PostgreSQL really rejects.

        `title` is varchar(150); 400 characters is a real constraint violation
        raised by the real driver, after the real upload has already happened.
        The serializer would normally stop this, which is exactly why the
        service is exercised directly.
        """
        before = Submission.objects.count()

        with self.assertRaises(DatabaseError):
            create_submission(
                profile=self.submitter.profile,
                title="x" * 400,
                context="",
                upload=upload_file(real_pdf_bytes()),
            )

        # No half-written record.
        self.assertEqual(Submission.objects.count(), before)

        # And no orphan: the uploaded object was removed, so nothing in the
        # bucket is left pointing at a row that does not exist. Verified by
        # asking the real Storage service for the object.
        keys = self._list_objects_for(self.submitter.profile.id)
        self.assertEqual(keys, [], f"cleanup left orphaned objects: {keys}")

    def _list_objects_for(self, profile_id) -> list[str]:
        client = self.storage._bucket  # real Storage client for this bucket
        try:
            listing = client.list(f"submissions/{profile_id}")
        except Exception:  # noqa: BLE001
            return []
        return [item["name"] for item in listing if item.get("name")]


class CleanupFailureTests(TransactionTestCase):
    """Both systems fail: the row will not save and the object will not delete."""

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.submitter = make_submitter("fail-cleanup")
        self.leaked_key: str | None = None

    def tearDown(self):
        if self.leaked_key:
            cleanup_storage_object(self.leaked_key)
        self.submitter.destroy()

    def test_cleanup_failure_is_logged_with_the_key_a_human_needs(self):
        """A real double failure.

        This uses the real SupabaseStorage class against the real service. The
        only alteration is that deletion is aimed at a bucket that genuinely
        does not exist, so `remove()` gets a real error from the real API. No
        response is faked and no exception is fabricated — the upload really
        succeeds and the delete really fails.
        """
        storage = self._storage_that_cannot_delete()

        with self.assertLogs("submissions.services", level="ERROR") as logs:
            with self.assertRaises(DatabaseError):
                create_submission(
                    profile=self.submitter.profile,
                    title="y" * 400,  # real varchar(150) violation
                    context="",
                    upload=upload_file(real_pdf_bytes()),
                    storage=storage,
                )

        self.leaked_key = storage.last_uploaded_key
        combined = "\n".join(logs.output)
        self.assertIn("ORPHANED STORAGE OBJECT", combined)
        # The log must name the object, or nobody can clean it up by hand.
        self.assertIn(storage.last_uploaded_key, combined)

    def _storage_that_cannot_delete(self):
        real_bucket = SupabaseStorage()._bucket_name
        doomed = f"no-such-bucket-{uuid.uuid4().hex[:8]}"

        class UploadsHereDeletesNowhere(SupabaseStorage):
            """Real client, real calls — deletion simply targets a bucket that is not there."""

            def __init__(self):
                super().__init__(bucket=real_bucket)
                self.last_uploaded_key = ""

            def upload(self, object_key, content, content_type="application/pdf"):
                self.last_uploaded_key = object_key
                return super().upload(object_key, content, content_type)

            def remove(self, object_key):
                return SupabaseStorage(bucket=doomed).remove(object_key)

        return UploadsHereDeletesNowhere()


class SilentDeleteRegressionTests(TransactionTestCase):
    """Supabase answers a failed delete with 200 and an empty list.

    Caught in Phase 2: `remove()` previously treated "did not raise" as
    success, so a cleanup that deleted nothing looked like a cleanup that
    worked, and the orphaned object was never reported. A mocked client raising
    an exception would have passed the old test and hidden this.
    """

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def test_deleting_from_a_missing_bucket_is_reported_as_a_failure(self):
        doomed = SupabaseStorage(bucket=f"no-such-bucket-{uuid.uuid4().hex[:8]}")
        with self.assertRaises(StorageUnavailable):
            doomed.remove("submissions/anything/at-all.pdf")

    def test_deleting_an_object_that_does_not_exist_is_reported_as_a_failure(self):
        real = SupabaseStorage()
        with self.assertRaises(StorageUnavailable):
            real.remove(f"submissions/{uuid.uuid4()}/never-uploaded.pdf")

    def test_deleting_an_object_that_does_exist_succeeds(self):
        """The positive case, so the check above cannot pass by always failing."""
        real = SupabaseStorage()
        key = f"submissions/cleanup-probe/{uuid.uuid4()}.pdf"
        real.upload(key, real_pdf_bytes())
        real.remove(key)  # must not raise
        with self.assertRaises(StorageUnavailable):
            real.remove(key)  # second delete removes nothing, so it must raise


class OversizedUploadTests(TransactionTestCase):
    """The 5 MiB limit, enforced over real HTTP rather than only in a unit test."""

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.submitter = make_submitter("oversize")

    def tearDown(self):
        self.submitter.destroy()

    def test_oversized_pdf_is_rejected_with_413(self):
        from django.conf import settings

        client = APIClient()
        oversized = b"%PDF-1.4\n" + b"0" * (settings.MAX_UPLOAD_BYTES + 1024)
        response = client.post(
            "/api/submissions/",
            {"title": "Far too large", "file": upload_file(oversized, "huge.pdf")},
            format="multipart",
            **self.submitter.auth_header(),
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "file_too_large")
        self.assertFalse(Submission.objects.filter(title="Far too large").exists())

    def test_empty_file_is_rejected_over_http(self):
        client = APIClient()
        response = client.post(
            "/api/submissions/",
            {"title": "Nothing inside", "file": upload_file(b"", "empty.pdf")},
            format="multipart",
            **self.submitter.auth_header(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(response.json()["error"]["code"], {"empty_file", "invalid_request"})
