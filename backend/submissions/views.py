"""HTTP layer. Authorization decisions live in the queryset, not in the UI."""

from __future__ import annotations

import logging

from django.db import DatabaseError
from rest_framework import status as http_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Role
from config.errors import ApiError, error_response
from integrations.supabase_storage import StorageUnavailable, get_storage
from submissions.models import Status, Submission
from submissions.permissions import IsReviewer
from submissions.serializers import (
    DecisionSerializer,
    SubmissionCreateSerializer,
    SubmissionSerializer,
    status_counts_from,
)
from submissions.services import create_submission, decide_submission
from submissions.validation import FileRejected

logger = logging.getLogger(__name__)


def visible_submissions(profile):
    """The caller's authorized set.

    This single function is what stops one submitter reading another's
    documents. Every read path goes through it, so a missed check in a view
    cannot widen access. A submitter asking for someone else's id gets an empty
    queryset, which becomes a 404 — the same answer as a document that does not
    exist, so the response never reveals that another user's document is there.
    """
    base = Submission.objects.select_related("submitted_by", "reviewed_by")
    if profile.role == Role.REVIEWER:
        return base
    return base.filter(submitted_by=profile)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def submissions_collection(request):
    if request.method == "GET":
        return _list_submissions(request)
    return _create_submission(request)


def _list_submissions(request):
    profile = request.user

    requested_status = request.query_params.get("status")
    if requested_status and requested_status != "all":
        valid = {s.value for s in Status}
        if requested_status not in valid:
            raise ApiError(
                "invalid_status_filter",
                f"Unknown status filter. Expected one of: {', '.join(sorted(valid))}.",
                400,
                {"status": ["Unrecognised value."]},
            )

    # Reviewers work a queue: oldest first. Submitters track their own recent
    # work: newest first. Both tie-break on id so ordering is deterministic.
    authorized = visible_submissions(profile)
    if profile.role == Role.REVIEWER:
        authorized = authorized.order_by("created_at", "id")
    else:
        authorized = authorized.order_by("-created_at", "-id")

    # One database round trip, not two.
    #
    # Counting with a separate aggregate query cost a second round trip to the
    # database's region — measured at ~156ms, which is most of what this
    # endpoint spends. There is no pagination, so every authorized row is being
    # fetched anyway; counting and filtering them here is free by comparison.
    #
    # It also makes the counts structurally honest: they are derived from the
    # very rows being returned, so they cannot disagree with the data.
    #
    # This trade is only sound while the result set is small. Adding pagination
    # means going back to an aggregate query for the counts.
    all_rows = list(authorized)
    counts = status_counts_from(all_rows)

    rows = (
        [row for row in all_rows if row.status == requested_status]
        if requested_status and requested_status != "all"
        else all_rows
    )

    return Response(
        {"results": SubmissionSerializer(rows, many=True).data, "counts": counts}
    )


def _create_submission(request):
    # Checked here rather than with a permission class: this is a helper, not a
    # view, so a decorator on it would look like a guard without being one.
    if request.user.role != Role.SUBMITTER:
        raise ApiError("forbidden_role", "Only submitters can create submissions.", 403)

    serializer = SubmissionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        submission = create_submission(
            profile=request.user,
            title=data["title"].strip(),
            context=(data.get("context") or "").strip(),
            upload=data["file"],
        )
    except FileRejected as exc:
        return error_response(exc.code, exc.message, exc.http_status, {"file": [exc.message]})
    except StorageUnavailable:
        return error_response(
            "storage_unavailable",
            "The document could not be stored. Your details were kept — please try again.",
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except DatabaseError:
        return error_response(
            "submission_not_saved",
            "The document could not be saved. Your details were kept — please try again.",
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(SubmissionSerializer(submission).data, status=http_status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def submission_detail(request, submission_id):
    submission = visible_submissions(request.user).filter(id=submission_id).first()
    if submission is None:
        raise ApiError("not_found", "That submission could not be found.", 404)
    return Response(SubmissionSerializer(submission).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def submission_file_url(request, submission_id):
    """Mint a short-lived read URL, only after checking access."""
    submission = visible_submissions(request.user).filter(id=submission_id).first()
    if submission is None:
        raise ApiError("not_found", "That submission could not be found.", 404)

    try:
        signed = get_storage().create_signed_url(submission.storage_object_key)
    except StorageUnavailable:
        return error_response(
            "storage_unavailable",
            "The document could not be opened right now. Please try again.",
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # The URL itself is never logged or persisted — it is a bearer link.
    return Response({"url": signed.url, "expires_at": signed.expires_at.isoformat()})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsReviewer])
def submission_decision(request, submission_id):
    # Reviewers see everything, so existence and authorization coincide here.
    if not Submission.objects.filter(id=submission_id).exists():
        raise ApiError("not_found", "That submission could not be found.", 404)

    serializer = DecisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    submission = decide_submission(
        submission_id=submission_id,
        reviewer=request.user,
        decision=serializer.validated_data["decision"],
        note=serializer.validated_data.get("note", ""),
    )
    return Response(SubmissionSerializer(submission).data)
