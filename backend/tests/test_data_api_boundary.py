"""The Data API must never serve this application's tables.

Regression test for a real vulnerability found in Phase 2: Supabase grants
`anon` and `authenticated` full privileges on new tables in `public` by
default, so every Django-created table was readable AND writable through the
auto-generated REST API using only the publishable key — the key that ships in
the browser bundle. `app_profile.role` was updatable, which would have let any
visitor grant themselves reviewer access.

These checks run against the real project over real HTTP.
"""

import os

import httpx
from django.conf import settings
from django.test import SimpleTestCase, TransactionTestCase

from tests.support import assert_safe_test_project

APP_TABLES = ["app_profile", "app_submission"]


class DataApiBoundaryTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()
        cls.publishable = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        cls.rest = f"{settings.SUPABASE_URL}/rest/v1"

    def headers(self) -> dict:
        return {"apikey": self.publishable, "Authorization": f"Bearer {self.publishable}"}

    def test_publishable_key_cannot_read_application_tables(self):
        for table in APP_TABLES:
            response = httpx.get(
                f"{self.rest}/{table}", params={"select": "*"}, headers=self.headers(), timeout=30
            )
            self.assertNotEqual(
                response.status_code,
                200,
                f"SECURITY: {table} is readable through the Data API with the publishable key.",
            )

    def test_publishable_key_cannot_write_application_tables(self):
        """The dangerous one: writing app_profile.role would grant reviewer access."""
        response = httpx.patch(
            f"{self.rest}/app_profile",
            params={"role": "eq.submitter"},
            json={"role": "reviewer"},
            headers={**self.headers(), "Content-Type": "application/json"},
            timeout=30,
        )
        self.assertNotEqual(
            response.status_code,
            200,
            "SECURITY: application roles are writable through the Data API.",
        )
        self.assertNotIn(response.status_code, (201, 204))

    def test_publishable_key_cannot_delete_submissions(self):
        response = httpx.delete(
            f"{self.rest}/app_submission",
            params={"id": "neq.00000000-0000-0000-0000-000000000000"},
            headers=self.headers(),
            timeout=30,
        )
        self.assertNotIn(
            response.status_code,
            (200, 204),
            "SECURITY: submissions are deletable through the Data API.",
        )

    def test_private_bucket_is_not_browsable_with_the_publishable_key(self):
        response = httpx.post(
            f"{settings.SUPABASE_URL}/storage/v1/object/list/{settings.SUPABASE_STORAGE_BUCKET}",
            json={"prefix": "", "limit": 100},
            headers={**self.headers(), "Content-Type": "application/json"},
            timeout=30,
        )
        if response.status_code == 200:
            # An empty list is acceptable; actual object names are not.
            self.assertEqual(
                response.json(), [], "SECURITY: the bucket is listable with the publishable key."
            )


class PrivateStorageTests(TransactionTestCase):
    """Objects must be reachable only through a current, untampered signature."""

    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        from tests.support import make_submitter, real_pdf_bytes
        from integrations.supabase_storage import SupabaseStorage
        import uuid as _uuid

        self.submitter = make_submitter("storage-acl")
        self.storage = SupabaseStorage()
        self.key = f"submissions/acl-probe/{_uuid.uuid4()}.pdf"
        self.storage.upload(self.key, real_pdf_bytes())

    def tearDown(self):
        try:
            self.storage.remove(self.key)
        except Exception:  # noqa: BLE001
            pass
        self.submitter.destroy()

    def _status(self, url: str, headers: dict | None = None) -> int:
        response = httpx.get(url, headers=headers or {}, timeout=30, follow_redirects=True)
        return response.status_code

    def test_object_is_not_served_from_the_public_path(self):
        bucket = settings.SUPABASE_STORAGE_BUCKET
        status = self._status(f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{self.key}")
        self.assertNotEqual(status, 200, "SECURITY: the bucket is serving objects publicly.")

    def test_object_is_not_served_without_credentials(self):
        bucket = settings.SUPABASE_STORAGE_BUCKET
        status = self._status(f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{self.key}")
        self.assertNotEqual(status, 200)

    def test_the_browsers_own_key_cannot_fetch_an_object(self):
        """The publishable key is in the bundle, so this is the realistic attack."""
        key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        bucket = settings.SUPABASE_STORAGE_BUCKET
        status = self._status(
            f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{self.key}",
            {"apikey": key, "Authorization": f"Bearer {key}"},
        )
        self.assertNotEqual(status, 200, "SECURITY: the publishable key can read stored documents.")

    def test_a_valid_signed_url_works(self):
        """The positive case, so the denials above cannot pass by always failing."""
        signed = self.storage.create_signed_url(self.key, 60)
        self.assertEqual(self._status(signed.url), 200)

    def test_a_signed_url_stops_working_once_it_expires(self):
        import time

        signed = self.storage.create_signed_url(self.key, 1)
        time.sleep(3)
        self.assertNotEqual(self._status(signed.url), 200, "SECURITY: expired links still resolve.")

    def test_a_tampered_signature_is_rejected(self):
        signed = self.storage.create_signed_url(self.key, 60)
        self.assertNotEqual(self._status(signed.url[:-6] + "aaaaaa"), 200)
