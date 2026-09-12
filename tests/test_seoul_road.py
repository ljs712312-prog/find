import pytest
import requests
from streamlit.testing.v1 import AppTest

import app as app_module
from src.address import AddressParseError, parse_address
from src.lookup import TITLE_ENDPOINT, lookup_register
from src.seoul_candidates import CandidateSearchError, KeywordRows, SeoulCandidateClient
from src.seoul_road import (
    RoadAddress, RoadCandidate, RoadSearchResult, SeoulRoadClient, parse_road_address,
)


ROAD = RoadAddress("은천로5길", 26)
PARCEL = parse_address("관악구 봉천동 645-77", region="서울")
PNU = "1162010100106450077"


@pytest.mark.parametrize("value", [
    "은천로5길 26", "은천로5길26", "은천로5길 ２６", "은천로5길 26 (봉천동)",
    "서울 은천로5길 26", "서울시 은천로5길 26", "서울특별시 은천로5길 26",
])
def test_road_input_supports_copied_and_short_addresses(value):
    assert parse_road_address(value) == ROAD


def test_district_subnumber_and_underground_are_preserved():
    value = parse_road_address("서울특별시 강남구 테헤란로 ０１５２–１ (역삼동, 건물명)")
    assert value == RoadAddress("테헤란로", 152, 1, "강남구")
    assert value.query == "강남구 테헤란로 152-1"
    assert parse_road_address("중구 세종대로 지하 101").underground
    assert parse_road_address("강북구 4.19로 8").road == "4.19로"
    assert parse_road_address("봉천동 645-77") is None
    assert parse_road_address("645-77") is None


@pytest.mark.parametrize("value", [
    "경기도 수원시 영통구 광교중앙로 145", "부산광역시 중구 중앙대로 1",
    "가짜구 은천로5길 26", "관악구 은천로5길 0", "은천로5길", "은천로5길 26 201호",
])
def test_road_never_silently_discards_wrong_jurisdiction_or_extra_numbers(value):
    with pytest.raises(AddressParseError):
        parse_road_address(value)


def row(road="서울특별시 관악구 은천로5길 26", pnu=PNU, doc="1"):
    return {"ADDR_ROAD": road, "PNU": pnu, "DOCID": doc, "INFO_YN": "",
            "DANJI_NAME": "", "F_ADDR": "untrusted address"}


class KeywordClient:
    def __init__(self, rows, complete=True):
        self.rows, self.complete, self.calls = rows, complete, []
    def search_rows(self, query):
        self.calls.append(query)
        return KeywordRows(tuple(self.rows), self.complete, len(self.rows), len(self.rows),
                           None if self.complete else "일부 후보")


def test_exact_road_number_pnu_and_html_highlight_matching():
    client = KeywordClient([
        row("서울특별시 관악구 <font color='red'>은천로5길</font> <font>26</font>"),
        row(doc="duplicate"), row("서울특별시 관악구 은천로5길 26-1", doc="2"),
        row("서울특별시 관악구 은천로5길 260", doc="3"),
        row("서울특별시 관악구 은천로 26", doc="4"),
        row("서울특별시 관악구 은천로5길 지하 26", doc="5"), row("", doc="6"),
        row("서울특별시 관악구 은천로5길 26 3층[301호](봉천동)", doc="7"),
    ])
    result = SeoulRoadClient(keyword_client=client).find(ROAD)
    assert result.complete and len(result.matches) == 1
    assert result.matches[0].parsed.land_key == PARCEL.land_key
    assert result.matches[0].road_address == "서울특별시 관악구 은천로5길 26"
    assert client.calls == ["은천로5길 26"]


def test_duplicate_road_names_return_all_parcels_and_district_can_narrow():
    client = KeywordClient([
        row("서울특별시 관악구 중앙로 1"),
        row("서울특별시 금천구 중앙로 1", "1154510200103320037", "2"),
        row("서울특별시 관악구 중앙로 1", "1162010100206450077", "3"),
    ])
    result = SeoulRoadClient(keyword_client=client).find(RoadAddress("중앙로", 1))
    assert result.complete and len(result.matches) == 3
    assert {c.parsed.is_mountain for c in result.matches} == {True, False}
    result = SeoulRoadClient(keyword_client=client).find(RoadAddress("중앙로", 1, district="금천구"))
    assert len(result.matches) == 1 and result.matches[0].parsed.district == "금천구"


@pytest.mark.parametrize("bad", [
    row(pnu="bad"), row(pnu="1162010100306450077"), row(pnu="1162010100100000077"),
    row(pnu="4111710700106450077"), row(pnu="1199910100106450077"),
    row(pnu="1154510200103320037"),
])
def test_unverified_road_parcel_link_is_not_a_successful_unique_match(bad):
    result = SeoulRoadClient(keyword_client=KeywordClient([row(), bad])).find(ROAD)
    assert len(result.matches) == 1 and not result.complete and result.note


