import pytest
import requests
from streamlit.testing.v1 import AppTest

import app as app_module
from src.address import parse_address
from src.seoul_candidates import CandidateSearchError, ParcelCandidates, SeoulCandidateClient
from src.seoul_search import parse_lot_number, search_seoul_lot


LOT = parse_lot_number("332-37")
ADDRESS = parse_address("독산동 332-37", region="서울")
OTHER = parse_address("서교동 332-37", region="서울")
PNU = "1154510200103320037"


def row(pnu=PNU, doc="1"):
    return {"PNU": pnu, "DOCID": doc, "F_ADDR": "do not trust this text",
            "INFO_YN": "", "DANJI_NAME": "", "ADDR_ROAD": ""}


def payload(rows, total=None):
    return {"result": {"land": {"thisTotalCount": len(rows) if total is None else total, "colDetailList": rows}}}


class Response:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class Session:
    def __init__(self, *actions):
        self.actions = list(actions)
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append(kwargs)
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return Response(action)


def test_exact_pnu_dedup_without_filtering_blank_building_metadata():
    rows = [row(), row(doc="2"), row("1154510200103320038", "3"),
            row("1154510200203320037", "4"), row("4111710700103320037", "5")]
    session = Session(payload(rows))
    result = SeoulCandidateClient(session=session).find(LOT)
    assert result.complete and [p.land_key for p in result.parcels] == [ADDRESS.land_key]
    assert session.calls[0]["data"]["query"] == "332-37"
    assert session.calls[0]["timeout"]


def test_mountain_and_main_only_numbers_never_mix_with_normal_or_subparcels():
    session = Session(payload([row("1154510200200010005"), row("1154510200100010005", "2")]))
    result = SeoulCandidateClient(session=session).find(parse_lot_number("산1-5"))
    assert len(result.parcels) == 1 and result.parcels[0].land_key.plat_gb_cd == "1"
    result = SeoulCandidateClient(session=Session(payload([
        row("1154510200107370000"), row("1154510200107370001", "2")
    ]))).find(parse_lot_number("737"))
    assert len(result.parcels) == 1 and result.parcels[0].land_key.ji == "0000"


def test_pages_beyond_first_100_are_read_and_unique_parcels_are_retained():
    first = [row(doc=str(i)) for i in range(100)]
    second = [row("1144012000103320037", "101")]
    session = Session(payload(first, 101), payload(second, 101))
    result = SeoulCandidateClient(session=session).find(LOT)
    assert result.complete and result.received_rows == 101
    assert {p.land_key for p in result.parcels} == {ADDRESS.land_key, OTHER.land_key}
    assert [c["data"]["startCount"] for c in session.calls] == [0, 100]


def test_large_result_limit_and_repeated_pages_are_explicitly_incomplete():
    first = [row(doc=str(i)) for i in range(100)]
    result = SeoulCandidateClient(session=Session(payload(first, 1000)), max_pages=1).find(LOT)
    assert not result.complete and result.note and result.parcels
    result = SeoulCandidateClient(session=Session(payload(first, 200), payload(first, 200))).find(LOT)
    assert not result.complete and "반복" in result.note


@pytest.mark.parametrize("data", [None, {}, payload([], 100), payload([], "bad"), payload([None])])
def test_bad_responses_never_become_empty_success(data):
    with pytest.raises(CandidateSearchError):
        SeoulCandidateClient(session=Session(data)).find(LOT)


def test_invalid_pnu_is_partial_and_transport_error_is_not_no_result():
    result = SeoulCandidateClient(session=Session(payload([row(), row("bad", "2")]))).find(LOT)
    assert result.parcels and not result.complete and result.note
    with pytest.raises(CandidateSearchError) as error:
        SeoulCandidateClient(session=Session(requests.Timeout("sensitive transport detail"))).find(LOT)
    assert "sensitive" not in str(error.value)


def test_candidate_only_scan_calls_two_targets_and_full_expansion_checks_the_rest():
    calls = []
    fast = search_seoul_lot(LOT, lambda key: calls.append(key) or (), candidates=(ADDRESS, OTHER, ADDRESS))
    assert len(calls) == 2 and fast.total_dongs == 2 and fast.is_complete
    assert fast.candidate_parcels is not None
    calls.clear()
    full = search_seoul_lot(LOT, lambda key: calls.append(key) or (), previous=fast)
    assert len(calls) == 465 and full.total_dongs == 467 and full.is_complete
    assert full.candidate_parcels is None
    with pytest.raises(ValueError):
        search_seoul_lot(LOT, lambda key: (), candidates=(parse_address("역삼동 737", region="서울"),))


def test_fast_adapter_is_default_and_never_calls_unlisted_dongs(monkeypatch):
    calls = []
    class Cache:
        def get(self, key, request):
            calls.append(key)
            return ()
    monkeypatch.setattr(app_module, "_secret", lambda name: "test" if name == "BUILDING_HUB_API_KEY" else None)
    monkeypatch.setattr(app_module, "_seoul_title_cache", lambda *args: Cache())
    monkeypatch.setattr(app_module, "_seoul_candidates_cached", lambda lot: ParcelCandidates((ADDRESS, OTHER), True, 20, 20))
    app = AppTest.from_string('''
import app
from src.seoul_search import parse_lot_number
result = app._run_citywide_search(parse_lot_number("332-37"))
app._render_citywide_results(result)
''', default_timeout=10).run()
    assert not app.exception and set(calls) == {ADDRESS.land_key, OTHER.land_key}
    assert any("주소 후보 2/2" in item.value for item in app.success)
    assert any(button.label == "누락 주소까지 전체 동 확인" for button in app.button)
    assert not any("서울 전체에서 해당 지번으로 조회되는 건축물대장이 없습니다" in item.value for item in app.info)


def test_discovery_outage_does_not_silently_start_467_requests(monkeypatch):
    monkeypatch.setattr(app_module, "_secret", lambda name: "test")
    def fail(lot):
        raise CandidateSearchError("주소 검색 연결 실패")
    monkeypatch.setattr(app_module, "_seoul_candidates_cached", fail)
    monkeypatch.setattr(app_module, "_seoul_title_cache", lambda *args: pytest.fail("No broad scan without explicit action"))
    app = AppTest.from_string('''
import app
from src.seoul_search import parse_lot_number
result = app._run_citywide_search(parse_lot_number("332-37"))
app._render_citywide_results(result)
''', default_timeout=10).run()
    assert not app.exception and not app.success
    assert any("주소 검색 연결 실패" in item.value for item in app.warning)
