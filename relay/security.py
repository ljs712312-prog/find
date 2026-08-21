"""Request authentication primitives for the BuildingHUB relay."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any


class AuthenticationError(RuntimeError):
    """The caller did not present one valid, fresh, unused HMAC request."""


class JSONBodyError(ValueError):
    """The request body is not an unambiguous JSON object."""


class _DuplicateJSONKeyError(ValueError):
    pass


_EPOCH_SECONDS = re.compile(r"[1-9][0-9]{9,10}\Z")
_NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{64}\Z")


def load_json_object(body: bytes) -> dict[str, Any]:
    """Decode a small JSON object while rejecting duplicate and NaN values."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise JSONBodyError("request body must be UTF-8 JSON") from error

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_without_duplicate_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, _DuplicateJSONKeyError, ValueError) as error:
        raise JSONBodyError("request body must be valid unambiguous JSON") from error

    if not isinstance(decoded, dict):
        raise JSONBodyError("request body must be a JSON object")
    return decoded


def canonical_json(value: Mapping[str, Any]) -> str:
    """Return the precise JSON serialization covered by the HMAC signature."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def make_signature(
    secret: bytes, *, timestamp: str, nonce: str, endpoint: str, body: Mapping[str, Any]
) -> str:
    """Return the lowercase hexadecimal HMAC required by the wire contract."""

    signing_bytes = "\n".join(
        (timestamp, nonce, endpoint, canonical_json(body))
    ).encode("utf-8")
    return hmac.new(secret, signing_bytes, hashlib.sha256).hexdigest()


class NonceStore:
    """Bounded per-process replay cache.

    Cloud Run's service is deployed with one Uvicorn worker.  The cache is
    intentionally process-local so no customer data or secret has to be sent
    to another service.  A horizontally scaled deployment should replace this
    class with a shared atomic store before relying on it for cross-instance
    replay prevention.
    """

    def __init__(self, *, ttl_seconds: int, maximum_entries: int = 20_000) -> None:
        self._ttl_seconds = ttl_seconds
        self._maximum_entries = maximum_entries
        self._entries: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def consume(self, nonce: str, *, now: float) -> bool:
        """Atomically record *nonce*, returning false when it was already used."""

        async with self._lock:
            expired = [key for key, expires_at in self._entries.items() if expires_at <= now]
            for key in expired:
                del self._entries[key]
            if nonce in self._entries or len(self._entries) >= self._maximum_entries:
                return False
            self._entries[nonce] = now + self._ttl_seconds
            return True


async def authenticate_request(
    *,
    headers: Mapping[str, str],
    endpoint: str,
    body: Mapping[str, Any],
    secret: bytes,
    max_clock_skew_seconds: int,
    nonce_store: NonceStore,
    clock: Callable[[], float] = time.time,
) -> None:
    """Authenticate one request using timestamp, nonce, and HMAC-SHA256.

    All authentication failures deliberately collapse into the same exception,
    so an unauthenticated caller cannot learn whether a nonce was previously
    valid or a signature almost matched.
    """

    timestamp = str(headers.get("x-building-hub-timestamp", ""))
    nonce = str(headers.get("x-building-hub-nonce", ""))
    signature = str(headers.get("x-building-hub-signature", ""))
    now = clock()

    if not _EPOCH_SECONDS.fullmatch(timestamp):
        raise AuthenticationError("invalid request authentication")
    try:
        timestamp_value = int(timestamp)
    except ValueError:  # Defensive; the regular expression already checked this.
        raise AuthenticationError("invalid request authentication") from None
    if abs(now - timestamp_value) > max_clock_skew_seconds:
        raise AuthenticationError("invalid request authentication")
    if not _NONCE.fullmatch(nonce) or not _SIGNATURE.fullmatch(signature):
        raise AuthenticationError("invalid request authentication")

    expected = make_signature(
        secret,
        timestamp=timestamp,
        nonce=nonce,
        endpoint=endpoint,
        body=body,
    )
    if not hmac.compare_digest(expected, signature):
        raise AuthenticationError("invalid request authentication")
    if not await nonce_store.consume(nonce, now=now):
        raise AuthenticationError("invalid request authentication")


def _without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKeyError(key)
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")
