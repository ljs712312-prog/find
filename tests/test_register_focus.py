from collections import Counter
from decimal import Decimal
from threading import Event, get_ident

import pytest

from src.address import parse_address
from src.building_hub import BuildingHubAPIError, BuildingHubAuthError
from src.lookup import BASIS_ENDPOINT, FLOOR_ENDPOINT, TITLE_ENDPOINT
from src.register_loader import RegisterSectionCache, load_register_focus


LAND = parse_address("신림동 10-380", region="서울").land_key
BASE = {**LAND.as_api_params(), "mgmBldrgstPk": "TITLE"}


def data(endpoint):
    if endpoint == TITLE_ENDPOINT:
        return [{**BASE, "mainPurpsCdNm": "제2종근린생활시설", "totArea": "772.8"}]
    if endpoint == FLOOR_ENDPOINT:
        return [
            {**BASE, "flrNoNm": "1층", "etcPurps": "고시원", "area": "100.8"},
            {**BASE, "flrNoNm": "1층", "etcPurps": "주차장", "area": "70.77"},
        ]
    return []


class Client:
    def __enter__(self):
        self.thread = get_ident()
        return self

    def __exit__(self, *args):
        assert self.thread == get_ident()

    def fetch_all(self, endpoint, land_key, **kwargs):
        assert self.thread == get_ident() and land_key == LAND
        return data(endpoint)


