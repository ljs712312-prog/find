"""Focused contract and security tests for the standalone relay."""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from relay.app import create_app
from relay.config import RelaySettings
from relay.security import canonical_json, make_signature

NOW = 1_800_000_000
SERVICE_KEY = "relay-test-service-key-that-must-not-leak"
HMAC_SECRET = b"relay-test-hmac-secret-that-is-longer-than-32-bytes"


def _settings(**overrides: Any) -> RelaySettings:
    values: dict[str, Any] = {
        "service_key": SERVICE_KEY,
        "hmac_secret": HMAC_SECRET,
        "upstream_backoff_seconds": 0,
        "upstream_max_retries": 1,
    }
    values.update(overrides)
    return RelaySettings(**values)


async def _no_sleep(_: float) -> None:
    return None


def _app(handler: httpx.MockTransport) -> Any:
    return create_app(
        _settings(),
        transport=handler,
        clock=lambda: float(NOW),
        sleep=_no_sleep,
    )


def _body_and_headers(
    *,
    endpoint: str = "getBrTitleInfo",
    params: dict[str, Any] | None = None,
    nonce: str = "valid_nonce_00001",
    timestamp: int = NOW,
) -> tuple[bytes, dict[str, str]]:
    payload = {
        "params": params
        or {
            "sigunguCd": "41110",
            "bjdongCd": "10100",
            "platGbCd": "0",
            "bun": "396",
            "ji": "30",
        }
    }
    timestamp_text = str(timestamp)
    signature = make_signature(
        HMAC_SECRET,
        timestamp=timestamp_text,
        nonce=nonce,
        endpoint=endpoint,
        body=payload,
    )
    return canonical_json(payload).encode("utf-8"), {
        "Content-Type": "application/json",
        "X-Building-Hub-Timestamp": timestamp_text,
        "X-Building-Hub-Nonce": nonce,
        "X-Building-Hub-Signature": signature,
    }


def _success_envelope() -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": {"item": []}, "pageNo": 1, "totalCount": 0},
        }
    }


def test_healthz_never_calls_upstream() -> None:
    def unexpected_call(_: httpx.Request) -> httpx.Response:
        raise AssertionError("health check must not call BuildingHUB")

    with TestClient(_app(httpx.MockTransport(unexpected_call))) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_signed_request_forwards_only_validated_official_params() -> None:
    requests: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_success_envelope())

    params = {
        "sigunguCd": "41110",
        "bjdongCd": "10100",
        "platGbCd": "0",
        "bun": "396",
        "ji": "30",
        "pageNo": 2,
        "numOfRows": 55,
        "_type": "json",
        "startDate": "20240101",
        "endDate": "20241231",
    }
    body, headers = _body_and_headers(params=params)

    with TestClient(_app(httpx.MockTransport(upstream))) as client:
        response = client.post("/v1/building-hub/getBrTitleInfo", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == _success_envelope()
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url).split("?", 1)[0] == (
        "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
    )
    assert dict(request.url.params) == {
        "sigunguCd": "41110",
        "bjdongCd": "10100",
        "platGbCd": "0",
        "bun": "0396",
        "ji": "0030",
        "pageNo": "2",
        "numOfRows": "55",
        "_type": "json",
        "startDate": "20240101",
        "endDate": "20241231",
        "serviceKey": SERVICE_KEY,
    }


def test_endpoint_specific_unit_filters_are_forwarded_only_to_unit_area_endpoint() -> None:
    requests: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_success_envelope())

    params = {
        "sigunguCd": "41110",
        "bjdongCd": "10100",
        "platGbCd": "0",
        "bun": "396",
        "ji": "30",
        "dongNm": "101동",
        "hoNm": "1001호",
    }
    body, headers = _body_and_headers(
        endpoint="getBrExposPubuseAreaInfo", params=params, nonce="valid_nonce_00002"
    )
    with TestClient(_app(httpx.MockTransport(upstream))) as client:
        allowed = client.post(
            "/v1/building-hub/getBrExposPubuseAreaInfo", content=body, headers=headers
        )

        forbidden_body, forbidden_headers = _body_and_headers(
            params=params, nonce="valid_nonce_00003"
        )
        forbidden = client.post(
            "/v1/building-hub/getBrTitleInfo",
            content=forbidden_body,
            headers=forbidden_headers,
        )

    assert allowed.status_code == 200
    assert dict(requests[0].url.params)["dongNm"] == "101동"
    assert dict(requests[0].url.params)["hoNm"] == "1001호"
    assert forbidden.status_code == 400
    assert len(requests) == 1


def test_signature_tampering_replay_and_unlisted_endpoints_do_not_reach_upstream() -> None:
    requests: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_success_envelope())

    body, headers = _body_and_headers(nonce="valid_nonce_00004")
    tampered = body.replace(b'"396"', b'"397"')
    with TestClient(_app(httpx.MockTransport(upstream))) as client:
        tampered_response = client.post(
            "/v1/building-hub/getBrTitleInfo", content=tampered, headers=headers
        )
        first = client.post("/v1/building-hub/getBrTitleInfo", content=body, headers=headers)
        replay = client.post("/v1/building-hub/getBrTitleInfo", content=body, headers=headers)
        unlisted = client.post("/v1/building-hub/not-an-operation", content=body, headers=headers)

    assert tampered_response.status_code == 401
    assert first.status_code == 200
    assert replay.status_code == 401
    assert unlisted.status_code == 404
    assert len(requests) == 1


def test_rejects_service_key_and_duplicate_json_before_upstream() -> None:
    requests: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_success_envelope())

    unsafe_params = {
        "sigunguCd": "41110",
        "bjdongCd": "10100",
        "platGbCd": "0",
        "bun": "396",
        "ji": "30",
        "serviceKey": "caller-must-not-send-this",
    }
    unsafe_body, unsafe_headers = _body_and_headers(
        params=unsafe_params, nonce="valid_nonce_00005"
    )
    duplicate_body = (
        b'{"params":{"sigunguCd":"41110"},"params":{"sigunguCd":"41110"}}'
    )
    _, duplicate_headers = _body_and_headers(nonce="valid_nonce_00006")

    with TestClient(_app(httpx.MockTransport(upstream))) as client:
        unsafe = client.post(
            "/v1/building-hub/getBrTitleInfo", content=unsafe_body, headers=unsafe_headers
        )
        duplicate = client.post(
            "/v1/building-hub/getBrTitleInfo",
            content=duplicate_body,
            headers=duplicate_headers,
        )

    assert unsafe.status_code == 400
    assert duplicate.status_code == 400
    assert requests == []


def test_retries_safe_gateway_failures_and_redacts_service_key_from_gateway_envelope() -> None:
    attempts: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(
            403,
            content=json.dumps(
                {
                    "OpenAPI_ServiceResponse": {
                        "cmmMsgHeader": {"errMsg": f"serviceKey={SERVICE_KEY}"}
                    }
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    body, headers = _body_and_headers(nonce="valid_nonce_00007")
    with TestClient(_app(httpx.MockTransport(upstream))) as client:
        response = client.post("/v1/building-hub/getBrTitleInfo", content=body, headers=headers)

    assert response.status_code == 403
    assert len(attempts) == 2
    assert SERVICE_KEY not in response.text
    assert "[REDACTED]" in response.text
