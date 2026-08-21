"""Small, defensive client for the Korean Building HUB register API.

The public API is parcel based: callers provide a land key, the client requests
all pages for one whitelisted operation, and returns only normalized item
dictionaries.  Authentication material is deliberately kept out of reprs and
exception messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections.abc import Mapping
from typing import Any, Callable
from urllib.parse import quote, quote_plus, urlsplit
import xml.etree.ElementTree as ET

import requests

LOGGER = logging.getLogger(__name__)


class BuildingHubError(RuntimeError):
    """Base class for Building HUB failures."""


class BuildingHubValidationError(BuildingHubError, ValueError):
    """The caller supplied an invalid endpoint, land key, or option."""


class BuildingHubNetworkError(BuildingHubError):
    """The request could not reach the public-data gateway."""

    def __init__(
        self,
        *,
        endpoint: str,
        attempts: int,
        reason: str,
        elapsed_seconds: float | None = None,
    ) -> None:
        # Keep only safe diagnostic metadata.  In particular, do not keep a
        # requests exception object because it can contain the service-key URL.
        self.endpoint = endpoint
        self.attempts = attempts
        self.reason = reason
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            "Building HUB network error "
            f"({reason}) after {attempts} attempt(s) at {endpoint}"
        )


class BuildingHubHTTPError(BuildingHubError):
    """The gateway returned a non-success HTTP status."""

    def __init__(self, status_code: int, *, retryable: bool) -> None:
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(f"Building HUB HTTP error ({status_code})")


class BuildingHubDecodeError(BuildingHubError):
    """The HTTP body was neither valid JSON nor valid XML."""


class BuildingHubEnvelopeError(BuildingHubError):
    """The decoded body did not match the documented API envelope."""


class BuildingHubAPIError(BuildingHubError):
    """The API envelope reported a non-success result code."""

    def __init__(
        self,
        result_code: str,
        result_message: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.result_code = result_code
        self.result_message = result_message
        self.retryable = retryable
        detail = f": {result_message}" if result_message else ""
        super().__init__(f"Building HUB API error {result_code}{detail}")


class BuildingHubAuthError(BuildingHubAPIError):
    """The service key is absent, unauthorized, unknown, or expired."""


class BuildingHubQuotaError(BuildingHubAPIError):
    """The non-retryable daily request allowance was exhausted."""


class BuildingHubRateLimitError(BuildingHubAPIError):
    """The retryable per-second request allowance was exceeded."""


class BuildingHubPaginationError(BuildingHubError):
    """Pagination stopped being trustworthy (for example, a repeated page)."""


@dataclass(frozen=True)
class _Page:
    items: list[dict[str, Any]]
    total_count: int | None
    page_no: int | None


@dataclass(frozen=True)
class _RelayConfig:
    """Configuration for the narrowly scoped, signed BuildingHUB relay.

    The HMAC secret is intentionally omitted from the dataclass representation
    so an accidental debug representation cannot disclose it.
    """

    base_url: str
    hmac_secret: str = field(repr=False)


class BuildingHubClient:
    """Fetch normalized building-register rows from the official HUB service."""

    BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"
    _REGISTER_BASE_URL = BASE_URL
    _RELAY_URL_ENV = "BUILDING_HUB_RELAY_URL"
    _RELAY_HMAC_SECRET_ENV = "BUILDING_HUB_RELAY_HMAC_SECRET"
    _RELAY_FALLBACK_REASONS = frozenset(
        {"connect_timeout", "connection", "tls", "proxy"}
    )

    ENDPOINTS = frozenset(
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

    _LAND_FIELD_ALIASES = {
        "sigunguCd": ("sigunguCd", "sigungu_cd"),
        "bjdongCd": ("bjdongCd", "bjdong_cd"),
        "platGbCd": ("platGbCd", "plat_gb_cd"),
        "bun": ("bun", "main_bun"),
        "ji": ("ji", "sub_bun"),
    }
    _FILTERS = frozenset({"startDate", "endDate", "dongNm", "hoNm"})
    _SUCCESS_CODES = frozenset({"0", "00", "0000"})
    _AUTH_CODES = frozenset({"20", "30", "31"})
    _QUOTA_CODES = frozenset({"22"})
    _RATE_LIMIT_CODES = frozenset({"23"})

    def __init__(
        self,
        service_key: str,
        *,
        session: Any | None = None,
        timeout: float | tuple[float, float] = (3.05, 15.0),
        max_retries: int = 3,
        backoff_factor: float = 0.25,
        max_pages: int = 10_000,
        sleep: Callable[[float], None] = time.sleep,
        relay_url: str | None = None,
        relay_hmac_secret: str | None = None,
    ) -> None:
        key = str(service_key).strip() if service_key is not None else ""
        if not key:
            raise BuildingHubValidationError("service_key must not be empty")
        self._validate_timeout(timeout)
        if not isinstance(max_retries, int) or max_retries < 0:
            raise BuildingHubValidationError("max_retries must be a non-negative integer")
        if backoff_factor < 0:
            raise BuildingHubValidationError("backoff_factor must be non-negative")
        if not isinstance(max_pages, int) or max_pages < 1:
            raise BuildingHubValidationError("max_pages must be a positive integer")

        self._service_key = key
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_factor = float(backoff_factor)
        self._max_pages = max_pages
        self._sleep = sleep
        self._relay_config = self._configure_relay(
            relay_url=relay_url,
            relay_hmac_secret=relay_hmac_secret,
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self.BASE_URL!r}, "
            "service_key='[REDACTED]', "
            f"relay_enabled={self.relay_enabled}, max_retries={self._max_retries})"
        )

    @property
    def relay_enabled(self) -> bool:
        """Whether this client may fall back to the signed register relay."""

        return self._relay_config is not None

    def close(self) -> None:
        if self._owns_session and hasattr(self._session, "close"):
            self._session.close()

    def __enter__(self) -> "BuildingHubClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_all(
        self,
        endpoint: str,
        land_key: Mapping[str, Any] | object,
        *,
        num_of_rows: int = 100,
        response_type: str = "json",
        **query: Any,
    ) -> list[dict[str, Any]]:
        """Return every result row for *endpoint* as plain dictionaries.

        ``land_key`` may be a mapping or any object exposing camelCase or
        snake_case parcel attributes.  The service only accepts 100 rows per
        request, so this method owns ``pageNo`` and follows ``totalCount``.
        """

        endpoint = self._validate_endpoint(endpoint)
        num_of_rows = self._validate_num_of_rows(num_of_rows)

        if "_type" in query:
            if response_type != "json":
                raise BuildingHubValidationError(
                    "provide either response_type or _type, not both"
                )
            response_type = query.pop("_type")
        response_type = str(response_type).strip().lower()
        if response_type not in {"json", "xml"}:
            raise BuildingHubValidationError("response_type must be 'json' or 'xml'")

        unknown = set(query) - self._FILTERS
        if unknown:
            names = ", ".join(sorted(unknown))
            raise BuildingHubValidationError(f"unsupported query parameter(s): {names}")
        if endpoint != "getBrExposPubuseAreaInfo" and ({"dongNm", "hoNm"} & set(query)):
            raise BuildingHubValidationError(
                "dongNm and hoNm are only valid for getBrExposPubuseAreaInfo"
            )

        base_params = self._land_params(land_key)
        base_params.update(
            {key: value for key, value in query.items() if value is not None and value != ""}
        )
        base_params["_type"] = response_type
        base_params["numOfRows"] = num_of_rows

        collected: list[dict[str, Any]] = []
        page_no = 1
        expected_total: int | None = None
        seen_pages: set[str] = set()

        while page_no <= self._max_pages:
            params = dict(base_params)
            params["pageNo"] = page_no
            page = self._request_page(endpoint, params)

            if page.page_no is not None and page.page_no != page_no:
                raise BuildingHubPaginationError(
                    f"requested page {page_no}, but the API returned page {page.page_no}"
                )

            if expected_total is None:
                expected_total = page.total_count
            elif page.total_count is not None and page.total_count != expected_total:
                raise BuildingHubPaginationError("totalCount changed while paging")

            if page.items:
                fingerprint = self._page_fingerprint(page.items)
                if fingerprint in seen_pages:
                    raise BuildingHubPaginationError(
                        f"the API repeated a result page at pageNo={page_no}"
                    )
                seen_pages.add(fingerprint)
                collected.extend(page.items)
            else:
                if expected_total is not None and len(collected) < expected_total:
                    raise BuildingHubPaginationError(
                        "the API returned an empty page before totalCount was reached"
                    )
                break

            if expected_total is not None and len(collected) >= expected_total:
                break
            if expected_total is None and len(page.items) < num_of_rows:
                break
            page_no += 1
        else:
            raise BuildingHubPaginationError(
                f"pagination exceeded the safety limit of {self._max_pages} pages"
            )

        return collected

    # Friendly aliases used by calling code; all share the same strict behavior.
    fetch = fetch_all
    get_all = fetch_all

    def _request_page(self, endpoint: str, params: dict[str, Any]) -> _Page:
        url = f"{self.BASE_URL}/{endpoint}"
        request_params = dict(params)
        request_params["serviceKey"] = self._service_key
        started_at = time.monotonic()

        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(
                    url,
                    params=request_params,
                    timeout=self._timeout,
                )
            except requests.exceptions.RequestException as error:
                reason = self._network_failure_reason(error)
                if self._should_fallback_to_relay(reason):
                    LOGGER.info(
                        "BuildingHUB direct transport failed; using signed relay "
                        "endpoint=%s reason=%s direct_attempts=%s",
                        endpoint,
                        reason,
                        attempt + 1,
                    )
                    return self._request_relay_page(
                        endpoint,
                        params,
                        direct_attempts=attempt + 1,
                        started_at=started_at,
                    )
                if attempt < self._max_retries:
                    self._backoff(attempt)
                    continue
                LOGGER.warning(
                    "BuildingHUB request failed endpoint=%s reason=%s attempts=%s elapsed_ms=%s",
                    endpoint,
                    reason,
                    attempt + 1,
                    round((time.monotonic() - started_at) * 1000),
                )
                raise BuildingHubNetworkError(
                    endpoint=endpoint,
                    attempts=attempt + 1,
                    reason=reason,
                    elapsed_seconds=time.monotonic() - started_at,
                ) from None

            status = getattr(response, "status_code", None)
            if not isinstance(status, int):
                raise BuildingHubHTTPError(0, retryable=False)

            if status < 200 or status >= 300:
                # The public-data gateway returns its useful error code inside a
                # JSON/XML envelope even when the HTTP status is 4xx (and,
                # occasionally, 5xx).  Decode that envelope before reducing the
                # failure to a generic HTTP error so authentication and quota
                # failures remain actionable.  Malformed/non-envelope bodies
                # deliberately fall through to the existing HTTP policy.
                try:
                    payload = self._decode_payload(response)
                    self._extract_page(payload)
                except BuildingHubRateLimitError:
                    if attempt < self._max_retries:
                        self._backoff(attempt, self._retry_after(response))
                        continue
                    raise
                except (BuildingHubAuthError, BuildingHubQuotaError):
                    # Repeating the same request cannot repair credentials or a
                    # depleted daily allowance, even if the gateway used 5xx.
                    raise
                except BuildingHubAPIError:
                    # Preserve the transport retry policy for other gateway
                    # errors carried by 429/5xx responses.  On ordinary 4xx,
                    # the decoded API error is immediately actionable.
                    if self._retryable_http_status(status):
                        if attempt < self._max_retries:
                            self._backoff(attempt, self._retry_after(response))
                            continue
                    raise
                except (BuildingHubDecodeError, BuildingHubEnvelopeError):
                    pass

            if self._retryable_http_status(status):
                if attempt < self._max_retries:
                    self._backoff(attempt, self._retry_after(response))
                    continue
                raise BuildingHubHTTPError(status, retryable=True)
            if status < 200 or status >= 300:
                raise BuildingHubHTTPError(status, retryable=False)

            try:
                payload = self._decode_payload(response)
                return self._extract_page(payload)
            except BuildingHubRateLimitError:
                if attempt < self._max_retries:
                    self._backoff(attempt, self._retry_after(response))
                    continue
                raise
            except (BuildingHubDecodeError, BuildingHubEnvelopeError):
                # The public gateway occasionally terminates a successful HTTP
                # response early or returns a transient HTML/empty body. A
                # bounded retry repairs that case without masking a persistent
                # schema change.
                if attempt < self._max_retries:
                    self._backoff(attempt)
                    continue
                raise

        raise AssertionError("unreachable retry loop")

    def _should_fallback_to_relay(self, reason: str) -> bool:
        """Return whether the failed *direct* attempt may use the relay.

        The relay is an egress-path fallback, not a second interpretation of
        API responses.  In particular, a response that reached BuildingHUB
        (HTTP/API/auth/quota/rate-limit/read-timeout) must remain direct and
        actionable instead of being hidden behind another service.
        """

        return (
            self._relay_config is not None
            and reason in self._RELAY_FALLBACK_REASONS
        )

    def _request_relay_page(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        direct_attempts: int,
        started_at: float,
    ) -> _Page:
        """Ask the narrowly scoped relay for one already-validated page.

        The service key is deliberately absent from this request.  The relay
        owns its own BuildingHUB service key and receives only the endpoint
        selected by this client plus already-whitelisted parcel parameters.
        """

        config = self._relay_config
        if config is None:  # Defensive: this method is private and gated above.
            raise AssertionError("relay request attempted without relay configuration")

        body = self._canonical_json({"params": dict(params)})
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        signature = self._relay_signature(
            secret=config.hmac_secret,
            timestamp=timestamp,
            nonce=nonce,
            endpoint=endpoint,
            body=body,
        )
        url = f"{config.base_url}/v1/building-hub/{quote(endpoint, safe='')}"
        headers = {
            "Accept": "application/json, application/xml",
            "Content-Type": "application/json; charset=utf-8",
            "X-Building-Hub-Timestamp": timestamp,
            "X-Building-Hub-Nonce": nonce,
            "X-Building-Hub-Signature": signature,
            # Supabase Edge Functions honor this header and execute the relay
            # in Seoul. Other relay providers safely ignore it.
            "X-Region": "ap-northeast-2",
        }

        try:
            response = self._session.post(
                url,
                data=body,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as error:
            reason = self._network_failure_reason(error)
            LOGGER.warning(
                "BuildingHUB relay request failed endpoint=%s reason=%s attempts=%s elapsed_ms=%s",
                endpoint,
                reason,
                direct_attempts + 1,
                round((time.monotonic() - started_at) * 1000),
            )
            raise BuildingHubNetworkError(
                endpoint=endpoint,
                attempts=direct_attempts + 1,
                reason=reason,
                elapsed_seconds=time.monotonic() - started_at,
            ) from None

        status = getattr(response, "status_code", None)
        if not isinstance(status, int):
            raise BuildingHubHTTPError(0, retryable=False)

        if status < 200 or status >= 300:
            # The relay forwards the official envelope unchanged.  Preserve an
            # actionable upstream auth/quota/API error when one is present;
            # otherwise expose only the relay's safe status code.
            try:
                payload = self._decode_payload(response)
                self._extract_page(payload)
            except BuildingHubAPIError:
                raise
            except (BuildingHubDecodeError, BuildingHubEnvelopeError):
                pass
            raise BuildingHubHTTPError(
                status,
                retryable=status == 429 or 500 <= status <= 599,
            )

        payload = self._decode_payload(response)
        return self._extract_page(payload)

    @staticmethod
    def _canonical_json(value: Mapping[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def _relay_signature(
        *,
        secret: str,
        timestamp: str,
        nonce: str,
        endpoint: str,
        body: str,
    ) -> str:
        signed = f"{timestamp}\n{nonce}\n{endpoint}\n{body}".encode("utf-8")
        return hmac.new(
            secret.encode("utf-8"),
            signed,
            hashlib.sha256,
        ).hexdigest()

    def _decode_payload(self, response: Any) -> Mapping[str, Any]:
        text = getattr(response, "text", None)
        if text is None:
            content = getattr(response, "content", b"")
            if isinstance(content, bytes):
                text = content.decode("utf-8", errors="replace")
            else:
                text = str(content)
        if not str(text).strip():
            raise BuildingHubDecodeError("Building HUB returned an empty response body")

        body = str(text).lstrip("\ufeff \t\r\n")
        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("Content-Type", "")).lower()
        looks_json = "json" in content_type or body.startswith(("{", "["))

        if looks_json:
            try:
                payload = json.loads(body)
            except (TypeError, ValueError):
                raise BuildingHubDecodeError(
                    "Building HUB returned malformed JSON"
                ) from None
            if not isinstance(payload, Mapping):
                raise BuildingHubEnvelopeError("JSON response root must be an object")
            return payload

        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            raise BuildingHubDecodeError(
                "Building HUB returned neither valid JSON nor valid XML"
            ) from None
        return self._xml_payload(root)

    def _extract_page(self, payload: Mapping[str, Any]) -> _Page:
        response_node = payload.get("response")
        if not isinstance(response_node, Mapping):
            response_node = self._gateway_error_as_response(payload)
        if not isinstance(response_node, Mapping):
            raise BuildingHubEnvelopeError("response object is missing")

        header = response_node.get("header")
        if not isinstance(header, Mapping):
            raise BuildingHubEnvelopeError("response.header object is missing")
        code_value = header.get("resultCode")
        if code_value is None or str(code_value).strip() == "":
            raise BuildingHubEnvelopeError("response.header.resultCode is missing")
        code = str(code_value).strip()
        message = self._redact(header.get("resultMsg", ""))
        if code not in self._SUCCESS_CODES:
            self._raise_api_error(code, message)

        body = response_node.get("body")
        if not isinstance(body, Mapping):
            raise BuildingHubEnvelopeError("response.body object is missing")

        items_node = body.get("items")
        if items_node is None or items_node == "":
            raw_items: Any = None
        elif isinstance(items_node, Mapping):
            raw_items = items_node.get("item")
        else:
            raise BuildingHubEnvelopeError("response.body.items must be an object or null")

        items = self._normalize_items(raw_items)
        total_count = self._optional_nonnegative_int(body.get("totalCount"), "totalCount")
        page_no = self._optional_nonnegative_int(body.get("pageNo"), "pageNo")
        return _Page(items=items, total_count=total_count, page_no=page_no)

    def _gateway_error_as_response(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        gateway = payload.get("OpenAPI_ServiceResponse")
        if not isinstance(gateway, Mapping):
            return None
        header = gateway.get("cmmMsgHeader")
        if not isinstance(header, Mapping):
            return None
        code = header.get("returnReasonCode")
        message = header.get("returnAuthMsg") or header.get("errMsg") or ""
        if code is None:
            return None
        return {
            "header": {"resultCode": code, "resultMsg": message},
            "body": None,
        }

    def _xml_payload(self, root: ET.Element) -> Mapping[str, Any]:
        gateway_header = self._find_element(root, "cmmMsgHeader")
        if gateway_header is not None:
            code = self._child_text(gateway_header, "returnReasonCode")
            message = (
                self._child_text(gateway_header, "returnAuthMsg")
                or self._child_text(gateway_header, "errMsg")
            )
            return {
                "response": {
                    "header": {"resultCode": code, "resultMsg": message},
                    "body": None,
                }
            }

        header_element = self._find_element(root, "header")
        body_element = self._find_element(root, "body")
        if header_element is None:
            raise BuildingHubEnvelopeError("XML response header is missing")

        header = {
            "resultCode": self._child_text(header_element, "resultCode"),
            "resultMsg": self._child_text(header_element, "resultMsg"),
        }
        body: dict[str, Any] | None = None
        if body_element is not None:
            item_elements = [
                child
                for child in body_element.iter()
                if self._local_name(child.tag) == "item"
            ]
            body = {
                "items": {
                    "item": [self._flat_xml_item(element) for element in item_elements]
                }
                if item_elements
                else None,
                "numOfRows": self._child_text(body_element, "numOfRows"),
                "pageNo": self._child_text(body_element, "pageNo"),
                "totalCount": self._child_text(body_element, "totalCount"),
            }
        return {"response": {"header": header, "body": body}}

    def _raise_api_error(self, code: str, message: str) -> None:
        if code in self._AUTH_CODES:
            raise BuildingHubAuthError(code, message, retryable=False)
        if code in self._QUOTA_CODES:
            raise BuildingHubQuotaError(code, message, retryable=False)
        if code in self._RATE_LIMIT_CODES:
            raise BuildingHubRateLimitError(code, message, retryable=True)
        raise BuildingHubAPIError(code, message, retryable=False)

    @staticmethod
    def _normalize_items(raw_items: Any) -> list[dict[str, Any]]:
        if raw_items is None or raw_items == "":
            return []
        if isinstance(raw_items, Mapping):
            return [dict(raw_items)]
        if isinstance(raw_items, list):
            normalized: list[dict[str, Any]] = []
            for item in raw_items:
                if not isinstance(item, Mapping):
                    raise BuildingHubEnvelopeError(
                        "every response item must be an object"
                    )
                normalized.append(dict(item))
            return normalized
        raise BuildingHubEnvelopeError("response item must be null, an object, or a list")

    def _configure_relay(
        self,
        *,
        relay_url: str | None,
        relay_hmac_secret: str | None,
    ) -> _RelayConfig | None:
        """Validate optional signed-relay settings without affecting other APIs."""

        if self.BASE_URL.rstrip("/") != self._REGISTER_BASE_URL:
            # ``BuildingPermitHubClient`` inherits the transport but points to
            # a different official service.  Never let register relay settings
            # silently route permit calls to the wrong upstream API.
            if relay_url is not None or relay_hmac_secret is not None:
                raise BuildingHubValidationError(
                    "the BuildingHUB relay is only available for the register service"
                )
            return None

        raw_url = relay_url
        if raw_url is None:
            raw_url = os.environ.get(self._RELAY_URL_ENV)
        raw_secret = relay_hmac_secret
        if raw_secret is None:
            raw_secret = os.environ.get(self._RELAY_HMAC_SECRET_ENV)

        url = self._optional_config_text(raw_url)
        secret = self._optional_config_text(raw_secret)
        if url is None:
            if secret is not None:
                raise BuildingHubValidationError(
                    "BUILDING_HUB_RELAY_URL is required when "
                    "BUILDING_HUB_RELAY_HMAC_SECRET is configured"
                )
            return None

        if secret is None:
            # Avoid a second Streamlit secret for the free relay.  Both the
            # Streamlit backend and Worker derive the same domain-separated
            # HMAC key from the existing BuildingHUB service key.  The service
            # key itself is never sent in the relay request.
            secret = hashlib.sha256(
                f"buildinghub-relay-v1\x00{self._service_key}".encode("utf-8")
            ).hexdigest()

        return _RelayConfig(
            base_url=self._validate_relay_url(url),
            hmac_secret=self._validate_relay_hmac_secret(secret),
        )

    @staticmethod
    def _optional_config_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    @staticmethod
    def _validate_relay_url(value: str) -> str:
        if value != value.strip() or any(char.isspace() for char in value):
            raise BuildingHubValidationError(
                "BUILDING_HUB_RELAY_URL must not contain whitespace"
            )
        try:
            parsed = urlsplit(value)
            # Accessing ``port`` forces urlsplit to validate its numeric range.
            _ = parsed.port
        except ValueError:
            raise BuildingHubValidationError(
                "BUILDING_HUB_RELAY_URL must be a valid HTTPS URL"
            ) from None
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "\\" in parsed.path
            or ".." in parsed.path.split("/")
        ):
            raise BuildingHubValidationError(
                "BUILDING_HUB_RELAY_URL must be an absolute HTTPS URL without "
                "credentials, query, or fragment"
            )
        return value.rstrip("/")

    @staticmethod
    def _validate_relay_hmac_secret(value: str | None) -> str:
        if value is None:
            raise AssertionError("relay HMAC secret must be present after validation")
        if value != value.strip() or any(char.isspace() for char in value):
            raise BuildingHubValidationError(
                "BUILDING_HUB_RELAY_HMAC_SECRET must not contain whitespace"
            )
        if len(value) < 32:
            raise BuildingHubValidationError(
                "BUILDING_HUB_RELAY_HMAC_SECRET must be at least 32 characters"
            )
        return value

    def _land_params(self, land_key: Mapping[str, Any] | object) -> dict[str, str]:
        params: dict[str, str] = {}
        for api_name, aliases in self._LAND_FIELD_ALIASES.items():
            value = self._duck_value(land_key, aliases)
            if value is None or str(value).strip() == "":
                raise BuildingHubValidationError(f"land_key.{api_name} is required")
            text = str(value).strip()
            if api_name in {"bun", "ji"} and text.isdigit():
                text = text.zfill(4)
            params[api_name] = text

        if params["platGbCd"] not in {"0", "1", "2"}:
            raise BuildingHubValidationError("land_key.platGbCd must be 0, 1, or 2")
        for name in ("sigunguCd", "bjdongCd"):
            if len(params[name]) != 5:
                raise BuildingHubValidationError(f"land_key.{name} must be 5 characters")
        for name in ("bun", "ji"):
            if not params[name].isdigit() or len(params[name]) > 4:
                raise BuildingHubValidationError(
                    f"land_key.{name} must contain at most four digits"
                )
        return params

    @staticmethod
    def _duck_value(source: Mapping[str, Any] | object, names: tuple[str, ...]) -> Any:
        if isinstance(source, Mapping):
            for name in names:
                if name in source:
                    return source[name]
            return None
        for name in names:
            if hasattr(source, name):
                return getattr(source, name)
        return None

    @classmethod
    def _validate_endpoint(cls, endpoint: str) -> str:
        value = str(endpoint).strip().lstrip("/")
        if value not in cls.ENDPOINTS:
            raise BuildingHubValidationError(f"unsupported Building HUB endpoint: {value}")
        return value

    @staticmethod
    def _validate_num_of_rows(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
            raise BuildingHubValidationError("num_of_rows must be an integer from 1 to 100")
        return value

    @staticmethod
    def _validate_timeout(value: float | tuple[float, float]) -> None:
        values = value if isinstance(value, tuple) else (value,)
        if len(values) not in {1, 2} or any(
            isinstance(part, bool) or not isinstance(part, (int, float)) or part <= 0
            for part in values
        ):
            raise BuildingHubValidationError(
                "timeout must be a positive number or a pair of positive numbers"
            )

    @staticmethod
    def _optional_nonnegative_int(value: Any, field: str) -> int | None:
        if value is None or value == "":
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            raise BuildingHubEnvelopeError(f"response.body.{field} is not an integer") from None
        if parsed < 0:
            raise BuildingHubEnvelopeError(f"response.body.{field} must not be negative")
        return parsed

    def _backoff(self, attempt: int, retry_after: float | None = None) -> None:
        delay = retry_after
        if delay is None:
            delay = self._backoff_factor * (2**attempt)
        self._sleep(min(max(float(delay), 0.0), 60.0))

    @staticmethod
    def _retry_after(response: Any) -> float | None:
        headers = getattr(response, "headers", {}) or {}
        value = headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _retryable_http_status(status: int) -> bool:
        return status in {408, 429} or 500 <= status <= 599

    @staticmethod
    def _network_failure_reason(error: requests.exceptions.RequestException) -> str:
        """Return a stable, non-sensitive category for an HTTP failure."""

        if isinstance(error, requests.exceptions.ConnectTimeout):
            return "connect_timeout"
        if isinstance(error, requests.exceptions.ReadTimeout):
            return "read_timeout"
        if isinstance(error, requests.exceptions.Timeout):
            return "timeout"
        if isinstance(error, requests.exceptions.SSLError):
            return "tls"
        if isinstance(error, requests.exceptions.ProxyError):
            return "proxy"
        if isinstance(error, requests.exceptions.ChunkedEncodingError):
            return "interrupted"
        if isinstance(error, requests.exceptions.ConnectionError):
            return "connection"
        return "request"

    @staticmethod
    def _page_fingerprint(items: list[dict[str, Any]]) -> str:
        encoded = json.dumps(
            items,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _redact(self, value: Any) -> str:
        text = str(value or "")
        secrets_to_redact = [self._service_key]
        if self._relay_config is not None:
            secrets_to_redact.append(self._relay_config.hmac_secret)
        candidates = {
            encoded
            for secret in secrets_to_redact
            for encoded in (
                secret,
                quote(secret, safe=""),
                quote_plus(secret, safe=""),
            )
        }
        for candidate in candidates:
            if candidate:
                text = text.replace(candidate, "[REDACTED]")
        return text[:500]

    @classmethod
    def _local_name(cls, tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @classmethod
    def _find_element(cls, root: ET.Element, name: str) -> ET.Element | None:
        for element in root.iter():
            if cls._local_name(element.tag) == name:
                return element
        return None

    @classmethod
    def _child_text(cls, root: ET.Element, name: str) -> str:
        element = cls._find_element(root, name)
        return (element.text or "").strip() if element is not None else ""

    @classmethod
    def _flat_xml_item(cls, item: ET.Element) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for child in list(item):
            result[cls._local_name(child.tag)] = (child.text or "").strip()
        return result


__all__ = [
    "BuildingHubAPIError",
    "BuildingHubAuthError",
    "BuildingHubClient",
    "BuildingHubDecodeError",
    "BuildingHubEnvelopeError",
    "BuildingHubError",
    "BuildingHubHTTPError",
    "BuildingHubNetworkError",
    "BuildingHubPaginationError",
    "BuildingHubQuotaError",
    "BuildingHubRateLimitError",
    "BuildingHubValidationError",
]
