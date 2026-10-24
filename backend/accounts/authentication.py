"""Turning a Bearer token into an application identity.

The chain is deliberate and every step is checked server-side:

    Bearer token -> Supabase verifies it -> auth user id -> Profile -> role

The browser supplies only the first link. It cannot assert who it is, and it
cannot assert what role it has: the role is read from a table it cannot write.
"""

import logging

from rest_framework.authentication import BaseAuthentication

from accounts.models import Profile
from config.errors import ApiError
from integrations.supabase_auth import AuthUnavailable, InvalidToken, get_verifier

logger = logging.getLogger(__name__)


class SupabaseTokenAuthentication(BaseAuthentication):
    def __init__(self, verifier=None):
        self._verifier = verifier

    @property
    def verifier(self):
        return self._verifier or get_verifier()

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header:
            return None  # DRF turns this into 401 via IsAuthenticated

        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ApiError(
                "invalid_authorization_header",
                "Authorization header must be in the form 'Bearer <token>'.",
                401,
            )

        token = parts[1]

        try:
            verified = self.verifier.verify(token)
        except InvalidToken:
            raise ApiError(
                "invalid_token", "Your session is not valid. Please sign in again.", 401
            ) from None
        except AuthUnavailable:
            # Not the user's fault, and not a reason to sign them out.
            raise ApiError(
                "auth_unavailable",
                "The authentication service is temporarily unavailable. Please try again.",
                503,
            ) from None

        try:
            profile = Profile.objects.get(auth_user_id=verified.auth_user_id)
        except Profile.DoesNotExist:
            # Authenticated with Supabase, but not provisioned in this
            # application. Denied — never auto-created, never given a default
            # role.
            logger.info("Rejected unprovisioned auth user %s", verified.auth_user_id)
            raise ApiError(
                "profile_not_provisioned",
                "This account is not set up for the review workspace. Contact an administrator.",
                403,
            ) from None

        return (profile, token)

    def authenticate_header(self, request):
        return "Bearer"
