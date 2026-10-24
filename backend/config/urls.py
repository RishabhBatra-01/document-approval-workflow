from django.urls import path

from accounts.views import health, me
from submissions.views import (
    submission_decision,
    submission_detail,
    submission_file_url,
    submissions_collection,
)

urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/me/", me, name="me"),
    path("api/submissions/", submissions_collection, name="submissions"),
    path("api/submissions/<uuid:submission_id>/", submission_detail, name="submission-detail"),
    path("api/submissions/<uuid:submission_id>/file-url/", submission_file_url, name="submission-file-url"),
    path("api/submissions/<uuid:submission_id>/decision/", submission_decision, name="submission-decision"),
]
