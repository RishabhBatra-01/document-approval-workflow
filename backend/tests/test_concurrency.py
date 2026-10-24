"""A genuine simultaneous-decision race against real PostgreSQL.

TransactionTestCase, not TestCase: the default TestCase wraps each test in a
transaction that is never committed, so concurrent threads would not see one
another's writes and the race would be invisible. This class commits for real.
"""

from __future__ import annotations

import threading

from django.db import connections
from django.test import TransactionTestCase

from config.errors import ApiError
from submissions.models import Status, Submission
from submissions.services import decide_submission
from tests.support import (
    assert_safe_test_project,
    cleanup_storage_object,
    make_reviewer,
    make_submitter,
    real_pdf_bytes,
    upload_file,
)
from submissions.services import create_submission


class ConcurrentDecisionTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_test_project()
        super().setUpClass()

    def setUp(self):
        self.accounts = []
        self.object_keys = []
        self.submitter = self._track(make_submitter("race-sub"))
        self.reviewer_a = self._track(make_reviewer("race-a"))
        self.reviewer_b = self._track(make_reviewer("race-b"))

    def tearDown(self):
        for key in self.object_keys:
            cleanup_storage_object(key)
        for account in self.accounts:
            account.destroy()

    def _track(self, account):
        self.accounts.append(account)
        return account

    def _new_pending(self) -> Submission:
        submission = create_submission(
            profile=self.submitter.profile,
            title="Race subject",
            context="",
            upload=upload_file(real_pdf_bytes()),
        )
        self.object_keys.append(submission.storage_object_key)
        return submission

    def _run_simultaneously(self, submission_id, attempts):
        """Fire every decision at once and collect what each one got back."""
        results: list[tuple[str, object]] = []
        lock = threading.Lock()
        # Released only when every thread is parked at the same point, so the
        # requests genuinely overlap rather than queueing.
        start = threading.Barrier(len(attempts))

        def attempt(reviewer, decision, note):
            try:
                start.wait(timeout=30)
                decided = decide_submission(
                    submission_id=submission_id, reviewer=reviewer, decision=decision, note=note
                )
                with lock:
                    results.append(("ok", decided.status))
            except ApiError as exc:
                with lock:
                    results.append(("error", exc.code))
            except Exception as exc:  # noqa: BLE001
                with lock:
                    results.append(("unexpected", repr(exc)))
            finally:
                # Each thread owns its own connection; leaking them exhausts
                # the pooler.
                connections.close_all()

        threads = [threading.Thread(target=attempt, args=a) for a in attempts]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return results

    def test_two_opposing_decisions_at_once_leave_exactly_one_winner(self):
        submission = self._new_pending()

        results = self._run_simultaneously(
            submission.id,
            [
                (self.reviewer_a.profile, "approve", "Approved by A."),
                (self.reviewer_b.profile, "reject", "Rejected by B."),
            ],
        )

        self.assertNotIn("unexpected", [kind for kind, _ in results], results)
        successes = [value for kind, value in results if kind == "ok"]
        conflicts = [value for kind, value in results if kind == "error"]

        self.assertEqual(len(successes), 1, f"exactly one decision must win: {results}")
        self.assertEqual(conflicts, ["already_decided"])

        stored = Submission.objects.get(id=submission.id)
        self.assertEqual(stored.status, successes[0])
        # The loser must not have partially overwritten the winner.
        if stored.status == Status.APPROVED:
            self.assertEqual(stored.decision_note, "Approved by A.")
            self.assertEqual(stored.reviewed_by_id, self.reviewer_a.profile.id)
        else:
            self.assertEqual(stored.decision_note, "Rejected by B.")
            self.assertEqual(stored.reviewed_by_id, self.reviewer_b.profile.id)

    def test_five_simultaneous_approvals_produce_one_decision(self):
        submission = self._new_pending()

        results = self._run_simultaneously(
            submission.id,
            [(self.reviewer_a.profile, "approve", f"Attempt {i}") for i in range(5)],
        )

        successes = [v for kind, v in results if kind == "ok"]
        conflicts = [v for kind, v in results if kind == "error"]

        self.assertEqual(len(successes), 1, f"{results}")
        self.assertEqual(len(conflicts), 4)
        self.assertTrue(all(code == "already_decided" for code in conflicts))

        stored = Submission.objects.get(id=submission.id)
        self.assertEqual(stored.status, Status.APPROVED)
        self.assertIsNotNone(stored.reviewed_at)

    def test_a_decision_after_the_race_still_conflicts(self):
        submission = self._new_pending()
        decide_submission(
            submission_id=submission.id,
            reviewer=self.reviewer_a.profile,
            decision="approve",
            note="First.",
        )

        with self.assertRaises(ApiError) as caught:
            decide_submission(
                submission_id=submission.id,
                reviewer=self.reviewer_b.profile,
                decision="reject",
                note="Too late.",
            )
        self.assertEqual(caught.exception.code, "already_decided")
        self.assertEqual(caught.exception.http_status, 409)
        self.assertEqual(Submission.objects.get(id=submission.id).decision_note, "First.")