class Response:
    def __init__(self, rows, total):
        self.data = {"result": {"land": {"thisTotalCount": total, "colDetailList": rows}}}
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class Session:
    def __init__(self, responses):
        self.responses, self.offsets = list(responses), []
    def post(self, url, **kwargs):
        self.offsets.append(kwargs["data"]["startCount"])
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_exact_road_can_be_on_later_keyword_page_and_limit_stays_partial():
    first = [row("서울특별시 관악구 은천로5길 26-1", doc=str(i)) for i in range(100)]
    session = Session([Response(first, 101), Response([row(doc="last")], 101)])
    result = SeoulRoadClient(keyword_client=SeoulCandidateClient(session=session)).find(ROAD)
    assert result.complete and len(result.matches) == 1 and session.offsets == [0, 100]
    first[0] = row()
    result = SeoulRoadClient(keyword_client=SeoulCandidateClient(
        session=Session([Response(first, 101)]), max_pages=1,
    )).find(ROAD)
    assert result.matches and not result.complete
    with pytest.raises(CandidateSearchError):
        SeoulRoadClient(keyword_client=SeoulCandidateClient(
            session=Session([requests.Timeout("private request details")]), max_retries=0,
        )).find(ROAD)


def candidate(parsed=PARCEL):
    return RoadCandidate(parsed, "서울특별시 관악구 은천로5길 26")


def outcome_for(parsed):
    class Client:
        def fetch_all(self, endpoint, land_key, **kwargs):
            return [{**land_key.as_api_params(), "mgmBldrgstPk": "TEST-1",
                     "regstrGbCd": "1", "platPlc": parsed.canonical_address,
                     "mainPurpsCdNm": "단독주택", "etcPurps": "다가구용단독주택(8가구)",
                     "fmlyCnt": "8", "totArea": "329.86", "grndFlrCnt": "3"}] if endpoint == TITLE_ENDPOINT else []
    return app_module.SearchOutcome(parsed, snapshot=lookup_register(Client(), parsed))


def setup_ui(monkeypatch, result):
    calls = []
    class CachedRoad:
        cleared = []
        def __call__(self, address):
            return result
        def clear(self, address):
            self.cleared.append(address)
    cached = CachedRoad()
    monkeypatch.setattr(app_module, "_seoul_road_cached", cached)
    monkeypatch.setattr(app_module, "_secret", lambda name: None)
    def search(query, *args, **kwargs):
        parsed = parse_address(query, region="서울")
        calls.append(parsed)
        return outcome_for(parsed)
    monkeypatch.setattr(app_module, "_search", search)
    monkeypatch.setattr(app_module, "_run_citywide_search", lambda *a, **k: pytest.fail("Road input must not scan every dong"))
    app = AppTest.from_string("import app\napp.render_app()", default_timeout=15).run()
    app.text_input[0].set_value("은천로5길 26")
    app.button[0].click().run()
    assert not app.exception
    return app, calls, cached


def test_unique_road_automatically_queries_exact_parcel_and_links_portal(monkeypatch):
    app, calls, _ = setup_ui(monkeypatch, RoadSearchResult(ROAD, (candidate(),), True))
    assert [c.land_key for c in calls] == [PARCEL.land_key]
    assert any("봉천동 645-77" in info.value for info in app.info)
    links = {item.label: item.url for item in app.get("link_button")}
    assert "bobn=0645&bubn=0077" in links["서울부동산정보광장 직접 보기"]
    assert app.metric


def test_multiple_road_candidates_require_selection_and_clear_stale_details(monkeypatch):
    other = parse_address("관악구 봉천동 645-78", region="서울")
    app, calls, _ = setup_ui(monkeypatch, RoadSearchResult(ROAD, (candidate(), candidate(other)), True))
    assert not calls and not app.metric
    assert next(b for b in app.button if b.label == "선택한 지번 상세 조회").disabled
    app.selectbox(key="seoul_road_choice").set_value(PARCEL.canonical_address).run()
    next(b for b in app.button if b.label == "선택한 지번 상세 조회").click().run()
    assert not app.exception and len(calls) == 1 and app.metric
    app.selectbox(key="seoul_road_choice").set_value(other.canonical_address).run()
    assert not app.exception and not app.metric and "search_outcome" not in app.session_state
    app.text_input[0].set_value("")
    app.button[0].click().run()
    assert not app.exception and app.error and app_module.SEOUL_ROAD_STATE_KEY not in app.session_state


def test_partial_unique_result_does_not_auto_pick_and_does_not_stay_cached(monkeypatch):
    app, calls, cached = setup_ui(monkeypatch, RoadSearchResult(ROAD, (candidate(),), False, "일부 후보"))
    assert not calls and cached.cleared == [ROAD]
    assert any("일부 후보" in warning.value for warning in app.warning)


def test_empty_result_and_network_failure_cannot_leave_old_building_visible(monkeypatch):
    app, calls, _ = setup_ui(monkeypatch, RoadSearchResult(ROAD, (), True))
    assert not calls and not app.metric and any("찾지 못했습니다" in i.value for i in app.info)
    app.session_state["search_outcome"] = outcome_for(PARCEL)
    def fail(address):
        raise CandidateSearchError("서울포털 연결 실패")
    monkeypatch.setattr(app_module, "_seoul_road_cached", fail)
    app.button[0].click().run()
    assert not app.exception and not app.metric and "search_outcome" not in app.session_state
    assert any("연결 실패" in error.value for error in app.error)


def test_existing_legal_dong_ending_in_ro_keeps_lot_interpretation(monkeypatch):
    app, calls, _ = setup_ui(monkeypatch, RoadSearchResult(ROAD, (), True))
    monkeypatch.setattr(app_module, "_seoul_road_cached", lambda *a: pytest.fail("Existing lot input must not become a road"))
    app.text_input[0].set_value("세종로 1")
    app.button[0].click().run()
    assert not app.exception and calls[-1].legal_dong == "세종로" and calls[-1].lot_number == "1"
