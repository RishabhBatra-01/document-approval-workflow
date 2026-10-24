"""Verification of Supabase access tokens.

The seam that keeps token verification swappable and testable. It does exactly
one thing: given a raw access token, return the verified Auth user id, or raise.

Two failures are deliberately distinguished:
  InvalidToken   -> the caller's token is bad        -> 401, do not retry
  AuthUnavailable-> Supabase could not be reached    -> 503, retrying may work
Collapsing them would log users out during an outage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from django.conf import settings
from supabase import Client, create_client

logger = logging.getLogger(__name__)


class InvalidToken(Exception):
    """The token is absent, malformed, expired, or revoked."""


class AuthUnavailable(Exception):
    """Supabase Auth could not be reached. A temporary condition."""


@dataclass(frozen=True)
class VerifiedUser:
    auth_user_id: str
    email: str


class SupabaseAuthVerifier:
    """Verifies tokens against the configured Supabase project."""

    def __init__(self, url: str | None = None, secret_key: str | None = None):
        self._url = url or settings.SUPABASE_URL
        self._secret_key = secret_key or settings.SUPABASE_SECRET_KEY
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        # One shared client. Its session is never mutated with a user's token;
        # the token is passed per call, so concurrent requests cannot bleed
        # into one another.
        if self._client is None:
            self._client = create_client(self._url, self._secret_key)
        return self._client

    def verify(self, access_token: str) -> VerifiedUser:
        if not access_token or not access_token.strip():
            raise InvalidToken("No access token supplied.")

        try:
            response = self.client.auth.get_user(access_token)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
            # Genuinely could not reach the service.
            logger.warning("Supabase Auth unreachable: %s", type(exc).__name__)
            raise AuthUnavailable("Authentication service is unreachable.") from exc
        except Exception as exc:  # noqa: BLE001 - SDK raises varied auth errors
            status_code = getattr(exc, "status", None) or getattr(exc, "code", None)
            # 5xx from the provider is an outage, not a bad credential.
            if isinstance(status_code, int) and status_code >= 500:
                logger.warning("Supabase Auth returned %s", status_code)
                raise AuthUnavailable("Authentication service is unavailable.") from exc
            raise InvalidToken("Access token is not valid.") from exc

        user = getattr(response, "user", None)
        if user is None or not getattr(user, "id", None):
            raise InvalidToken("Access token did not resolve to a user.")

        return VerifiedUser(auth_user_id=str(user.id), email=getattr(user, "email", "") or "")


_default_verifier: SupabaseAuthVerifier | None = None


def get_verifier() -> SupabaseAuthVerifier:
    global _default_verifier
    if _default_verifier is None:
        _default_verifier = SupabaseAuthVerifier()
    return _default_verifier
