from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import pytest
import requests

from src.building_hub import (
    BuildingHubAPIError,
    BuildingHubAuthError,
    BuildingHubClient,
    BuildingHubDecodeError,
    BuildingHubEnvelopeError,
    BuildingHubHTTPError,
    BuildingHubNetworkError,
    BuildingHubPaginationError,
    BuildingHubQuotaError,
    BuildingHubValidationError,
)


KEY = "secret+/key=="
LAND_DICT = {
    "sigunguCd": "41117",
    "bjdongCd": "10700",
    "platGbCd": "1",
    "bun": 6,
    "ji": 11,
}


def api_payload(
    item: Any,
    *,
    total_count: int | str = 1,
    page_no: int | str = 1,
    code: str = "00",
    message: str = "NORMAL SERVICE",
    items_node: Any = ...,
) -> dict[str, Any]:
    if items_node is ...:
        items_node = {"item": item}
    return {
        "response": {
            "header": {"resultCode": code, "resultMsg": message},
            "body": {
                "items": items_node,
                "numOfRows": 100,
                "pageNo": page_no,
                "totalCount": total_count,
            },
        }
    }


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any | None = None,
        text: str | None = None,
        content_type: str = "application/json",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False) if text is None else text
        self.content = self.text.encode("utf-8")
        self.headers = {"Content-Type": content_type, **(headers or {})}


class FakeSession:
    def __init__(self, *actions: Any) -> None:
        self.actions = list(actions)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.actions:
            raise AssertionError("unexpected HTTP call")
        action = self.actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action

    def close(self) -> None:
        self.closed = True


@dataclass
class SnakeCaseLandKey:
    sigungu_cd: str = "41117"
    bjdong_cd: str = "10700"
    plat_gb_cd: str = "0"
    main_bun: int = 12
    sub_bun: int = 0


def test_https_whitelist_duck_land_key_timeout_and_key_redaction() -> None:
    session = FakeSession(
        FakeResponse(payload=api_payload({"mgmBldrgstPk": "pk-1"}))
    )
    client = BuildingHubClient(
        KEY,
        session=session,
        timeout=(1.25, 8.0),
        max_retries=0,
    )

    items = client.fetch_all("/getBrTitleInfo", SnakeCaseLandKey())

    assert items == [{"mgmBldrgstPk": "pk-1"}]
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == (
        "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
    )
    assert call["timeout"] == (1.25, 8.0)
    assert call["params"] == {
        "sigunguCd": "41117",
        "bjdongCd": "10700",
        "platGbCd": "0",
        "bun": "0012",
        "ji": "0000",
        "_type": "json",
        "numOfRows": 100,
        "pageNo": 1,
        "serviceKey": KEY,
    }
    assert KEY not in repr(client)
    assert "[REDACTED]" in repr(client)


@pytest.mark.parametrize("num_of_rows", [0, 101, True, 1.5])
def test_num_of_rows_is_limited_to_one_hundred(num_of_rows: Any) -> None:
    client = BuildingHubClient(KEY, session=FakeSession())
    with pytest.raises(BuildingHubValidationError):
        client.fetch_all("getBrTitleInfo", LAND_DICT, num_of_rows=num_of_rows)


def test_endpoint_and_query_parameters_are_whitelisted() -> None:
    client = BuildingHubClient(KEY, session=FakeSession())
    with pytest.raises(BuildingHubValidationError):
        client.fetch_all("../admin", LAND_DICT)
    with pytest.raises(BuildingHubValidationError):
        client.fetch_all("getBrTitleInfo", LAND_DICT, serviceKey="override")
    with pytest.raises(BuildingHubValidationError):
        client.fetch_all("getBrTitleInfo", LAND_DICT, hoNm="101호")


def test_pagination_normalizes_single_object_and_list_items() -> None:
    session = FakeSession(
        FakeResponse(
            payload=api_payload(
                {"id": "one"}, total_count="3", page_no="1"
            )
        ),
        FakeResponse(
            payload=api_payload(
                [{"id": "two"}, {"id": "three"}],
                total_count=3,
                page_no=2,
            )
        ),
    )
    client = BuildingHubClient(KEY, session=session, max_retries=0)

    result = client.fetch_all("getBrBasisOulnInfo", LAND_DICT, num_of_rows=2)

    assert result == [{"id": "one"}, {"id": "two"}, {"id": "three"}]
    assert [call["params"]["pageNo"] for call in session.calls] == [1, 2]
    assert all(call["params"]["numOfRows"] == 2 for call in session.calls)


@pytest.mark.parametrize(
    "items_node",
    [None, {"item": None}, {"item": []}],
)
def test_null_or_empty_items_normalize_to_empty_list(items_node: Any) -> None:
    session = FakeSession(
        FakeResponse(
            payload=api_payload(
                None,
                total_count=0,
                items_node=items_node,
            )
        )
    )
    client = BuildingHubClient(KEY, session=session, max_retries=0)

    assert client.fetch_all("getBrTitleInfo", LAND_DICT) == []


