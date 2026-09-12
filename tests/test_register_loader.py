from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event, Lock, get_ident

import pytest

from src.address import parse_address
from src.building_hub import BuildingHubAPIError, BuildingHubAuthError, BuildingHubNetworkError
from src.lookup import LOOKUP_ENDPOINTS, TITLE_ENDPOINT, FLOOR_ENDPOINT, BASIS_ENDPOINT, lookup_register
from src.register_loader import RegisterSectionCache, load_register_parallel


LAND = parse_address("관악구 봉천동 645-77", region="서울").land_key


def rows(endpoint):
    base = {**LAND.as_api_params(), "mgmBldrgstPk": "BUILDING"}
    if endpoint == TITLE_ENDPOINT:
        return [{**base, "bldNm": "테스트 건물", "fmlyCnt": "8", "totArea": "329.86"}]
    if endpoint == FLOOR_ENDPOINT:
        return [{**base, "flrNoNm": "3층", "etcPurps": "주택(1가구)", "area": "74.86"}]
    return []


def test_parallel_fetch_overlaps_three_workers_keeps_data_and_reuses_cached_sections():
    barrier, lock = Barrier(3), Lock()
    clients, calls = [], []
    active, peak = 0, 0
    class Client:
        def __init__(self):
            self.thread, self.closed = get_ident(), False
            clients.append(self)
        def fetch_all(self, endpoint, land_key, **kwargs):
            nonlocal active, peak
            assert self.thread == get_ident() and not self.closed and land_key == LAND
            with lock:
                calls.append(endpoint)
                if endpoint != TITLE_ENDPOINT:
                    active += 1
                    peak = max(peak, active)
            if endpoint in LOOKUP_ENDPOINTS[1:4]:
                barrier.wait(timeout=3)
            with lock:
                if endpoint != TITLE_ENDPOINT:
                    active -= 1
            return rows(endpoint)
        def close(self):
            self.closed = True
    cache = RegisterSectionCache(interval=0)
    result = load_register_parallel(LAND, Client, cache)
    assert not result.is_partial and peak == 3
    assert calls[0] == TITLE_ENDPOINT and set(calls) == set(LOOKUP_ENDPOINTS)
    assert 2 <= len(clients) <= 4 and all(client.closed for client in clients)
    building = result.buildings[0]
    assert building.family_count == 8 and building.total_area == Decimal("329.86")
    assert building.floors[0].other_purpose == "주택(1가구)"
    assert load_register_parallel(LAND, Client, cache) == result
    assert len(calls) == 6


@pytest.mark.parametrize("failure", [
    BuildingHubAPIError("05", "SERVICETIMEOUT_ERROR", retryable=True),
    BuildingHubNetworkError(endpoint=FLOOR_ENDPOINT, attempts=3, reason="connection"),
])
def test_partial_failure_preserves_other_sections_then_retries_only_failed_one(failure):
    calls = Counter()
    class Client:
        def fetch_all(self, endpoint, land_key, **kwargs):
            calls[endpoint] += 1
            if endpoint == FLOOR_ENDPOINT and calls[endpoint] == 1:
                raise failure
            return rows(endpoint)
        def close(self):
            pass
    cache = RegisterSectionCache(interval=0)
    first = load_register_parallel(LAND, Client, cache)
    assert first.is_partial and len(first.buildings) == 1
    assert [item.endpoint for item in first.unavailable_endpoints] == [FLOOR_ENDPOINT]
    second = load_register_parallel(LAND, Client, cache)
    assert not second.is_partial and second.buildings[0].floors[0].area == Decimal("74.86")
    assert calls[FLOOR_ENDPOINT] == 2 and all(calls[e] == 1 for e in LOOKUP_ENDPOINTS if e != FLOOR_ENDPOINT)


def test_prefetched_later_rows_survive_earlier_connection_failure():
    class Client:
        def fetch_all(self, endpoint, land_key, **kwargs):
            if endpoint == BASIS_ENDPOINT:
                raise BuildingHubNetworkError(endpoint=endpoint, attempts=3, reason="connection")
            return rows(endpoint)
        def close(self):
            pass
    result = load_register_parallel(LAND, Client, RegisterSectionCache(interval=0))
    assert [item.endpoint for item in result.unavailable_endpoints] == [BASIS_ENDPOINT]
    assert result.buildings[0].floors


@pytest.mark.parametrize("endpoint", [TITLE_ENDPOINT, FLOOR_ENDPOINT])
def test_auth_errors_stay_errors_and_title_failure_starts_no_details(endpoint):
    calls = []
    class Client:
        def fetch_all(self, target, land_key, **kwargs):
            calls.append(target)
            if target == endpoint:
                raise BuildingHubAuthError("30", "denied")
            return rows(target)
        def close(self):
            pass
    with pytest.raises(BuildingHubAuthError):
        load_register_parallel(LAND, Client, RegisterSectionCache(interval=0))
    if endpoint == TITLE_ENDPOINT:
        assert calls == [TITLE_ENDPOINT]


