"""Create the evaluation accounts.

Repeatable and non-destructive: running it twice does not reset anyone's
password and does not duplicate profiles. Passwords are read from an
interactive prompt or the environment, never from a command-line argument
(which would land in shell history) and never written to a file.

    python manage.py provision_accounts
"""

from __future__ import annotations

import os
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from supabase import create_client

from accounts.models import Profile, Role

# Each account has its own password slug. Keying passwords by role would give
# the two submitters the same password, so compromising one would compromise
# the other and the "submitter A cannot see submitter B" guarantee would rest
# on a shared secret.
ACCOUNTS = [
    ("PROVISION_SUBMITTER_A_EMAIL", "Alex Morgan", Role.SUBMITTER, "SUBMITTER_A"),
    ("PROVISION_SUBMITTER_B_EMAIL", "Priya Shah", Role.SUBMITTER, "SUBMITTER_B"),
    ("PROVISION_REVIEWER_EMAIL", "Sam Patel", Role.REVIEWER, "REVIEWER"),
]


class Command(BaseCommand):
    help = "Create or repair the pre-provisioned submitter and reviewer accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password-from-env",
            action="store_true",
            help="Read passwords from PROVISION_PASSWORD_<SLUG> instead of prompting (for CI).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)

        for env_name, display_name, role, slug in ACCOUNTS:
            email = os.environ.get(env_name, "").strip()
            if not email:
                raise CommandError(f"{env_name} is not set in the environment.")

            existing = Profile.objects.filter(email__iexact=email).first()
            if existing:
                # Already provisioned. Leave the Auth password untouched —
                # silently resetting it would lock out whoever is using it.
                self.stdout.write(f"  = {email} already provisioned as {existing.role}")
                continue

            password = self._read_password(email, role, slug, options["password_from_env"])

            auth_user_id = self._ensure_auth_user(client, email, password)

            with transaction.atomic():
                Profile.objects.create(
                    auth_user_id=auth_user_id,
                    email=email,
                    display_name=display_name,
                    role=role,
                )
            self.stdout.write(self.style.SUCCESS(f"  + {email} provisioned as {role}"))

        self.stdout.write(self.style.SUCCESS("Provisioning complete."))

    def _read_password(self, email: str, role: str, slug: str, from_env: bool) -> str:
        if from_env:
            key = f"PROVISION_PASSWORD_{slug}"
            value = os.environ.get(key, "")
            if not value:
                raise CommandError(f"{key} is not set.")
            return value

        password = getpass(f"Password for {email} ({role}): ")
        if len(password) < 10:
            raise CommandError("Choose a password of at least 10 characters.")
        confirm = getpass("Confirm: ")
        if password != confirm:
            raise CommandError("Passwords did not match.")
        return password

    def _ensure_auth_user(self, client, email: str, password: str) -> str:
        """Create the Supabase Auth user, or adopt one that already exists."""
        try:
            created = client.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    # Confirmed server-side: this product sends no email, so an
                    # unconfirmed account could never sign in.
                    "email_confirm": True,
                }
            )
            if created and created.user:
                return str(created.user.id)
        except Exception as exc:  # noqa: BLE001 - SDK raises varied admin errors
            message = str(exc).lower()
            if "already" not in message and "registered" not in message and "exists" not in message:
                raise CommandError(f"Could not create Auth user {email}: {exc}") from exc

        # Already in Auth but missing a Profile — find the id and link it.
        page = client.auth.admin.list_users()
        users = page if isinstance(page, list) else getattr(page, "users", [])
        for user in users:
            if (getattr(user, "email", "") or "").lower() == email.lower():
                return str(user.id)

        raise CommandError(f"Auth user {email} exists but could not be found to link.")
