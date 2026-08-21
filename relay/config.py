"""Configuration for the BuildingHUB relay.

Only the relay process receives the public-data service key.  Keep this module
small and deliberately avoid configuration knobs that could turn the service
into a general-purpose HTTP proxy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class RelayConfigurationError(RuntimeError):
    """The relay cannot start safely with the supplied configuration."""


UPSTREAM_BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"


@dataclass(frozen=True)
class RelaySettings:
    """Validated, non-sensitive relay settings.

    ``repr=False`` is important here: application start-up failures and debug
    logs must never accidentally render either secret.
    """

    service_key: str = field(repr=False)
    hmac_secret: bytes = field(repr=False)
    max_clock_skew_seconds: int = 300
    upstream_connect_timeout_seconds: float = 4.0
    upstream_read_timeout_seconds: float = 20.0
    upstream_max_retries: int = 2
    upstream_backoff_seconds: float = 0.25
    max_request_bytes: int = 8_192
    max_response_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if not isinstance(self.service_key, str) or not self.service_key.strip():
            raise RelayConfigurationError("DATA_GO_SERVICE_KEY must be configured")
        if not isinstance(self.hmac_secret, bytes) or len(self.hmac_secret) < 32:
            raise RelayConfigurationError(
                "RELAY_HMAC_SECRET must contain at least 32 UTF-8 bytes"
            )
        if not 30 <= self.max_clock_skew_seconds <= 900:
            raise RelayConfigurationError(
                "RELAY_MAX_CLOCK_SKEW_SECONDS must be between 30 and 900"
            )
        if self.upstream_connect_timeout_seconds <= 0:
            raise RelayConfigurationError("upstream connect timeout must be positive")
        if self.upstream_read_timeout_seconds <= 0:
            raise RelayConfigurationError("upstream read timeout must be positive")
        if not 0 <= self.upstream_max_retries <= 4:
            raise RelayConfigurationError("UPSTREAM_MAX_RETRIES must be from 0 to 4")
        if not 0 <= self.upstream_backoff_seconds <= 5:
            raise RelayConfigurationError(
                "UPSTREAM_BACKOFF_SECONDS must be between 0 and 5"
            )
        if not 1_024 <= self.max_request_bytes <= 65_536:
            raise RelayConfigurationError("MAX_REQUEST_BYTES must be from 1024 to 65536")
        if not 10_000 <= self.max_response_bytes <= 10_000_000:
            raise RelayConfigurationError(
                "MAX_RESPONSE_BYTES must be from 10000 to 10000000"
            )

    @property
    def nonce_ttl_seconds(self) -> int:
        """Keep a nonce longer than its complete accepted timestamp window."""

        return (self.max_clock_skew_seconds * 2) + 30

    @classmethod
    def from_environment(cls) -> RelaySettings:
        service_key = os.environ.get("DATA_GO_SERVICE_KEY", "").strip()
        hmac_text = os.environ.get("RELAY_HMAC_SECRET", "")
        if not service_key or not hmac_text:
            raise RelayConfigurationError(
                "DATA_GO_SERVICE_KEY and RELAY_HMAC_SECRET must be configured"
            )

        return cls(
            service_key=service_key,
            hmac_secret=hmac_text.encode("utf-8"),
            max_clock_skew_seconds=_environment_int(
                "RELAY_MAX_CLOCK_SKEW_SECONDS", default=300, minimum=30, maximum=900
            ),
            upstream_connect_timeout_seconds=_environment_float(
                "UPSTREAM_CONNECT_TIMEOUT_SECONDS", default=4.0, minimum=0.1, maximum=60
            ),
            upstream_read_timeout_seconds=_environment_float(
                "UPSTREAM_READ_TIMEOUT_SECONDS", default=20.0, minimum=0.1, maximum=120
            ),
            upstream_max_retries=_environment_int(
                "UPSTREAM_MAX_RETRIES", default=2, minimum=0, maximum=4
            ),
            upstream_backoff_seconds=_environment_float(
                "UPSTREAM_BACKOFF_SECONDS", default=0.25, minimum=0, maximum=5
            ),
            max_request_bytes=_environment_int(
                "MAX_REQUEST_BYTES", default=8_192, minimum=1_024, maximum=65_536
            ),
            max_response_bytes=_environment_int(
                "MAX_RESPONSE_BYTES", default=1_000_000, minimum=10_000, maximum=10_000_000
            ),
        )


def _environment_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise RelayConfigurationError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise RelayConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _environment_float(
    name: str, *, default: float, minimum: float, maximum: float
) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise RelayConfigurationError(f"{name} must be numeric") from error
    if not minimum <= value <= maximum:
        raise RelayConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value
