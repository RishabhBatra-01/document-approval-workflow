"""The submission path and its access rules, end to end against real services."""

from django.test import TestCase
from rest_framework.test import APIClient

from submissions.models import Status, Submission
from tests.support import (
    RealAccount,
    assert_safe_test_project,
    cleanup_storage_object,
    make_reviewer,
    make_submitter,
    real_pdf_bytes,
    upload_file,
)


class WorkflowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.client = APIClient()
        self.accounts: list[RealAccount] = []
        self.object_keys: list[str] = []
        self.alice = self.track(make_submitter("alice"))
        self.bob = self.track(make_submitter("bob"))
        self.reviewer = self.track(make_reviewer("rev"))

    def tearDown(self):
        for key in self.object_keys:
            cleanup_storage_object(key)
        for account in self.accounts:
            account.destroy()

    def track(self, account: RealAccount) -> RealAccount:
        self.accounts.append(account)
        return account

    def submit(self, account: RealAccount, title="Quarterly report", extra=None):
        payload = {"title": title, "context": "Please review.", "file": upload_file(real_pdf_bytes())}
        if extra:
            payload.update(extra)
        response = self.client.post(
            "/api/submissions/", payload, format="multipart", **account.auth_header()
        )
        if response.status_code == 201:
            submission = Submission.objects.get(id=response.json()["id"])
            self.object_keys.append(submission.storage_object_key)
        return response

    # --- creating ---------------------------------------------------------

    def test_submitter_creates_a_pending_submission(self):
        response = self.submit(self.alice)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], Status.PENDING)
        self.assertEqual(body["submitted_by"]["email"], self.alice.email)
        self.assertIsNone(body["reviewed_by"])

        stored = Submission.objects.get(id=body["id"])
        # The real file really landed, under a generated key.
        self.assertNotIn("document.pdf", stored.storage_object_key)
        self.assertTrue(stored.storage_object_key.endswith(".pdf"))
        self.assertGreater(stored.file_size_bytes, 0)

    def test_client_cannot_choose_owner_or_status(self):
        response = self.submit(
            self.alice,
            extra={"submitted_by": str(self.bob.profile.id), "status": Status.APPROVED},
        )
        self.assertEqual(response.status_code, 201)
        stored = Submission.objects.get(id=response.json()["id"])
        self.assertEqual(stored.submitted_by_id, self.alice.profile.id)
        self.assertEqual(stored.status, Status.PENDING)

    def test_blank_title_is_rejected(self):
        response = self.client.post(
            "/api/submissions/",
            {"title": "   ", "file": upload_file(real_pdf_bytes())},
            format="multipart",
            **self.alice.auth_header(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.json()["error"]["field_errors"])

    def test_missing_file_is_rejected(self):
        response = self.client.post(
            "/api/submissions/", {"title": "No file"}, format="multipart", **self.alice.auth_header()
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.json()["error"]["field_errors"])

    def test_unreviewable_file_is_rejected_on_content_not_extension(self):
        """A text file named .pdf and declared application/pdf is still text."""
        response = self.client.post(
            "/api/submissions/",
            {"title": "Fake", "file": upload_file(b"this is plainly not a pdf", "report.pdf")},
            format="multipart",
            **self.alice.auth_header(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unsupported_file")

    def test_an_image_can_be_submitted_and_is_stored_as_an_image(self):
        """A photograph of a signed form is a real submission, not a PDF."""
        from tests.support import real_image_bytes

        response = self.client.post(
            "/api/submissions/",
            {"title": "Signed form", "file": upload_file(real_image_bytes("PNG"), "scan.png")},
            format="multipart",
            **self.alice.auth_header(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        stored = Submission.objects.get(id=response.json()["id"])
        self.object_keys.append(stored.storage_object_key)
        self.assertEqual(stored.content_type, "image/png")
        self.assertTrue(stored.storage_object_key.endswith(".png"))

    def test_a_word_document_is_refused_with_advice(self):
        from tests.support import docx_like_bytes

        response = self.client.post(
            "/api/submissions/",
            {"title": "Contract", "file": upload_file(docx_like_bytes(), "contract.docx")},
            format="multipart",
            **self.alice.auth_header(),
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()["error"]
        self.assertEqual(body["code"], "office_open_xml")
        self.assertIn("PDF", body["message"])

    def test_reviewer_cannot_create(self):
        response = self.submit(self.reviewer)
        self.assertEqual(response.status_code, 403)

    # --- reading ----------------------------------------------------------

    def test_submitter_sees_only_their_own(self):
        self.submit(self.alice, title="Alice document")
        self.submit(self.bob, title="Bob document")

        titles = [
            row["title"]
            for row in self.client.get("/api/submissions/", **self.alice.auth_header()).json()["results"]
        ]
        self.assertEqual(titles, ["Alice document"])

    def test_submitter_cannot_fetch_another_submitters_document(self):
        created = self.submit(self.bob, title="Bob private").json()
        response = self.client.get(f"/api/submissions/{created['id']}/", **self.alice.auth_header())
        # 404, not 403: the response must not confirm the document exists.
        self.assertEqual(response.status_code, 404)

    def test_submitter_cannot_get_a_read_url_for_another_submitters_document(self):
        created = self.submit(self.bob, title="Bob private").json()
        response = self.client.get(
            f"/api/submissions/{created['id']}/file-url/", **self.alice.auth_header()
        )
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_read_url_is_denied(self):
        created = self.submit(self.alice).json()
        response = self.client.get(f"/api/submissions/{created['id']}/file-url/")
        self.assertEqual(response.status_code, 401)

    def test_owner_gets_a_working_signed_url(self):
        import urllib.request

        created = self.submit(self.alice).json()
        response = self.client.get(
            f"/api/submissions/{created['id']}/file-url/", **self.alice.auth_header()
        )
        self.assertEqual(response.status_code, 200)
        url = response.json()["url"]
        self.assertIn("token=", url)

        # The link really resolves to the real stored PDF.
        with urllib.request.urlopen(url, timeout=30) as fetched:
            self.assertEqual(fetched.status, 200)
            self.assertTrue(fetched.read(5).startswith(b"%PDF-"))

    def test_reviewer_sees_all_submissions_oldest_first(self):
        self.submit(self.alice, title="First")
        self.submit(self.bob, title="Second")
        titles = [
            row["title"]
            for row in self.client.get("/api/submissions/", **self.reviewer.auth_header()).json()["results"]
        ]
        self.assertEqual(titles, ["First", "Second"])

    def test_counts_are_not_narrowed_by_the_status_filter(self):
        self.submit(self.alice, title="One")
        self.submit(self.alice, title="Two")

        unfiltered = self.client.get("/api/submissions/", **self.alice.auth_header()).json()
        filtered = self.client.get(
            "/api/submissions/?status=approved", **self.alice.auth_header()
        ).json()

        self.assertEqual(filtered["results"], [])
        self.assertEqual(filtered["counts"], unfiltered["counts"])
        self.assertEqual(filtered["counts"]["pending"], 2)

    def test_malformed_status_filter_is_a_clear_error(self):
        response = self.client.get("/api/submissions/?status=banana", **self.alice.auth_header())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_status_filter")

    # --- deciding ---------------------------------------------------------

    def test_reviewer_approves_and_the_actor_and_time_are_recorded(self):
        created = self.submit(self.alice).json()
        response = self.client.post(
            f"/api/submissions/{created['id']}/decision/",
            {"decision": "approve", "note": "Looks good."},
            format="json",
            **self.reviewer.auth_header(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], Status.APPROVED)
        self.assertEqual(body["reviewed_by"]["email"], self.reviewer.email)
        self.assertIsNotNone(body["reviewed_at"])
        self.assertEqual(body["decision_note"], "Looks good.")

    def test_rejection_requires_a_reason(self):
        created = self.submit(self.alice).json()
        response = self.client.post(
            f"/api/submissions/{created['id']}/decision/",
            {"decision": "reject", "note": "   "},
            format="json",
            **self.reviewer.auth_header(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "rejection_note_required")
        self.assertEqual(Submission.objects.get(id=created["id"]).status, Status.PENDING)

    def test_submitter_cannot_decide(self):
        created = self.submit(self.alice).json()
        response = self.client.post(
            f"/api/submissions/{created['id']}/decision/",
            {"decision": "approve"},
            format="json",
            **self.alice.auth_header(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.get(id=created["id"]).status, Status.PENDING)

    def test_second_decision_conflicts_and_preserves_the_first(self):
        created = self.submit(self.alice).json()
        header = self.reviewer.auth_header()

        first = self.client.post(
            f"/api/submissions/{created['id']}/decision/",
            {"decision": "approve", "note": "First wins."},
            format="json",
            **header,
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            f"/api/submissions/{created['id']}/decision/",
            {"decision": "reject", "note": "Should not overwrite."},
            format="json",
            **header,
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "already_decided")

        stored = Submission.objects.get(id=created["id"])
        self.assertEqual(stored.status, Status.APPROVED)
        self.assertEqual(stored.decision_note, "First wins.")

    def test_decision_on_a_missing_submission_is_404(self):
        response = self.client.post(
            "/api/submissions/00000000-0000-0000-0000-000000000000/decision/",
            {"decision": "approve"},
            format="json",
            **self.reviewer.auth_header(),
        )
        self.assertEqual(response.status_code, 404)