def test_xml_success_envelope_returns_dict_items() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <response>
      <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE</resultMsg></header>
      <body>
        <items>
          <item><mgmBldrgstPk>pk-1</mgmBldrgstPk><hoNm>101호</hoNm></item>
          <item><mgmBldrgstPk>pk-2</mgmBldrgstPk><hoNm>102호</hoNm></item>
        </items>
        <numOfRows>100</numOfRows><pageNo>1</pageNo><totalCount>2</totalCount>
      </body>
    </response>"""
    session = FakeSession(
        FakeResponse(text=xml, content_type="application/xml")
    )
    client = BuildingHubClient(KEY, session=session, max_retries=0)

    result = client.fetch_all(
        "getBrExposInfo", LAND_DICT, response_type="xml"
    )

    assert result == [
        {"mgmBldrgstPk": "pk-1", "hoNm": "101호"},
        {"mgmBldrgstPk": "pk-2", "hoNm": "102호"},
    ]
    assert session.calls[0]["params"]["_type"] == "xml"


def test_decode_and_envelope_errors_are_distinct() -> None:
    malformed = BuildingHubClient(
        KEY,
        session=FakeSession(FakeResponse(text="{broken", content_type="application/json")),
        max_retries=0,
    )
    with pytest.raises(BuildingHubDecodeError):
        malformed.fetch_all("getBrTitleInfo", LAND_DICT)

    wrong_envelope = BuildingHubClient(
        KEY,
        session=FakeSession(FakeResponse(payload={"unexpected": {}})),
        max_retries=0,
    )
    with pytest.raises(BuildingHubEnvelopeError):
        wrong_envelope.fetch_all("getBrTitleInfo", LAND_DICT)


def test_auth_error_is_not_retried_and_does_not_expose_key() -> None:
    response = FakeResponse(
        payload=api_payload(
            None,
            code="30",
            message=f"bad service key: {KEY}",
            items_node=None,
        )
    )
    session = FakeSession(response, AssertionError("must not retry"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubAuthError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert len(session.calls) == 1
    assert KEY not in str(caught.value)
    assert KEY not in caught.value.result_message
    assert "[REDACTED]" in caught.value.result_message


def test_http_400_gateway_code_10_is_an_api_error() -> None:
    response = FakeResponse(
        status_code=400,
        payload={
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "INVALID_REQUEST_PARAMETER_ERROR",
                    "returnAuthMsg": "invalid request parameter",
                    "returnReasonCode": "10",
                }
            }
        },
    )
    session = FakeSession(response, AssertionError("must not retry"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubAPIError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert type(caught.value) is BuildingHubAPIError
    assert caught.value.result_code == "10"
    assert caught.value.retryable is False
    assert len(session.calls) == 1


def test_http_401_gateway_code_20_is_an_auth_error() -> None:
    response = FakeResponse(
        status_code=401,
        payload={
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "SERVICE_KEY_IS_NULL",
                    "returnAuthMsg": "service access denied",
                    "returnReasonCode": "20",
                }
            }
        },
    )
    session = FakeSession(response, AssertionError("must not retry"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubAuthError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert caught.value.result_code == "20"
    assert caught.value.retryable is False
    assert len(session.calls) == 1


def test_http_403_gateway_code_30_is_an_auth_error_and_redacts_key() -> None:
    response = FakeResponse(
        status_code=403,
        payload={
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                    "returnAuthMsg": f"unregistered service key: {KEY}",
                    "returnReasonCode": "30",
                }
            }
        },
    )
    session = FakeSession(response, AssertionError("must not retry"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubAuthError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert caught.value.result_code == "30"
    assert caught.value.retryable is False
    assert KEY not in str(caught.value)
    assert KEY not in caught.value.result_message
    assert "[REDACTED]" in caught.value.result_message
    assert len(session.calls) == 1


def test_5xx_gateway_application_error_preserves_retry_policy() -> None:
    transient_error = FakeResponse(
        status_code=503,
        payload={
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "APPLICATION_ERROR",
                    "returnAuthMsg": "temporary gateway failure",
                    "returnReasonCode": "01",
                }
            }
        },
    )
    session = FakeSession(
        transient_error,
        FakeResponse(payload=api_payload({"id": "ok"})),
    )
    sleeps: list[float] = []
    client = BuildingHubClient(
        KEY,
        session=session,
        max_retries=1,
        sleep=sleeps.append,
    )

    assert client.fetch_all("getBrTitleInfo", LAND_DICT) == [{"id": "ok"}]
    assert len(session.calls) == 2
    assert sleeps == [0.25]


def test_5xx_gateway_auth_error_is_not_retried() -> None:
    response = FakeResponse(
        status_code=503,
        payload={
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                    "returnAuthMsg": "unregistered service key",
                    "returnReasonCode": "30",
                }
            }
        },
    )
    session = FakeSession(response, AssertionError("must not retry"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubAuthError):
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert len(session.calls) == 1


def test_xml_gateway_quota_error_is_not_retried() -> None:
    xml = """<OpenAPI_ServiceResponse><cmmMsgHeader>
      <errMsg>SERVICE ERROR</errMsg>
      <returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>
      <returnReasonCode>22</returnReasonCode>
    </cmmMsgHeader></OpenAPI_ServiceResponse>"""
    session = FakeSession(FakeResponse(text=xml, content_type="application/xml"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubQuotaError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert caught.value.retryable is False
    assert len(session.calls) == 1


def test_network_failure_retries_then_succeeds() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        requests.ConnectionError("URL containing a secret must not escape"),
        FakeResponse(payload=api_payload({"id": 1})),
    )
    client = BuildingHubClient(
        KEY,
        session=session,
        max_retries=1,
        backoff_factor=0.5,
        sleep=sleeps.append,
    )

    assert client.fetch_all("getBrTitleInfo", LAND_DICT) == [{"id": 1}]
    assert len(session.calls) == 2
    assert sleeps == [0.5]


def test_network_failure_after_retries_is_sanitized() -> None:
    session = FakeSession(requests.Timeout(f"timed out with {KEY}"))
    client = BuildingHubClient(KEY, session=session, max_retries=0)

    with pytest.raises(BuildingHubNetworkError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert KEY not in str(caught.value)
    assert caught.value.endpoint == "getBrTitleInfo"
    assert caught.value.attempts == 1
    assert caught.value.reason == "timeout"


def test_network_timeout_uses_four_attempts_and_keeps_safe_diagnostics() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        *[requests.ReadTimeout(f"read timeout for {KEY}") for _ in range(4)]
    )
    client = BuildingHubClient(KEY, session=session, sleep=sleeps.append)

    with pytest.raises(BuildingHubNetworkError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert len(session.calls) == 4
    assert sleeps == [0.25, 0.5, 1.0]
    assert caught.value.endpoint == "getBrTitleInfo"
    assert caught.value.attempts == 4
    assert caught.value.reason == "read_timeout"
    assert KEY not in str(caught.value)


def test_owned_session_ignores_ambient_proxy_settings() -> None:
    client = BuildingHubClient(KEY)
    try:
        assert client._session.trust_env is False
    finally:
        client.close()


def test_http_429_and_5xx_are_retried() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        FakeResponse(status_code=429, text="busy", headers={"Retry-After": "2"}),
        FakeResponse(status_code=503, text="down"),
        FakeResponse(payload=api_payload({"id": "ok"})),
    )
    client = BuildingHubClient(
        KEY,
        session=session,
        max_retries=2,
        backoff_factor=0.25,
        sleep=sleeps.append,
    )

    assert client.fetch_all("getBrTitleInfo", LAND_DICT) == [{"id": "ok"}]
    assert sleeps == [2.0, 0.5]
    assert len(session.calls) == 3


def test_non_retryable_http_error_is_classified() -> None:
    session = FakeSession(FakeResponse(status_code=404, text="not found"))
    client = BuildingHubClient(KEY, session=session, max_retries=3)

    with pytest.raises(BuildingHubHTTPError) as caught:
        client.fetch_all("getBrTitleInfo", LAND_DICT)

    assert caught.value.status_code == 404
    assert caught.value.retryable is False
    assert len(session.calls) == 1


def test_result_code_23_is_retried() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        FakeResponse(
            payload=api_payload(
                None,
                code="23",
                message="LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR",
                items_node=None,
            )
        ),
        FakeResponse(payload=api_payload({"id": "ok"})),
    )
    client = BuildingHubClient(
        KEY,
        session=session,
        max_retries=1,
        sleep=sleeps.append,
    )

    assert client.fetch_all("getBrTitleInfo", LAND_DICT) == [{"id": "ok"}]
    assert len(session.calls) == 2
    assert sleeps == [0.25]


def test_repeated_page_guard_prevents_infinite_pagination() -> None:
    same_items = [{"id": 1}, {"id": 2}]
    session = FakeSession(
        FakeResponse(
            payload=api_payload(same_items, total_count=4, page_no=1)
        ),
        FakeResponse(
            payload=api_payload(same_items, total_count=4, page_no=2)
        ),
    )
    client = BuildingHubClient(KEY, session=session, max_retries=0)

    with pytest.raises(BuildingHubPaginationError, match="repeated"):
        client.fetch_all("getBrTitleInfo", LAND_DICT, num_of_rows=2)

    assert len(session.calls) == 2


def test_scalar_item_is_an_envelope_error() -> None:
    session = FakeSession(FakeResponse(payload=api_payload("not-an-object")))
    client = BuildingHubClient(KEY, session=session, max_retries=0)

    with pytest.raises(BuildingHubEnvelopeError):
        client.fetch_all("getBrTitleInfo", LAND_DICT)
