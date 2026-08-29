from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from app import SearchOutcome
from src.address import LandKey, ParsedAddress


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _outcome() -> SearchOutcome:
    building = SimpleNamespace(
        building_name="Test building",
        dong_name=None,
        register_group="general",
        lot_address="lot",
        road_address=None,
        title={},
        ground_floor_count=4,
        underground_floor_count=1,
        household_count=0,
        family_count=8,
        purpose_name="단독주택",
        approval_date="20200101",
        other_purpose="다가구주택(8가구)",
        structure_name=None,
        site_area=None,
        building_area=None,
        total_area=None,
        floors=(),
        units=(),
        is_collective=False,
        is_multi_family_house=True,
    )
    parsed = ParsedAddress(
        raw="x",
        normalized="x",
        district="x",
        legal_dong="x",
        land_key=LandKey("41117", "10700", "0", "0006", "0011"),
    )
    snapshot = SimpleNamespace(
        buildings=(building,), warnings=(), source_as_of="20260813"
    )
    return SearchOutcome(parsed=parsed, snapshot=snapshot)


def test_violation_screening_is_opt_in_and_has_official_fallback() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _outcome()
    app.run()

    assert not app.exception
    assert [button.label for button in app.button] == [
        "정보 확인하기",
        "경기부동산포털 1차 확인",
        "이 지번의 인허가 호별면적 조회",
    ]
    links = {item.label: item.url for item in app.get("link_button")}
    assert links["경기포털에서 직접 보기"].endswith(
        "code=01&pnu=4111710700100060011"
    )
    assert "CappBizCD=15000000098" in links["정부24 대장 열람"]
    assert links["개별주택가격 조회 사이트"].endswith(
        "/notice/hpindividual/search.htm"
    )
    assert "개별공시지가 조회" not in links
    rendered_text = " ".join(
        item.value for item in (*app.caption, *app.info, *app.warning)
    )
    assert "경기부동산포털 기준" in rendered_text
    assert "해당 사항 없음" not in rendered_text
    assert "공식 사이트에서 주소" in rendered_text


def test_collective_building_opens_the_unit_price_search() -> None:
    outcome = _outcome()
    collective = SimpleNamespace(
        **{
            **vars(outcome.snapshot.buildings[0]),
            "purpose_name": "공동주택",
            "other_purpose": "다세대주택",
            "units": (
                SimpleNamespace(
                    dong_name=None,
                    ho_name="201호",
                    exposures=(),
                    exclusive_area=None,
                    common_area=None,
                    purposes=(),
                ),
                SimpleNamespace(
                    dong_name=None,
                    ho_name="202호",
                    exposures=(),
                    exclusive_area=None,
                    common_area=None,
                    purposes=(),
                ),
            ),
            "is_collective": True,
            "is_multi_family_house": False,
        }
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = SearchOutcome(
        parsed=outcome.parsed,
        snapshot=SimpleNamespace(
            buildings=(collective,), warnings=(), source_as_of="20260813"
        ),
    )
    app.run()

    assert not app.exception
    assert "선택 호실 공동주택 공시가격 조회" not in [
        button.label for button in app.button
    ]
    links = {item.label: item.url for item in app.get("link_button")}
    assert links["공동주택가격 조회 사이트"].endswith(
        "/notice/town/searchPastYear.htm"
    )
    assert "개별공시가격 조회" not in links


def test_portal_button_is_available_when_buildinghub_returns_no_buildings() -> None:
    outcome = _outcome()
    empty_snapshot = SimpleNamespace(
        buildings=(), warnings=(), source_as_of="20260813"
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = SearchOutcome(
        parsed=outcome.parsed,
        snapshot=empty_snapshot,
    )
    app.run()

    assert not app.exception
    assert "경기부동산포털 1차 확인" in [
        button.label for button in app.button
    ]


def test_partial_buildinghub_snapshot_keeps_title_and_explains_missing_detail() -> None:
    outcome = _outcome()
    partial_snapshot = SimpleNamespace(
        buildings=outcome.snapshot.buildings,
        warnings=("getBrFlrOulnInfo: 이번 조회에서 상세자료를 받지 못했습니다.",),
        source_as_of="20260813",
        unavailable_endpoints=(
            SimpleNamespace(endpoint="getBrFlrOulnInfo"),
        ),
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = SearchOutcome(
        parsed=outcome.parsed,
        snapshot=partial_snapshot,
    )
    app.run()

    assert not app.exception
    rendered_warnings = " ".join(item.value for item in app.warning)
    assert "층별개요" in rendered_warnings
    assert "층별 정보는 표시하지 않습니다" in rendered_warnings
