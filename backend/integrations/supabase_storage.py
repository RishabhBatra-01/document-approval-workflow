"""Private Supabase Storage access.

Only this module talks to Storage, and only the backend holds the credential
that can. The browser never uploads or lists directly; it receives a signed
read URL after Django has checked that the caller is allowed to have one.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from django.conf import settings
from supabase import Client, create_client

logger = logging.getLogger(__name__)


class StorageUnavailable(Exception):
    """Storage could not be reached or refused the operation."""


@dataclass(frozen=True)
class SignedUrl:
    url: str
    expires_at: datetime


def build_object_key(profile_id, extension: str = ".pdf") -> str:
    """Generate the storage path.

    The user's filename is never part of the key: it is attacker-controlled and
    would permit path traversal and collisions. The key is derived from the
    owner and a fresh UUID, which also makes keys unguessable.

    The extension comes from what validation proved the bytes to be, never
    from what the upload claimed to be called.
    """
    safe = extension if extension.startswith(".") else f".{extension}"
    return f"submissions/{profile_id}/{uuid.uuid4()}{safe}"


class SupabaseStorage:
    def __init__(self, url: str | None = None, secret_key: str | None = None, bucket: str | None = None):
        self._url = url or settings.SUPABASE_URL
        self._secret_key = secret_key or settings.SUPABASE_SECRET_KEY
        self._bucket_name = bucket or settings.SUPABASE_STORAGE_BUCKET
        self._client: Client | None = None

    @property
    def _bucket(self):
        if self._client is None:
            self._client = create_client(self._url, self._secret_key)
        return self._client.storage.from_(self._bucket_name)

    def upload(self, object_key: str, content: bytes, content_type: str = "application/pdf") -> None:
        try:
            self._bucket.upload(
                path=object_key,
                file=content,
                file_options={"content-type": content_type, "upsert": "false"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
            raise StorageUnavailable("Storage service is unreachable.") from exc
        except Exception as exc:  # noqa: BLE001 - SDK raises varied storage errors
            logger.warning("Storage upload failed for %s: %s", object_key, type(exc).__name__)
            raise StorageUnavailable("Storage rejected the upload.") from exc

    def remove(self, object_key: str) -> None:
        """Delete an object, and insist that it actually happened.

        Supabase answers a delete with HTTP 200 and an empty list whether the
        object was removed, the object did not exist, or the bucket itself does
        not exist — it does not raise. Measured against the real API.

        So the response has to be inspected. Treating the call as successful
        because it did not throw would let a failed cleanup look like a
        successful one, and the orphaned object would never be reported.
        """
        try:
            removed = self._bucket.remove([object_key])
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
            raise StorageUnavailable("Storage service is unreachable.") from exc
        except Exception as exc:  # noqa: BLE001
            raise StorageUnavailable("Storage refused the delete.") from exc

        if not removed:
            raise StorageUnavailable(
                f"Storage reported no object deleted for key {object_key}."
            )

    def create_signed_url(self, object_key: str, expires_in: int | None = None) -> SignedUrl:
        """Mint a short-lived read link.

        This is a bearer link: anyone holding it can read the object until it
        expires. It is generated on demand, never stored on the record and
        never logged.
        """
        ttl = expires_in or settings.SUPABASE_SIGNED_URL_TTL
        try:
            response = self._bucket.create_signed_url(object_key, ttl)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
            raise StorageUnavailable("Storage service is unreachable.") from exc
        except Exception as exc:  # noqa: BLE001
            raise StorageUnavailable("Storage could not sign a URL.") from exc

        url = response.get("signedURL") or response.get("signedUrl") if isinstance(response, dict) else None
        if not url:
            raise StorageUnavailable("Storage returned no signed URL.")

        expires_at = datetime.fromtimestamp(
            datetime.now(tz=timezone.utc).timestamp() + ttl, tz=timezone.utc
        )
        return SignedUrl(url=url, expires_at=expires_at)


_default_storage: SupabaseStorage | None = None


def get_storage() -> SupabaseStorage:
    global _default_storage
    if _default_storage is None:
        _default_storage = SupabaseStorage()
    return _default_storage
