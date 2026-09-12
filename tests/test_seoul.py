"""Seoul jurisdiction, cross-city isolation, and commercial-building regressions."""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app as app_module
from app import SearchOutcome
from src.address import (
    AddressParseError,
    SEOUL_DISTRICTS,
    SEOUL_LEGAL_DONG_CODES,
    parse_address,
)
from src.building_hub import BuildingHubNetworkError
from src.legacy import lookup_legacy
from src.lookup import FLOOR_ENDPOINT, TITLE_ENDPOINT, lookup_register


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_seoul_official_coverage_and_every_district_resolves() -> None:
    assert len(SEOUL_DISTRICTS) == 25
    assert len(SEOUL_LEGAL_DONG_CODES) == 467
    for (district, dong), code in SEOUL_LEGAL_DONG_CODES.items():
        parsed = parse_address(f"서울특별시 {district} {dong} 1", region="서울")
        assert parsed.land_key.legal_dong_code == code
        assert parsed.canonical_address == f"서울특별시 {district} {dong} 1번지"


@pytest.mark.parametrize(("query", "code", "lot", "mountain"), [
    ("역삼동 ７３７–１", "1168010100", "0737", "0"),
    ("금천구 독산동 1000", "1154510200", "1000", "0"),
    ("서울시 종로구 청운동 산 1-1번지", "1111010100", "0001", "1"),
    ("성동구 성수동2가 333-1", "1120011500", "0333", "0"),
    ("강남구 신사동 1", "1168010700", "0001", "0"),
    ("은평구 신사동 1", "1138010900", "0001", "0"),
])
def test_seoul_addresses_use_exact_api_codes(query, code, lot, mountain) -> None:
    key = parse_address(query, region="서울").land_key
    assert key.legal_dong_code == code
    assert key.bun == lot
    assert key.plat_gb_cd == mountain


@pytest.mark.parametrize("query", ["신사동 1", "서울 신사동 1", "신정동 1"])
def test_ambiguous_seoul_dongs_require_a_district(query) -> None:
    with pytest.raises(AddressParseError, match="구까지 입력"):
        parse_address(query, region="서울")


@pytest.mark.parametrize("query", [
    "부산광역시 중동 1", "수원시 장안동 1", "강남구 독산동 1", "독산1동 1",
    "테헤란로 152", "737", "역삼동 0", "역삼동 1 201호", "역삼동.* 1",
])
def test_seoul_rejects_wrong_city_district_administrative_dong_and_road(query) -> None:
    with pytest.raises(AddressParseError):
        parse_address(query, region="서울")


def test_shared_suwon_seoul_names_are_resolved_by_selected_region() -> None:
    assert parse_address("장안동 1", region="서울").land_key.sigungu_cd == "11230"
    assert parse_address("장안동 1", region="수원").land_key.sigungu_cd == "41115"


def test_seoul_cannot_fall_back_to_same_named_suwon_parcel(monkeypatch) -> None:
    parsed = parse_address("장안동 1", region="서울")
    master = pd.DataFrame([{
        "대지위치": "경기도 수원시 팔달구 장안동 1번지",
        "번": "1", "지": "0", "관리건축물대장PK": "SUWON",
    }])
    assert lookup_legacy(parsed, master, pd.DataFrame()) == ()

    def unavailable(*args, **kwargs):
        raise BuildingHubNetworkError(endpoint=TITLE_ENDPOINT, attempts=1, reason="timeout")

    def forbidden():
        pytest.fail("Seoul must not read Suwon snapshots")

    monkeypatch.setattr(app_module, "_lookup_focus_api", unavailable)
    monkeypatch.setattr(app_module, "_legacy_frames", forbidden)
    outcome = app_module._search("장안동 1", "test-key", region="서울")
    assert outcome.api_error and not outcome.legacy and not outcome.used_legacy


def _commercial_outcome(purpose="제2종근린생활시설"):
    parsed = parse_address("역삼동 737", region="서울")
    land = parsed.land_key.as_api_params()

    class FixtureClient:
        def fetch_all(self, endpoint, land_key, num_of_rows=100, **query):
            assert land_key == parsed.land_key
            if endpoint == TITLE_ENDPOINT:
                return [{
                    **land, "mgmBldrgstPk": "SEOUL-TITLE", "bldNm": "서울 테스트 건물",
                    "regstrGbCd": "1", "regstrGbCdNm": "일반",
                    "mainPurpsCdNm": purpose, "etcPurps": "근린생활시설 및 사무소",
                    "platPlc": parsed.canonical_address, "platArea": "200.5",
                    "archArea": "120.25", "totArea": "600.75", "useAprDay": "20200101",
                    "grndFlrCnt": "5", "ugrndFlrCnt": "1", "indrAutoUtcnt": "2",
                    "oudrAutoUtcnt": "3", "indrMechUtcnt": "4", "oudrMechUtcnt": "0",
                    "rideUseElvtCnt": "1", "emgenUseElvtCnt": "0",
                }]
            if endpoint == FLOOR_ENDPOINT:
                return [{
                    **land, "mgmBldrgstPk": "SEOUL-TITLE", "flrNo": "1",
                    "flrNoNm": "1층", "flrGbCd": "10", "mainPurpsCdNm": purpose,
                    "etcPurps": "일반음식점", "area": "120.25",
                }]
            return []

    return SearchOutcome(parsed=parsed, snapshot=lookup_register(FixtureClient(), parsed))


@pytest.mark.parametrize("purpose", ["제1종근린생활시설", "제2종근린생활시설", "업무시설", "공동주택", "공장"])
def test_building_purposes_are_not_filtered_and_metrics_survive(purpose) -> None:
    building = _commercial_outcome(purpose).snapshot.buildings[0]
    assert building.purpose_name == purpose
    assert building.total_area == Decimal("600.75")
    assert building.floors[0].area == Decimal("120.25")
    assert ("주차", "9대", None) in app_module._metric_cards(building)


def test_seoul_ui_renders_commercial_result_and_no_gyeonggi_actions() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=15)
    app.session_state["search_outcome"] = _commercial_outcome()
    app.run()
    assert not app.exception
    assert not app.radio
    assert app.title[0].value == "건축물대장 조회시스템"
    assert "주차" in [metric.label for metric in app.metric]
    assert "9대" in [metric.value for metric in app.metric]
    assert any("제2종근린생활시설" in info.value for info in app.info)
    assert any("120.25" in str(frame.value) for frame in app.dataframe)
    labels = [button.label for button in app.button]
    links = {item.label: item.url for item in app.get("link_button")}
    assert "경기부동산포털 1차 확인" not in labels
    assert "서울포털 위반건축물 참고 확인" in labels
    assert "경기포털에서 직접 보기" not in links
    assert "세움터 대장 열람" not in links and "정부24 대장 열람" not in links
    assert not any("가격" in label for label in links)
    assert not any("인허가" in label for label in labels)

    app.text_input[0].set_value("수원시 망포동 6-11")
    app.button[0].click().run()
    assert not app.exception
    assert "search_outcome" not in app.session_state
    assert not app.metric
    assert any("서울특별시" in error.value for error in app.error)


def test_ambiguous_search_clears_old_result_without_api_call() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=15)
    app.session_state["search_outcome"] = _commercial_outcome()
    app.run()
    app.text_input[0].set_value("신사동 1")
    app.button[0].click().run()
    assert not app.exception
    assert any("구까지 입력" in error.value for error in app.error)
    assert not app.metric
