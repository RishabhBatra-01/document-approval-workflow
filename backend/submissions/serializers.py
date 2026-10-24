"""Request validation and response shaping."""

from django.conf import settings
from rest_framework import serializers

from submissions.models import Status, Submission


class SubmissionCreateSerializer(serializers.Serializer):
    # Trimmed before length is judged, so "   " is blank rather than length 3.
    title = serializers.CharField(
        max_length=settings.MAX_TITLE_LENGTH, trim_whitespace=True, allow_blank=False
    )
    context = serializers.CharField(
        max_length=settings.MAX_NOTE_LENGTH, required=False, allow_blank=True, default=""
    )
    file = serializers.FileField()


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(
        max_length=settings.MAX_NOTE_LENGTH, required=False, allow_blank=True, default=""
    )


class ProfileSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()


class SubmissionSerializer(serializers.ModelSerializer):
    submitted_by = ProfileSummarySerializer(read_only=True)
    reviewed_by = ProfileSummarySerializer(read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "title",
            "context",
            "status",
            "original_filename",
            "file_size_bytes",
            "content_type",
            "created_at",
            "submitted_by",
            "reviewed_by",
            "reviewed_at",
            "decision_note",
        ]
        # Everything is read-only: submissions are immutable once created, and
        # the only mutation is the decision, which has its own endpoint.
        read_only_fields = fields


def status_counts_from(rows) -> dict:
    """Counts across the caller's whole authorized set.

    Takes the already-fetched rows rather than a queryset, so counting costs
    no extra database round trip. Deliberately computed before any status
    filter is applied — deriving these from a filtered subset would make every
    tab report only its own size.
    """
    counts = {status.value: 0 for status in Status}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    counts["all"] = sum(counts[s.value] for s in Status)
    return counts
