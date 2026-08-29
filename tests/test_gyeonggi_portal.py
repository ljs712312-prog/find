from __future__ import annotations

import requests

import pytest

from src.address import LandKey
from src.gyeonggi_portal import (
    GyeonggiPortalClient,
    GyeonggiPortalError,
    PortalBuildingState,
    gyeonggi_portal_url,
)


class FakeResponse:
    def __init__(self, payload=None, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, page, data):
        self.page = page
        self.data = data
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.page

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.data


LAND = LandKey("41117", "10700", "0", "0006", "0011")
MOUNTAIN = LandKey("41113", "12900", "1", "0001", "0005")
CSRF_PAGE = """
<html><head>
<meta content=" session-token " name="_csrf">
<meta name="_csrf_header" content="X-CSRF-TOKEN">
</head></html>
"""


def test_public_page_url_uses_exact_pnu() -> None:
    assert gyeonggi_portal_url(LAND).endswith(
        "code=01&pnu=4111710700100060011"
    )


def test_visible_rows_are_only_a_portal_visibility_signal() -> None:
    session = FakeSession(
        FakeResponse({}, text=CSRF_PAGE),
        FakeResponse(
            [
                {"bldNm": "일반건축물", "violBldYn": None},
                {"bldNm": "별동", "violBldYn": "1"},
            ]
        ),
    )
    reference = GyeonggiPortalClient(session=session).get_building_reference(LAND)

    assert reference.state is PortalBuildingState.VISIBLE
    assert reference.building_count == 2
    assert reference.building_names == ("일반건축물", "별동")
    # Deliberately do not expose or interpret the portal's stale violation field.
    assert not hasattr(reference, "violation_state")


def test_empty_rows_are_not_converted_to_a_violation_yes() -> None:
    session = FakeSession(FakeResponse({}, text=CSRF_PAGE), FakeResponse([]))
    reference = GyeonggiPortalClient(session=session).get_building_reference(LAND)

    assert reference.state is PortalBuildingState.NOT_LISTED
    assert reference.building_count == 0


def test_request_uses_mountain_category_and_timeout() -> None:
    session = FakeSession(FakeResponse({}, text=CSRF_PAGE), FakeResponse([]))
    GyeonggiPortalClient(session=session).get_building_reference(MOUNTAIN)

    _, kwargs = session.post_calls[0]
    assert kwargs["data"]["pnu"] == "4111312900200010005"
    assert kwargs["data"]["lgGbn"] == "2"
    assert kwargs["timeout"] == (3.05, 15.0)
    assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert kwargs["headers"]["X-CSRF-TOKEN"] == "session-token"


@pytest.mark.parametrize("payload", [{}, "blocked", ValueError("not json")])
def test_unexpected_or_non_json_response_is_an_error(payload) -> None:
    session = FakeSession(FakeResponse({}), FakeResponse(payload))
    with pytest.raises(GyeonggiPortalError):
        GyeonggiPortalClient(session=session).get_building_reference(LAND)


def test_network_failure_is_not_mistaken_for_empty_rows() -> None:
    class BrokenSession(FakeSession):
        def get(self, url, **kwargs):
            raise requests.Timeout("offline")

    with pytest.raises(GyeonggiPortalError):
        GyeonggiPortalClient(
            session=BrokenSession(FakeResponse({}), FakeResponse([]))
        ).get_building_reference(LAND)
