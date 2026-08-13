from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from app import SearchOutcome
from src.address import LandKey, ParsedAddress


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
        purpose_name="house",
        approval_date="20200101",
        other_purpose=None,
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
    app = AppTest.from_file("app.py", default_timeout=10)
    app.session_state["search_outcome"] = _outcome()
    app.run()

    assert not app.exception
    assert [button.label for button in app.button] == [
        "정보 확인하기",
        "경기부동산포털 1차 확인",
    ]
    links = {item.label: item.url for item in app.get("link_button")}
    assert links["경기포털에서 직접 보기"].endswith(
        "code=01&pnu=4111710700100060011"
    )
    assert "CappBizCD=15000000098" in links["정부24 대장 열람"]
    rendered_text = " ".join(
        item.value for item in (*app.caption, *app.info, *app.warning)
    )
    assert "1차 확인용" in rendered_text
    assert "해당 사항 없음" not in rendered_text


def test_portal_button_is_available_when_buildinghub_returns_no_buildings() -> None:
    outcome = _outcome()
    empty_snapshot = SimpleNamespace(
        buildings=(), warnings=(), source_as_of="20260813"
    )
    app = AppTest.from_file("app.py", default_timeout=10)
    app.session_state["search_outcome"] = SearchOutcome(
        parsed=outcome.parsed,
        snapshot=empty_snapshot,
    )
    app.run()

    assert not app.exception
    assert "경기부동산포털 1차 확인" in [
        button.label for button in app.button
    ]
