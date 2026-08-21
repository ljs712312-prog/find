"""Narrow, retrying client for the one approved BuildingHUB origin."""

from __future__ import annotations

import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, quote_plus

import httpx

from .config import UPSTREAM_BASE_URL, RelaySettings

LOGGER = logging.getLogger(__name__)


# Keep this list aligned with the official BldRgstHubService operations the
# Streamlit app uses.  It is deliberately not configurable at runtime.
ALLOWED_ENDPOINTS = frozenset(
    {
        "getBrTitleInfo",
        "getBrBasisOulnInfo",
        "getBrFlrOulnInfo",
        "getBrExposPubuseAreaInfo",
        "getBrHsprcInfo",
        "getBrExposInfo",
        "getBrWclfInfo",
        "getBrRecapTitleInfo",
        "getBrAtchJibunInfo",
        "getBrJijiguInfo",
    }
)


class UpstreamUnavailable(RuntimeError):
    """A retryable connection or gateway problem prevented a response."""

    def __init__(self, *, endpoint: str, attempts: int, category: str) -> None:
        self.endpoint = endpoint
        self.attempts = attempts
        self.category = category
        super().__init__("BuildingHUB upstream is temporarily unavailable")


class UpstreamInvalidResponse(RuntimeError):
    """The fixed upstream sent oversized or malformed data."""


@dataclass(frozen=True)
class UpstreamResponse:
    """A validated, service-key-redacted upstream response envelope."""

    status_code: int
    body: bytes
    media_type: str


Sleep = Callable[[float], Awaitable[None]]


class BuildingHubUpstream:
    """Fetch only fixed-origin GET requests with a server-held service key."""

    def __init__(
        self,
        settings: RelaySettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        timeout = httpx.Timeout(
            connect=settings.upstream_connect_timeout_seconds,
            read=settings.upstream_read_timeout_seconds,
            write=10.0,
            pool=5.0,
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={
                "Accept": "application/json, application/xml;q=0.9",
                "User-Agent": "won-top-buildinghub-relay/1.0",
            },
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(
        self, *, endpoint: str, params: Mapping[str, Any], response_type: str
    ) -> UpstreamResponse:
        """Fetch one documented page and return its JSON or XML envelope.

        The input has already been schema-validated by ``relay.app``.  The
        relay owns serviceKey, destination host, HTTP method, and headers; the
        caller cannot turn this into an open proxy.
        """

        if endpoint not in ALLOWED_ENDPOINTS:
            raise ValueError("endpoint is not allowed")
        request_params = dict(params)
        request_params["serviceKey"] = self._settings.service_key
        url = f"{UPSTREAM_BASE_URL}/{endpoint}"

        for attempt in range(self._settings.upstream_max_retries + 1):
            try:
                status_code, headers, body = await self._request(url, request_params)
            except httpx.RequestError as error:
                if attempt < self._settings.upstream_max_retries:
                    await self._backoff(attempt)
                    continue
                category = _request_error_category(error)
                LOGGER.warning(
                    "BuildingHUB relay transport failure endpoint=%s attempts=%s category=%s",
                    endpoint,
                    attempt + 1,
                    category,
                )
                raise UpstreamUnavailable(
                    endpoint=endpoint, attempts=attempt + 1, category=category
                ) from None
            except UpstreamInvalidResponse:
                # Retrying malformed or oversized data cannot make it safe.
                raise

            if status_code in {429, 502, 503, 504} or 500 <= status_code <= 599:
                if attempt < self._settings.upstream_max_retries:
                    await self._backoff(attempt, _retry_after_seconds(headers))
                    continue
                LOGGER.warning(
                    "BuildingHUB relay gateway failure endpoint=%s attempts=%s status=%s",
                    endpoint,
                    attempt + 1,
                    status_code,
                )
                raise UpstreamUnavailable(
                    endpoint=endpoint,
                    attempts=attempt + 1,
                    category="gateway",
                )

            if 300 <= status_code <= 399:
                # A redirect would be an unreviewed destination.  Never follow
                # or expose it, even if a proxy inserts one in front of the API.
                raise UpstreamInvalidResponse("BuildingHUB returned an unexpected redirect")

            media_type = _validated_media_type(body, headers, expected=response_type)
            return UpstreamResponse(
                status_code=status_code,
                body=_redact_bytes(body, self._settings.service_key),
                media_type=media_type,
            )

        raise AssertionError("unreachable retry loop")

    async def _request(
        self, url: str, params: Mapping[str, Any]
    ) -> tuple[int, httpx.Headers, bytes]:
        # Streaming lets us enforce an upper response bound before retaining an
        # unexpectedly large body in memory.
        async with self._client.stream("GET", url, params=params) as response:
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self._settings.max_response_bytes:
                    raise UpstreamInvalidResponse("BuildingHUB response exceeds size limit")
                chunks.append(chunk)
            return response.status_code, response.headers, b"".join(chunks)

    async def _backoff(self, attempt: int, retry_after: float | None = None) -> None:
        delay = retry_after
        if delay is None:
            delay = self._settings.upstream_backoff_seconds * (2**attempt)
        await self._sleep(min(max(float(delay), 0.0), 30.0))


def _validated_media_type(body: bytes, headers: httpx.Headers, *, expected: str) -> str:
    """Accept only valid API JSON/XML envelopes, never arbitrary HTML/text."""

    if not body.strip():
        raise UpstreamInvalidResponse("BuildingHUB returned an empty response")

    declared = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    stripped = body.lstrip(b"\xef\xbb\xbf \t\r\n")
    looks_json = declared.endswith("json") or stripped.startswith((b"{", b"["))
    looks_xml = declared in {"application/xml", "text/xml"} or stripped.startswith(b"<")

    if looks_json:
        try:
            decoded = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UpstreamInvalidResponse("BuildingHUB returned malformed JSON") from error
        if not isinstance(decoded, dict):
            raise UpstreamInvalidResponse("BuildingHUB JSON envelope must be an object")
        return "application/json"

    if looks_xml:
        try:
            ET.fromstring(stripped)
        except ET.ParseError as error:
            raise UpstreamInvalidResponse("BuildingHUB returned malformed XML") from error
        return "application/xml"

    # Even a request that asks for XML can receive a JSON gateway error (and
    # vice versa), so detection is intentionally content based.  ``expected``
    # is retained to make the caller's allowed format explicit in this API.
    del expected
    raise UpstreamInvalidResponse("BuildingHUB response was not JSON or XML")


def _redact_bytes(body: bytes, service_key: str) -> bytes:
    """Defence in depth for unusual gateway messages that echo credentials."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        # JSON/XML validation already decoded the body above; this branch is
        # only a defensive fallback and must not leak undecodable bytes.
        return b"[REDACTED_UPSTREAM_BODY]"

    for candidate in {
        service_key,
        quote(service_key, safe=""),
        quote_plus(service_key, safe=""),
    }:
        if candidate:
            text = text.replace(candidate, "[REDACTED]")
    return text.encode("utf-8")


def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _request_error_category(error: httpx.RequestError) -> str:
    """Return stable diagnostics without retaining URL-bearing exception text."""

    if isinstance(error, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(error, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.ConnectError):
        return "connection"
    if isinstance(error, httpx.RemoteProtocolError):
        return "protocol"
    return "request"
