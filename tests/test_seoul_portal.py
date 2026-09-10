from dataclasses import replace

import pytest
import requests
from streamlit.testing.v1 import AppTest

import app as app_module
from src.address import parse_address
from src.seoul_portal import (
    SEOUL_BUILDING_LIST_URL,
    SEOUL_PORTAL_URL,
    SeoulPortalClient,
    SeoulPortalError,
    SeoulPortalState,
    _request_fields,
    parse_reference,
)


LAND = parse_address("역삼동 737", region="서울").land_key
ROW = {
    "bldrgstPk": "1024112777", "sggCd": "11680", "bjdongCd": "10100",
    "landGbn": "1", "bonbeon": "0737", "bubeon": "0000",
    "bldNm": "강남파이낸스센터", "dongNm": "주건축물제1동",
    "regstrKindNm": "일반건축물", "mainPurpsNm": "업무시설,근린생활시설,운동시설",
    "violBldYn": "0",
}


def test_known_portal_response_is_visible_without_certifying_no_violation():
    reference = parse_reference({"result": [ROW]}, LAND)
    assert reference.state is SeoulPortalState.VISIBLE
    assert reference.buildings[0].violation_raw == "0"
    assert reference.checked_at


def test_explicit_flag_preserved_even_if_another_building_has_zero():
    reference = parse_reference({"result": [ROW, dict(ROW, bldrgstPk="other", violBldYn="1")]}, LAND)
    assert reference.state is SeoulPortalState.FLAGGED
    assert len(reference.buildings) == 2


def test_empty_result_has_its_own_noncertified_state():
    reference = parse_reference({"result": []}, LAND)
    assert reference.state is SeoulPortalState.NOT_LISTED
    assert not reference.buildings


@pytest.mark.parametrize("payload", [None, [], {}, {"result": None}, {"result": {}},
    {"result": [None]}, {"result": [{}]}, {"result": [], "error": "unavailable"}])
def test_malformed_or_failed_response_never_becomes_no_building(payload):
    with pytest.raises(SeoulPortalError):
        parse_reference(payload, LAND)


@pytest.mark.parametrize(("field", "value"), [("sggCd", "41117"), ("bjdongCd", "10700"),
    ("landGbn", "2"), ("bonbeon", "0738"), ("bubeon", "0001"), ("bonbeon", None)])
def test_related_parcel_or_missing_address_is_not_applied_to_searched_parcel(field, value):
    with pytest.raises(SeoulPortalError, match="다른 지번"):
        parse_reference({"result": [dict(ROW, **{field: value})]}, LAND)


def test_mountain_request_uses_pnu_land_category():
    assert _request_fields(replace(LAND, plat_gb_cd="1"))["landGbn"] == "2"
    with pytest.raises(SeoulPortalError):
        _request_fields(parse_address("망포동 6-11").land_key)


def test_conflicting_same_register_is_an_error_but_exact_duplicates_are_removed():
    assert len(parse_reference({"result": [ROW, ROW]}, LAND).buildings) == 1
    with pytest.raises(SeoulPortalError):
        parse_reference({"result": [ROW, dict(ROW, violBldYn="1")]}, LAND)


class FakeResponse:
    def __init__(self, payload=None, *, http_error=False, json_error=False):
        self.payload = payload
        self.http_error = http_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.http_error:
            raise requests.HTTPError("upstream unavailable")

    def json(self):
        if self.json_error:
            raise ValueError("not JSON")
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_client_posts_exact_seoul_parcel_with_timeouts():
    session = FakeSession(FakeResponse({"result": [ROW]}))
    reference = SeoulPortalClient(session=session).get_building_reference(LAND)
    assert reference.state is SeoulPortalState.VISIBLE
    assert session.calls[0][0] == SEOUL_PORTAL_URL
    assert session.calls[1][0] == SEOUL_BUILDING_LIST_URL
    assert session.calls[1][1]["data"] == _request_fields(LAND)
    assert all(call[1]["timeout"] for call in session.calls)


@pytest.mark.parametrize("response", [FakeResponse(http_error=True), FakeResponse(json_error=True), requests.Timeout()])
def test_transport_failures_are_not_empty_building_results(response):
    with pytest.raises(SeoulPortalError):
        SeoulPortalClient(session=FakeSession(response)).get_building_reference(LAND)


@pytest.mark.parametrize("payload", [{"result": []}, {"result": [ROW]},
    {"result": [dict(ROW, violBldYn="1")]}, None])
def test_portal_check_is_opt_in_and_renders_distinct_results(monkeypatch, payload):
    calls = []

    def lookup(*args):
        calls.append(args)
        if payload is None:
            raise SeoulPortalError("서울포털 연결이 지연되었습니다. 위반 여부는 확인되지 않았습니다.")
        return parse_reference(payload, LAND)

    monkeypatch.setattr(app_module, "_seoul_portal_cached", lookup)
    app = AppTest.from_string('''
import app
from src.address import parse_address
app._render_violation(parse_address("역삼동 737", region="서울"))
''', default_timeout=10)
    app.run()
    assert not app.exception and not calls
    app.button[0].click().run()
    assert not app.exception and len(calls) == 1
    messages = " ".join(item.value for item in (*app.info, *app.warning))
    if payload is None:
        assert "연결이 지연" in messages and "미표시" not in messages
    elif not payload["result"]:
        assert "미표시" in messages and "확정할 수 없습니다" in messages
    elif payload["result"][0]["violBldYn"] == "1":
        assert "위반 표시가 있습니다" in messages
    else:
        assert "목록 1건" in messages and "위반이 없다는 뜻은 아닙니다" in messages
    links = {item.label for item in app.get("link_button")}
    assert "세움터 대장 열람" in links
    assert "서울부동산정보광장 직접 보기" in links
