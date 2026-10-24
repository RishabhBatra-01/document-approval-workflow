"""Application identity.

A Supabase Auth user is *authentication*. A Profile is *authorization*. The two
are deliberately separate: someone can hold a perfectly valid Supabase session
and still have no Profile, in which case this application refuses them. Roles
live here, in a table only the backend can write, never in Auth user metadata —
user metadata is editable by the user it belongs to.
"""

import uuid

from django.db import models


class Role(models.TextChoices):
    SUBMITTER = "submitter", "Submitter"
    REVIEWER = "reviewer", "Reviewer"


class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The verified Supabase Auth user id. Unique, so one Auth user maps to at
    # most one application identity. Not a FK: Supabase owns auth.users and
    # Django migrations must not reach into it.
    auth_user_id = models.UUIDField(unique=True, db_index=True)

    email = models.EmailField(max_length=320)
    display_name = models.CharField(max_length=120)
    role = models.CharField(max_length=16, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_profile"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[Role.SUBMITTER, Role.REVIEWER]),
                name="profile_role_valid",
            )
        ]

    def __str__(self) -> str:
        return f"{self.display_name} <{self.email}> ({self.role})"

    @property
    def is_reviewer(self) -> bool:
        return self.role == Role.REVIEWER

    @property
    def is_submitter(self) -> bool:
        return self.role == Role.SUBMITTER

    # DRF calls this on request.user. A Profile only ever exists for a verified
    # Auth user, so reaching this point means authentication already succeeded.
    @property
    def is_authenticated(self) -> bool:
        return True
