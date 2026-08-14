from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from app import SearchOutcome
from src.address import LandKey, ParsedAddress
from src.permit_lookup import (
    PermitCaseReference,
    PermitHouseholdReference,
    PermitUnitReference,
)


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
LAND = LandKey("41113", "12600", "0", "0092", "0007")


def _base_outcome(**changes: object) -> SearchOutcome:
    building = SimpleNamespace(
        building_name="다가구 테스트",
        dong_name=None,
        register_group="일반",
        lot_address="경기도 수원시 권선구 세류동 92-7번지",
        road_address=None,
        title={},
        ground_floor_count=4,
        underground_floor_count=0,
        household_count=0,
        family_count=8,
        purpose_name="단독주택",
        approval_date="20190902",
        other_purpose="다가구주택",
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
        raw="세류동 92-7",
        normalized="세류동 92-7",
        district="권선구",
        legal_dong="세류동",
        land_key=LAND,
    )
    snapshot = SimpleNamespace(
        buildings=(building,), warnings=(), source_as_of="20260814"
    )
    values = {"parsed": parsed, "snapshot": snapshot, **changes}
    return SearchOutcome(**values)


def _reference() -> PermitHouseholdReference:
    unit = PermitUnitReference(
        case_pk="CASE-1",
        unit_pk="UNIT-201",
        dong_pk="DONG-1",
        dong_name="주건축물",
        ho_number="201",
        ho_name="201호",
        floor_group_name="지상",
        floor_number=2,
        change_name="신규",
        exclusive_area=Decimal("31.25"),
        common_area=Decimal("0"),
        other_area=None,
        area_components=(),
    )
    case = PermitCaseReference(
        case_pk="CASE-1",
        building_name="다가구 테스트",
        application_type="신축",
        permit_date="20180101",
        use_approval_date="20190902",
        source_as_of="20260814",
        expected_family_count=1,
        expected_household_count=None,
        housing_types=("다가구주택",),
        matches_register_approval_date=True,
        units=(unit,),
    )
    return PermitHouseholdReference(
        land_key=LAND,
        cases=(case,),
        unlinked_unit_count=0,
        orphan_area_count=0,
        endpoint_stats=(),
        warnings=(),
        source_as_of="20260814",
    )


def test_permit_reference_is_separate_and_explicitly_non_authoritative() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome(
        permit_reference=_reference()
    )
    app.run()

    assert not app.exception
    rendered = " ".join(
        item.value
        for item in (
            *app.markdown,
            *app.caption,
            *app.info,
            *app.warning,
        )
    )
    assert "다가구 호별면적 자동 참고조회" in rendered
    assert "별지 제9호 또는 현재 건축물대장 확정값은 아닙니다" in rendered
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.loc[0, "전유면적(㎡)"] == "31.25"


def test_permit_failure_does_not_hide_register_result() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome(
        permit_error="건축인허가 참고조회 실패",
    )
    app.run()

    assert not app.exception
    assert any("공식 건축HUB에서 건축물 1건" in item.value for item in app.success)
    assert any("위의 건축물대장 조회 결과에는 영향이 없습니다" in item.value for item in app.warning)
