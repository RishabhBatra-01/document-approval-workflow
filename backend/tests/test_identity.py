"""Who the server believes you are, and what it refuses.

Every token here is real: obtained by signing in to the real Supabase project.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Profile, Role
from tests.support import RealAccount, assert_safe_test_project, make_submitter


class IdentityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.client = APIClient()
        self.created: list[RealAccount] = []

    def tearDown(self):
        for account in self.created:
            account.destroy()

    def track(self, account: RealAccount) -> RealAccount:
        self.created.append(account)
        return account

    def test_health_needs_no_authentication(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_leaks_no_configuration(self):
        body = self.client.get("/api/health/").content.decode().lower()
        for secret_marker in ["sb_secret", "password", "supabase.co", "postgres"]:
            self.assertNotIn(secret_marker, body)

    def test_missing_token_is_rejected(self):
        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, 401)

    def test_garbage_token_is_rejected(self):
        response = self.client.get("/api/me/", HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_token")

    def test_malformed_authorization_header_is_rejected(self):
        response = self.client.get("/api/me/", HTTP_AUTHORIZATION="Token abc123")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_authorization_header")

    def test_real_token_resolves_to_the_application_profile(self):
        account = self.track(make_submitter("identity"))
        response = self.client.get("/api/me/", **account.auth_header())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], account.email)
        self.assertEqual(body["role"], Role.SUBMITTER)

    def test_authenticated_but_unprovisioned_account_is_denied(self):
        """A valid Supabase session is not an application account."""
        account = self.track(RealAccount("orphan", Role.SUBMITTER, with_profile=False).create())
        self.assertFalse(Profile.objects.filter(auth_user_id=account.auth_user_id).exists())

        response = self.client.get("/api/me/", **account.auth_header())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "profile_not_provisioned")

    def test_role_cannot_be_asserted_by_the_client(self):
        """Headers and body cannot promote a submitter to reviewer."""
        account = self.track(make_submitter("noescalate"))
        response = self.client.get(
            "/api/me/",
            HTTP_X_ROLE="reviewer",
            **account.auth_header(),
        )
        self.assertEqual(response.json()["role"], Role.SUBMITTER)