def test_title_is_delivered_before_floor_finishes_and_only_two_sections_are_used():
    released, floor_started = Event(), Event()
    calls, updates = Counter(), []
    caller = get_ident()

    class SlowFloor(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            calls[endpoint] += 1
            if endpoint == FLOOR_ENDPOINT:
                floor_started.set()
                assert released.wait(3), "Title preview must not wait for floors"
            else:
                assert floor_started.wait(3), "The two requests must overlap"
            return super().fetch_all(endpoint, land_key, **kwargs)

    def update(snapshot, pending):
        assert get_ident() == caller
        updates.append((snapshot, pending))
        if pending:
            assert pending == frozenset({FLOOR_ENDPOINT})
            assert snapshot.buildings[0].purpose_name == "제2종근린생활시설"
            assert not snapshot.buildings[0].floors
            released.set()

    cache = RegisterSectionCache(interval=0)
    result = load_register_focus(LAND, SlowFloor, cache, on_update=update)
    assert calls == {TITLE_ENDPOINT: 1, FLOOR_ENDPOINT: 1}
    assert len(updates) == 2 and not updates[-1][1]
    assert not result.is_partial
    # Same-floor entries represent different uses and must not be collapsed.
    assert [(f.other_purpose, f.area) for f in result.buildings[0].floors] == [
        ("고시원", Decimal("100.8")), ("주차장", Decimal("70.77")),
    ]
    assert load_register_focus(LAND, SlowFloor, cache) == result
    assert calls == {TITLE_ENDPOINT: 1, FLOOR_ENDPOINT: 1}


def test_floor_can_arrive_first_without_losing_rows():
    floor_done = Event()
    class FloorFirst(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            if endpoint == TITLE_ENDPOINT:
                assert floor_done.wait(3)
            else:
                floor_done.set()
            return data(endpoint)
    result = load_register_focus(LAND, FloorFirst, RegisterSectionCache(interval=0))
    assert len(result.buildings[0].floors) == 2


@pytest.mark.parametrize("parent", ["TITLE", "UNKNOWN"])
def test_only_unlinked_floor_rows_trigger_extra_relationship_lookup(parent):
    calls = Counter()
    class Related(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            calls[endpoint] += 1
            if endpoint == FLOOR_ENDPOINT:
                return [{**data(endpoint)[0], "mgmBldrgstPk": "CHILD"}]
            if endpoint == BASIS_ENDPOINT:
                return [{**BASE, "mgmBldrgstPk": "CHILD", "mgmUpBldrgstPk": parent}]
            return data(endpoint)
    result = load_register_focus(LAND, Related, RegisterSectionCache(interval=0))
    assert calls == {TITLE_ENDPOINT: 1, FLOOR_ENDPOINT: 1, BASIS_ENDPOINT: 1}
    if parent == "TITLE":
        assert len(result.buildings[0].floors) == 1 and not result.unlinked_floors
    else:
        assert not result.buildings[0].floors and len(result.unlinked_floors) == 1


def test_failed_floor_is_not_cached_or_reported_as_empty_and_retry_reuses_title():
    calls = Counter()
    class Retry(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            calls[endpoint] += 1
            if endpoint == FLOOR_ENDPOINT and calls[endpoint] == 1:
                raise BuildingHubAPIError("05", "SERVICETIMEOUT_ERROR", retryable=True)
            return data(endpoint)
    cache = RegisterSectionCache(interval=0)
    first = load_register_focus(LAND, Retry, cache)
    assert first.is_partial and len(first.buildings) == 1
    assert [item.endpoint for item in first.unavailable_endpoints] == [FLOOR_ENDPOINT]
    second = load_register_focus(LAND, Retry, cache)
    assert not second.is_partial and len(second.buildings[0].floors) == 2
    assert calls == {TITLE_ENDPOINT: 1, FLOOR_ENDPOINT: 2}


def test_title_auth_failure_is_not_an_empty_result():
    class Denied(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            if endpoint == TITLE_ENDPOINT:
                raise BuildingHubAuthError("30", "denied", retryable=False)
            return data(endpoint)
    with pytest.raises(BuildingHubAuthError):
        load_register_focus(LAND, Denied, RegisterSectionCache(interval=0))


def test_wrong_parcel_floor_is_rejected_without_guessing_a_relationship():
    calls = Counter()
    class WrongParcel(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            calls[endpoint] += 1
            if endpoint == FLOOR_ENDPOINT:
                return [{**data(endpoint)[0], "ji": "0381"}]
            return data(endpoint)
    result = load_register_focus(LAND, WrongParcel, RegisterSectionCache(interval=0))
    assert not result.buildings[0].floors and result.warnings
    assert calls == {TITLE_ENDPOINT: 1, FLOOR_ENDPOINT: 1}


def test_unlinked_floor_is_visible_in_ui_without_claiming_data_is_absent():
    from streamlit.testing.v1 import AppTest
    from app import SearchOutcome
    class Unlinked(Client):
        def fetch_all(self, endpoint, land_key, **kwargs):
            if endpoint == FLOOR_ENDPOINT:
                return [{**data(endpoint)[0], "mgmBldrgstPk": "UNKNOWN", "dongNm": "별동"}]
            return data(endpoint)
    snapshot = load_register_focus(LAND, Unlinked, RegisterSectionCache(interval=0))
    app = AppTest.from_string('''
import app
import streamlit as st
app._render_api(st.session_state["result"])
''')
    app.session_state["result"] = SearchOutcome(
        parsed=parse_address("신림동 10-380", region="서울"), snapshot=snapshot,
    )
    app.run()
    assert not app.exception
    assert any("건물 연결" in item.value for item in app.warning)
    assert not any("공개 API에 없습니다" in item.value for item in app.info)
    assert app.dataframe[0].value.loc[0, "동"] == "별동"
    assert app.dataframe[0].value.loc[0, "상세용도"] == "고시원"
    assert app.dataframe[0].value.loc[0, "면적(㎡)"] == "100.8"


@pytest.mark.parametrize("endpoint", [TITLE_ENDPOINT, FLOOR_ENDPOINT])
def test_transient_error_recovers_with_patient_client_in_same_search(endpoint):
    calls, rescues = Counter(), []
    class Fast(Client):
        def fetch_all(self, which, *args, **kwargs):
            calls[which] += 1
            if which == endpoint:
                raise BuildingHubAPIError("05", "timeout", retryable=True)
            return data(which)
    class Recovery(Client):
        def fetch_all(self, which, *args, **kwargs):
            rescues.append(which)
            return data(which)
    cache = RegisterSectionCache(interval=0)
    result = load_register_focus(LAND, Fast, cache, recovery_factory=Recovery)
    assert not result.is_partial and result.buildings[0].floors
    assert rescues == [endpoint]
    assert load_register_focus(LAND, Fast, cache, recovery_factory=Recovery) == result
    assert calls == {TITLE_ENDPOINT: 1, FLOOR_ENDPOINT: 1} and rescues == [endpoint]


def test_empty_title_is_confirmed_in_xml_and_a_recovered_non_residential_title_is_kept():
    calls = []
    class Fast(Client):
        def fetch_all(self, endpoint, *args, **kwargs):
            return [] if endpoint == TITLE_ENDPOINT else data(endpoint)
    class Recovery(Client):
        def fetch_all(self, endpoint, *args, **kwargs):
            calls.append((endpoint, kwargs))
            return data(endpoint)
    result = load_register_focus(LAND, Fast, RegisterSectionCache(interval=0), recovery_factory=Recovery)
    assert result.buildings[0].purpose_name == "제2종근린생활시설"
    assert calls == [(TITLE_ENDPOINT, {"num_of_rows": 100, "response_type": "xml"})]


def test_auth_failure_does_not_trigger_recovery():
    class Denied(Client):
        def fetch_all(self, endpoint, *args, **kwargs):
            raise BuildingHubAuthError("30", "denied", retryable=False)
    def forbidden():
        pytest.fail("Authentication failures must not be retried on another route")
    with pytest.raises(BuildingHubAuthError):
        load_register_focus(LAND, Denied, RegisterSectionCache(interval=0), recovery_factory=forbidden)


def test_extra_confirmation_outage_does_not_erase_valid_empty_title():
    class Empty(Client):
        def fetch_all(self, endpoint, *args, **kwargs):
            return []
    class Unavailable(Client):
        def fetch_all(self, endpoint, *args, **kwargs):
            raise BuildingHubAPIError("05", "timeout", retryable=True)
    result = load_register_focus(LAND, Empty, RegisterSectionCache(interval=0), recovery_factory=Unavailable)
    assert not result.buildings
    assert next(s for s in result.endpoint_stats if s.endpoint == TITLE_ENDPOINT).received_count == 0