def test_title_service_timeout_is_not_an_empty_building_result():
    class Client:
        def fetch_all(self, endpoint, land_key, **kwargs):
            raise BuildingHubAPIError("05", "SERVICETIMEOUT_ERROR", retryable=True)
        def close(self):
            pass
    with pytest.raises(BuildingHubAPIError):
        load_register_parallel(LAND, Client, RegisterSectionCache(interval=0))


def test_cache_single_flight_failure_recovery_copy_isolation_and_expiry():
    started, release = Event(), Event()
    calls = []
    now = [0.0]
    cache = RegisterSectionCache(interval=0, ttl=10, clock=lambda: now[0])
    def request():
        calls.append(1)
        started.set()
        assert release.wait(3)
        return [{"value": [1]}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.get, FLOOR_ENDPOINT, LAND, request)
        assert started.wait(3)
        second = pool.submit(cache.get, FLOOR_ENDPOINT, LAND, request)
        release.set()
        a, b = first.result(), second.result()
    a[0]["value"].append(2)
    assert b == [{"value": [1]}] and calls == [1]
    assert cache.get(FLOOR_ENDPOINT, LAND, request) == b
    now[0] = 11
    cache.get(FLOOR_ENDPOINT, LAND, request)
    assert calls == [1, 1]
    def fail():
        raise BuildingHubNetworkError(endpoint=BASIS_ENDPOINT, attempts=1, reason="connection")
    with pytest.raises(BuildingHubNetworkError):
        cache.get(BASIS_ENDPOINT, LAND, fail)
    assert cache.get(BASIS_ENDPOINT, LAND, lambda: []) == []


def test_empty_titles_are_not_cached_and_rows_bound_memory():
    cache = RegisterSectionCache(interval=0, max_rows=2, max_entries=2)
    assert cache.get(TITLE_ENDPOINT, LAND, lambda: []) == []
    assert cache.get(TITLE_ENDPOINT, LAND, lambda: rows(TITLE_ENDPOINT))
    cache.get(FLOOR_ENDPOINT, LAND, lambda: [{"x": 1}, {"x": 2}])
    assert cache._row_count == 2 and len(cache._entries) == 1
    assert cache.get(TITLE_ENDPOINT, LAND, lambda: [{"fresh": True}]) == [{"fresh": True}]


def test_invalid_payload_does_not_poison_success_cache():
    cache = RegisterSectionCache(interval=0)
    from src.lookup import LookupDataError
    with pytest.raises(LookupDataError):
        cache.get(FLOOR_ENDPOINT, LAND, lambda: None)
    assert cache.get(FLOOR_ENDPOINT, LAND, lambda: []) == []


def test_partial_retry_button_preserves_road_mapping_and_restores_details(monkeypatch):
    import app as app_module
    from streamlit.testing.v1 import AppTest
    from src.seoul_road import RoadAddress, RoadCandidate, RoadSearchResult
    parsed = parse_address("관악구 봉천동 645-77", region="서울")
    class Client:
        def fetch_all(self, endpoint, land_key, **kwargs):
            if endpoint == FLOOR_ENDPOINT:
                raise BuildingHubAPIError("05", "SERVICETIMEOUT_ERROR", retryable=True)
            return rows(endpoint)
    partial = lookup_register(Client(), LAND)
    calls = []
    class GoodClient:
        def fetch_all(self, endpoint, land_key, **kwargs):
            return rows(endpoint)
    def search(query, *args, **kwargs):
        calls.append(query)
        return app_module.SearchOutcome(parsed=parsed, snapshot=lookup_register(GoodClient(), LAND))
    monkeypatch.setattr(app_module, "_search", search)
    monkeypatch.setattr(app_module, "_secret", lambda name: None)
    road = RoadSearchResult(RoadAddress("은천로5길", 26),
                            (RoadCandidate(parsed, "서울특별시 관악구 은천로5길 26"),), True)
    app = AppTest.from_string("import app\napp.render_app()", default_timeout=15)
    app.session_state["search_outcome"] = app_module.SearchOutcome(parsed=parsed, snapshot=partial)
    app.session_state[app_module.SEOUL_ROAD_STATE_KEY] = road
    app.run()
    next(b for b in app.button if b.label == "누락된 상세 정보 다시 확인").click().run()
    assert not app.exception and calls == [parsed.canonical_address]
    assert app.session_state[app_module.SEOUL_ROAD_STATE_KEY] == road
    assert any("74.86" in str(frame.value) for frame in app.dataframe)
    assert not any(b.label == "누락된 상세 정보 다시 확인" for b in app.button)
