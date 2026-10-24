"""The two operations that change state.

Kept out of the views so the rules are readable in one place and testable
without HTTP.
"""

from __future__ import annotations

import logging

from django.db import DatabaseError, transaction
from django.utils import timezone

from accounts.models import Profile
from config.errors import ApiError
from integrations.supabase_storage import StorageUnavailable, build_object_key, get_storage
from submissions.models import Status, Submission
from submissions.validation import FileRejected, validate_upload

logger = logging.getLogger(__name__)


def create_submission(
    *, profile: Profile, title: str, context: str, upload, storage=None
) -> Submission:
    """Validate, upload, then commit.

    Storage and PostgreSQL are two systems and cannot share a transaction. The
    order is chosen so the failure mode is recoverable: upload first, then
    write the row. If the row fails we try to delete the object. If that delete
    also fails we log it loudly with the key, because a human must clean it up.

    The reverse order would be worse: a row pointing at an object that does not
    exist is visible to users, whereas an orphaned object is invisible to them.
    """
    storage = storage or get_storage()

    content = upload.read()
    checked = validate_upload(content, upload.name)  # raises FileRejected

    # Everything after this point uses what the bytes proved to be, never what
    # the upload claimed: the stored extension, the recorded content type and
    # the bytes themselves (images have had their metadata removed).
    object_key = build_object_key(profile.id, checked.extension)
    storage.upload(object_key, checked.content, checked.content_type)

    try:
        with transaction.atomic():
            submission = Submission.objects.create(
                title=title,
                context=context,
                # Ownership comes from the verified session, never from the
                # request body. A client-supplied owner or status is ignored.
                submitted_by=profile,
                original_filename=upload.name[:255],
                storage_object_key=object_key,
                file_size_bytes=len(checked.content),
                content_type=checked.content_type,
                status=Status.PENDING,
            )
    except DatabaseError:
        logger.exception("Database write failed after upload; cleaning up %s", object_key)
        try:
            storage.remove(object_key)
        except StorageUnavailable:
            # Both systems failed. Surface an actionable log; do not pretend
            # this was atomic.
            logger.error(
                "ORPHANED STORAGE OBJECT: bucket object %s was uploaded but its "
                "database record failed and cleanup also failed. Manual removal required.",
                object_key,
            )
        raise

    return submission


def decide_submission(
    *, submission_id, reviewer: Profile, decision: str, note: str
) -> Submission:
    """Approve or reject, exactly once.

    The update is a single conditional UPDATE filtered on status='pending'.
    Whoever's statement matches the row first wins; a second or concurrent
    decision matches zero rows and is reported as a conflict. There is no
    read-then-save window for two requests to slip through.
    """
    if decision not in {"approve", "reject"}:
        raise ApiError(
            "invalid_decision",
            "Decision must be either 'approve' or 'reject'.",
            400,
            {"decision": ["Must be 'approve' or 'reject'."]},
        )

    note = (note or "").strip()
    if decision == "reject" and not note:
        raise ApiError(
            "rejection_note_required",
            "A rejection must explain what is wrong.",
            400,
            {"note": ["Required when rejecting."]},
        )

    new_status = Status.APPROVED if decision == "approve" else Status.REJECTED
    decided_at = timezone.now()

    matched = Submission.objects.filter(id=submission_id, status=Status.PENDING).update(
        status=new_status,
        reviewed_by=reviewer,
        reviewed_at=decided_at,
        decision_note=note,
    )

    if matched == 0:
        # Either it does not exist, or someone already decided it. Load it to
        # tell the two apart, and return the real saved outcome so the UI can
        # show what actually happened rather than guessing.
        existing = Submission.objects.filter(id=submission_id).first()
        if existing is None:
            raise ApiError("not_found", "That submission could not be found.", 404)
        raise ApiError(
            "already_decided",
            f"This submission was already {existing.status}.",
            409,
        )

    return Submission.objects.select_related("submitted_by", "reviewed_by").get(id=submission_id)
