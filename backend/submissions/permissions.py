"""Role gates.

Roles are exclusive in this version: a submitter cannot decide, and a reviewer
cannot submit. Both are enforced here, on the server, regardless of what the
frontend chooses to render.
"""

from rest_framework.permissions import BasePermission

from accounts.models import Role


class IsSubmitter(BasePermission):
    message = "Only submitters can create submissions."

    def has_permission(self, request, view):
        return getattr(request.user, "role", None) == Role.SUBMITTER


class IsReviewer(BasePermission):
    message = "Only reviewers can decide submissions."

    def has_permission(self, request, view):
        return getattr(request.user, "role", None) == Role.REVIEWER
