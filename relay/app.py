"""FastAPI application factory for the authenticated BuildingHUB relay."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .config import RelaySettings
from .security import (
    AuthenticationError,
    JSONBodyError,
    NonceStore,
    authenticate_request,
    load_json_object,
)
from .upstream import (
    ALLOWED_ENDPOINTS,
    BuildingHubUpstream,
    UpstreamInvalidResponse,
    UpstreamUnavailable,
)

LOGGER = logging.getLogger(__name__)


class RelayInputError(ValueError):
    """A public request violated the intentionally narrow relay contract."""


class OfficialBuildingHubParams(BaseModel):
    """The only public-data query parameters accepted by this relay.

    There is intentionally no free-form URL, header, method, serviceKey,
    filter, or body forwarding field.  Pagination and parcel fields are all
    the current Streamlit lookup needs for BldRgstHubService.
    """

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=False)

    sigungu_cd: str = Field(alias="sigunguCd")
    bjdong_cd: str = Field(alias="bjdongCd")
    plat_gb_cd: str = Field(alias="platGbCd")
    bun: str
    ji: str
    page_no: int = Field(default=1, alias="pageNo", ge=1, le=10_000)
    num_of_rows: int = Field(default=100, alias="numOfRows", ge=1, le=100)
    response_type: Literal["json", "xml"] = Field(default="json", alias="_type")
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    dong_nm: str | None = Field(default=None, alias="dongNm")
    ho_nm: str | None = Field(default=None, alias="hoNm")

    @field_validator("sigungu_cd", "bjdong_cd")
    @classmethod
    def _five_digit_code(cls, value: str) -> str:
        if len(value) != 5 or not value.isascii() or not value.isdigit():
            raise ValueError("must contain exactly five ASCII digits")
        return value

    @field_validator("plat_gb_cd")
    @classmethod
    def _parcel_type(cls, value: str) -> str:
        if value not in {"0", "1", "2"}:
            raise ValueError("must be 0, 1, or 2")
        return value

    @field_validator("bun", "ji")
    @classmethod
    def _parcel_number(cls, value: str) -> str:
        if not 1 <= len(value) <= 4 or not value.isascii() or not value.isdigit():
            raise ValueError("must contain one to four ASCII digits")
        return value.zfill(4)

    @field_validator("start_date", "end_date")
    @classmethod
    def _date_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) != 8 or not value.isascii() or not value.isdigit():
            raise ValueError("must be an eight-digit date")
        try:
            date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}")
        except ValueError as error:
            raise ValueError("must be a valid calendar date") from error
        return value

    @field_validator("dong_nm", "ho_nm")
    @classmethod
    def _unit_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 100 or any(ord(char) < 32 for char in normalized):
            raise ValueError("must be a non-empty printable value of at most 100 characters")
        return normalized

    @model_validator(mode="after")
    def _date_range(self) -> OfficialBuildingHubParams:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("startDate must not be after endDate")
        return self


class RelayRequestPayload(BaseModel):
    """Signed body: exactly one object named ``params``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    params: OfficialBuildingHubParams


