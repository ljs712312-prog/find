from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event, Lock, get_ident

import pytest
from streamlit.testing.v1 import AppTest

import app as app_module
from src.address import AddressParseError, parse_address
from src.building_hub import BuildingHubNetworkError, BuildingHubQuotaError
from src.lookup import LookupDataError, TITLE_ENDPOINT, lookup_title_summaries
from src.seoul_search import (
    ParcelMatch, SeoulLotResult, TitleCache, parse_lot_number,
    search_seoul_lot, seoul_parcels,
)

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
LOT = parse_lot_number("332-37")
LAND = parse_address("금천구 독산동 332-37", region="서울").land_key


def titles(land=LAND, *, rows=None):
    class Client:
        def fetch_all(self, endpoint, key):
            assert endpoint == TITLE_ENDPOINT and key == land
            return rows if rows is not None else [{
                **land.as_api_params(), "mgmBldrgstPk": "B1", "bldNm": "테스트 건물",
                "mainPurpsCdNm": "제2종근린생활시설", "totArea": "863.35",
                "indrAutoUtcnt": "19", "oudrAutoUtcnt": "0", "indrMechUtcnt": "0", "oudrMechUtcnt": "0",
            }]
    return lookup_title_summaries(Client(), land)


@pytest.mark.parametrize(("query", "expected"), [
    ("３３２－３７", ("0332", "0037", "0")),
    ("737번지", ("0737", "0000", "0")),
    ("산 1 - 5", ("0001", "0005", "1")),
])
def test_lot_number_keeps_exact_main_sub_and_mountain(query, expected):
    lot = parse_lot_number(query)
    assert (lot.bun, lot.ji, lot.plat_gb_cd) == expected


@pytest.mark.parametrize("query", ["0", "10000", "1-10000", "-1", "1-2-3"])
def test_invalid_number_never_launches_a_sweep(query):
    with pytest.raises(AddressParseError):
        parse_lot_number(query)


def test_named_addresses_remain_on_exact_address_path():
    assert parse_lot_number("독산동 332-37") is None
    assert parse_lot_number("은평구 신사동 산1-5") is None


def test_sweep_visits_all_467_seoul_dongs_and_does_not_choose_duplicate_names():
    seen = []
    lock = Lock()
    main_thread = get_ident()
    def fetch(key):
        with lock:
            seen.append(key)
        return titles(key) if key == LAND else ()
    def progress(done, total, count):
        assert get_ident() == main_thread
        assert done <= total == 467
    result = search_seoul_lot(LOT, fetch, on_progress=progress)
    assert len(set(seen)) == 467
    assert {key.sigungu_cd for key in seen} == {p.land_key.sigungu_cd for p in seoul_parcels(LOT)}
    assert len({key.sigungu_cd for key in seen}) == 25
    assert all((key.bun, key.ji, key.plat_gb_cd) == ("0332", "0037", "0") for key in seen)
    assert result.is_complete and result.building_count == 1
    assert result.matches[0].parsed.canonical_address == "서울특별시 금천구 독산동 332-37번지"


def test_timeout_is_partial_and_retry_fetches_only_unconfirmed_dong():
    def fetch(key):
        if key == LAND:
            raise BuildingHubNetworkError(endpoint=TITLE_ENDPOINT, attempts=1, reason="timeout")
        return ()
    partial = search_seoul_lot(LOT, fetch)
    assert not partial.is_complete and len(partial.checked_dongs) == 466
    assert len(partial.failures) == 1 and partial.failures[0].parsed.land_key == LAND
    calls = []
    complete = search_seoul_lot(LOT, lambda key: calls.append(key) or titles(key), previous=partial)
    assert complete.is_complete and complete.building_count == 1 and calls == [LAND]
    with pytest.raises(ValueError):
        search_seoul_lot(parse_lot_number("737"), fetch, previous=partial)


def test_quota_stops_scheduling_and_leaves_unvisited_dongs_explicit():
    calls = []
    def fetch(key):
        calls.append(key)
        raise BuildingHubQuotaError("22", "test secret must not appear")
    result = search_seoul_lot(LOT, fetch)
    assert len(calls) <= 4 and not result.is_complete and len(result.failures) == 467
    assert "한도" in result.stopped_reason and "secret" not in str(result)


def test_time_budget_preserves_successes_and_retry_continues_remaining_dongs():
    partial = search_seoul_lot(LOT, lambda key: (), max_seconds=0)
    assert not partial.is_complete and len(partial.checked_dongs) == 4
    calls = []
    complete = search_seoul_lot(LOT, lambda key: calls.append(key) or (), previous=partial)
    assert complete.is_complete and len(calls) == 463


