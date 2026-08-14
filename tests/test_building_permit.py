from __future__ import annotations

import json
from typing import Any

import pytest

from src.building_hub import BuildingHubValidationError
from src.building_permit import BuildingPermitHubClient


KEY = "permit-secret+/key=="
LAND = {
    "sigunguCd": "41113",
    "bjdongCd": "12600",
    "platGbCd": "0",
    "bun": 92,
    "ji": 7,
}


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, item: dict[str, Any]) -> None:
        self.text = json.dumps(
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {
                        "items": {"item": item},
                        "pageNo": 1,
                        "totalCount": 1,
                    },
                }
            },
            ensure_ascii=False,
        )


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse({"mgmPmsrgstPk": "CASE-1"})


def test_permit_client_uses_fixed_https_host_and_redacts_key() -> None:
    session = FakeSession()
    client = BuildingPermitHubClient(
        KEY,
        session=session,
        max_retries=0,
    )

    rows = client.fetch_all("getApBasisOulnInfo", LAND)

    assert rows == [{"mgmPmsrgstPk": "CASE-1"}]
    call = session.calls[0]
    assert call["url"] == (
        "https://apis.data.go.kr/1613000/ArchPmsHubService/"
        "getApBasisOulnInfo"
    )
    assert call["params"]["bun"] == "0092"
    assert call["params"]["ji"] == "0007"
    assert call["params"]["serviceKey"] == KEY
    assert KEY not in repr(client)


@pytest.mark.parametrize(
    "endpoint",
    ["getBrTitleInfo", "../admin", "getApDemolExtngMgmRgstInfo"],
)
def test_permit_client_rejects_unapproved_operations(endpoint: str) -> None:
    client = BuildingPermitHubClient(KEY, session=FakeSession())
    with pytest.raises(BuildingHubValidationError):
        client.fetch_all(endpoint, LAND)


def test_permit_client_rejects_register_only_name_filters() -> None:
    client = BuildingPermitHubClient(KEY, session=FakeSession())
    with pytest.raises(BuildingHubValidationError):
        client.fetch_all("getApHoOulnInfo", LAND, hoNm="201호")
