"""The submission record and its one legal state transition."""

import uuid

from django.db import models

from accounts.models import Profile


class Status(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


TERMINAL_STATUSES = frozenset({Status.APPROVED, Status.REJECTED})


class Submission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=150)
    context = models.TextField(max_length=2000, blank=True, default="")

    submitted_by = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="submissions"
    )

    # The name the user's file had. Display only — never used as a storage path,
    # because a filename is attacker-controlled and would allow traversal or
    # collision. Escaped when rendered.
    original_filename = models.CharField(max_length=255)

    # The generated key we actually wrote to. Unique so two rows can never claim
    # the same object.
    storage_object_key = models.CharField(max_length=300, unique=True)

    file_size_bytes = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    reviewed_by = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="decisions", null=True, blank=True
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(max_length=2000, blank=True, default="")

    class Meta:
        db_table = "app_submission"
        # Deterministic even when two rows share a timestamp, so pagination and
        # test assertions cannot flap.
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[Status.PENDING, Status.APPROVED, Status.REJECTED]),
                name="submission_status_valid",
            ),
            # The decision fields move together or not at all. The database
            # refuses a half-written decision even if application code is wrong.
            models.CheckConstraint(
                condition=(
                    models.Q(status=Status.PENDING, reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | models.Q(
                        status__in=[Status.APPROVED, Status.REJECTED],
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                    )
                ),
                name="submission_decision_fields_consistent",
            ),
            # A rejection without a reason is not a valid record.
            models.CheckConstraint(
                condition=~models.Q(status=Status.REJECTED, decision_note=""),
                name="submission_rejection_requires_note",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

    @property
    def is_pending(self) -> bool:
        return self.status == Status.PENDING