def test_titles_keep_multiple_buildings_and_reject_wrong_parcel_or_conflicting_pk():
    row = dict(titles()[0].title)
    assert len(titles(rows=[row, row, dict(row, mgmBldrgstPk="B2")])) == 2
    for bad_rows in ([dict(row, ji="0038")], [dict(row, mgmBldrgstPk="")], [row, dict(row, bldNm="conflict")]):
        with pytest.raises(LookupDataError):
            titles(rows=bad_rows)


def test_cache_coalesces_concurrent_calls_and_does_not_cache_errors():
    cache = TitleCache(interval=0)
    started, release = Event(), Event()
    calls = []
    def request():
        calls.append(1)
        started.set()
        assert release.wait(5)
        return titles()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(cache.get, LAND, request)
        assert started.wait(5)
        second = executor.submit(cache.get, LAND, request)
        release.set()
        assert first.result() == second.result()
    assert len(calls) == 1
    other = replace(LAND, ji="0038")
    def fail():
        raise LookupDataError("bad response")
    with pytest.raises(LookupDataError):
        cache.get(other, fail)
    assert cache.get(other, lambda: ()) == ()


def test_number_ui_lists_all_matches_then_opens_selected_exact_address(monkeypatch):
    calls = []
    parsed = parse_address("독산동 332-37", region="서울")
    result = SeoulLotResult(LOT, (ParcelMatch(parsed, titles()),),
                            tuple(p.land_key.legal_dong_code for p in seoul_parcels(LOT)), (), 467)
    monkeypatch.setattr(app_module, "_run_citywide_search", lambda lot, previous=None: result)
    def detail(query, key, **kwargs):
        calls.append(query)
        return app_module.SearchOutcome(parsed=parsed, api_error="fixture detail")
    monkeypatch.setattr(app_module, "_search", detail)
    app = AppTest.from_string("import app; app.render_app()", default_timeout=15).run()
    app.text_input[0].set_value("332-37")
    app.button[0].click().run()
    assert not app.exception and not calls
    table = app.dataframe[0].value
    assert table.iloc[0]["주소"] == parsed.canonical_address
    assert table.iloc[0]["주차대수"] == "19대"
    assert "제2종근린생활시설" in str(table)
    app.selectbox(key="seoul_address_choice").select(parsed.canonical_address).run()
    next(b for b in app.button if b.label == "선택한 주소 상세 조회").click().run()
    assert not app.exception and calls == [parsed.canonical_address]
    assert any("selectSigungu=11545" in item.url for item in app.get("link_button"))
    app.text_input[0].set_value("0")
    app.button[0].click().run()
    assert not app.exception and app.error and not app.dataframe
    assert "search_outcome" not in app.session_state and app_module.SEOUL_LOT_STATE_KEY not in app.session_state


def test_partial_empty_ui_does_not_claim_no_buildings(monkeypatch):
    def fail(key):
        raise BuildingHubQuotaError("22", "quota")
    result = search_seoul_lot(LOT, fail)
    app = AppTest.from_file(str(APP_PATH), default_timeout=15)
    app.session_state[app_module.SEOUL_LOT_STATE_KEY] = result
    app.run()
    assert not app.exception
    assert any("일부 검색 결과" in item.value for item in app.warning)
    assert not any("건축물대장이 없습니다" in item.value for item in app.info)
    assert any(b.label == "미확인 동 이어서 검색" for b in app.button)


def test_citywide_adapter_reuses_worker_connections_and_closes_every_client(monkeypatch):
    clients = []
    requests = []
    lock = Lock()
    class Client:
        def __init__(self, *args, **kwargs):
            self.thread = get_ident()
            self.closed = False
            with lock:
                clients.append(self)
        def fetch_all(self, endpoint, key):
            assert get_ident() == self.thread and not self.closed
            with lock:
                requests.append(key)
            return []
        def close(self):
            self.closed = True
    monkeypatch.setattr(app_module, "BuildingHubClient", Client)
    monkeypatch.setattr(app_module, "_secret", lambda name: "fixture-key" if name == "BUILDING_HUB_API_KEY" else None)
    monkeypatch.setattr(app_module, "_seoul_title_cache", lambda *args: TitleCache(interval=0))
    app = AppTest.from_string('''
import app
from src.seoul_search import parse_lot_number
result = app._run_citywide_search(parse_lot_number("332-37"), full_scan=True)
assert result.is_complete
''', default_timeout=15).run()
    assert not app.exception
    assert len(requests) == 467 and 1 <= len(clients) <= 4
    assert all(client.closed for client in clients)