def create_app(
    settings: RelaySettings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], Any] | None = None,
) -> FastAPI:
    """Create the relay application.

    The no-argument form is the Cloud Run/Uvicorn factory.  Test callers can
    inject a transport and fixed clock without a real key or network request.
    """

    configuration = settings if settings is not None else RelaySettings.from_environment()
    nonce_store = NonceStore(ttl_seconds=configuration.nonce_ttl_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        upstream_kwargs: dict[str, Any] = {"transport": transport}
        if sleep is not None:
            upstream_kwargs["sleep"] = sleep
        upstream = BuildingHubUpstream(configuration, **upstream_kwargs)
        app.state.upstream = upstream
        try:
            yield
        finally:
            await upstream.aclose()

    app = FastAPI(
        title="BuildingHUB authenticated relay",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AuthenticationError)
    async def _authentication_error(_: Request, __: AuthenticationError) -> JSONResponse:
        return _error_response(401, "invalid_authentication", "Request authentication failed.")

    @app.exception_handler(RelayInputError)
    async def _input_error(_: Request, __: RelayInputError) -> JSONResponse:
        return _error_response(
            400,
            "invalid_request",
            "Request must contain valid BuildingHUB parcel and page parameters.",
        )

    @app.exception_handler(UpstreamUnavailable)
    async def _upstream_unavailable(_: Request, error: UpstreamUnavailable) -> JSONResponse:
        LOGGER.warning(
            "BuildingHUB relay unavailable endpoint=%s attempts=%s category=%s",
            error.endpoint,
            error.attempts,
            error.category,
        )
        return _error_response(
            503,
            "upstream_unavailable",
            "BuildingHUB is temporarily unavailable. Please retry later.",
            retryable=True,
        )

    @app.exception_handler(UpstreamInvalidResponse)
    async def _upstream_invalid(_: Request, error: UpstreamInvalidResponse) -> JSONResponse:
        # The detailed exception is intentionally not logged because upstream
        # providers sometimes echo request URLs in their failure text.
        del error
        return _error_response(
            502,
            "upstream_invalid_response",
            "BuildingHUB returned an invalid response.",
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness endpoint: it must not spend a BuildingHUB API call."""

        return {"status": "ok"}

    @app.post("/v1/building-hub/{endpoint}")
    async def relay_building_hub(endpoint: str, request: Request) -> Response:
        if endpoint not in ALLOWED_ENDPOINTS:
            return _error_response(404, "not_found", "Requested endpoint was not found.")
        if request.query_params:
            raise RelayInputError("query parameters are not accepted")
        if _content_length_exceeds(request.headers, configuration.max_request_bytes):
            raise RelayInputError("request body is too large")
        if _content_type(request.headers) != "application/json":
            raise RelayInputError("content type must be application/json")
        if not _has_single_auth_headers(request):
            raise AuthenticationError("invalid request authentication")

        body_bytes = await _read_limited_body(request, configuration.max_request_bytes)
        if not body_bytes:
            raise RelayInputError("request body is empty")
        try:
            raw_payload = load_json_object(body_bytes)
        except JSONBodyError as error:
            raise RelayInputError("request body is invalid") from error

        await authenticate_request(
            headers=request.headers,
            endpoint=endpoint,
            body=raw_payload,
            secret=configuration.hmac_secret,
            max_clock_skew_seconds=configuration.max_clock_skew_seconds,
            nonce_store=nonce_store,
            clock=clock,
        )

        try:
            payload = RelayRequestPayload.model_validate(raw_payload)
        except ValidationError as error:
            raise RelayInputError("request payload is invalid") from error

        # Pass aliases so the official API sees exactly its documented names.
        if endpoint != "getBrExposPubuseAreaInfo" and (
            payload.params.dong_nm is not None or payload.params.ho_nm is not None
        ):
            raise RelayInputError("dongNm and hoNm are endpoint-specific")
        params = payload.params.model_dump(by_alias=True, exclude_none=True)
        upstream_response = await request.app.state.upstream.fetch(
            endpoint=endpoint,
            params=params,
            response_type=payload.params.response_type,
        )
        return Response(
            content=upstream_response.body,
            status_code=upstream_response.status_code,
            media_type=upstream_response.media_type,
        )

    return app


def _content_length_exceeds(headers: Mapping[str, str], maximum: int) -> bool:
    value = headers.get("content-length")
    if value is None:
        return False
    try:
        parsed = int(value)
        return parsed < 0 or parsed > maximum
    except ValueError:
        return True


def _content_type(headers: Mapping[str, str]) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _has_single_auth_headers(request: Request) -> bool:
    return all(
        len(request.headers.getlist(name)) == 1
        for name in (
            "x-building-hub-timestamp",
            "x-building-hub-nonce",
            "x-building-hub-signature",
        )
    )


async def _read_limited_body(request: Request, maximum: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > maximum:
            raise RelayInputError("request body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _error_response(
    status_code: int, code: str, message: str, *, retryable: bool = False
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            }
        },
    )
