from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from app import PERMIT_LOOKUP_STATE_KEY, SearchOutcome
from src.address import LandKey, ParsedAddress
from src.permit_lookup import (
    PermitAreaCategory,
    PermitCaseReference,
    PermitEndpointStats,
    PermitFloorReference,
    PermitHouseholdReference,
    PermitParcelReference,
    PermitUnassignedAreaReference,
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


def _case(
    case_pk: str,
    *,
    use_approval_date: str,
    area: str,
    ho_name: str,
    matches_register_approval_date: bool,
) -> PermitCaseReference:
    unit = PermitUnitReference(
        case_pk=case_pk,
        unit_pk=f"UNIT-{case_pk}",
        dong_pk=f"DONG-{case_pk}",
        dong_name="주건축물",
        ho_number=ho_name.removesuffix("호"),
        ho_name=ho_name,
        floor_group_name="지상",
        floor_number=2,
        change_name="신규",
        exclusive_area=Decimal(area),
        common_area=Decimal("0"),
        other_area=None,
        area_components=(),
    )
    return PermitCaseReference(
        case_pk=case_pk,
        building_name="다가구 테스트",
        application_type="신축",
        permit_date="20180101",
        use_approval_date=use_approval_date,
        source_as_of="20260814",
        expected_family_count=1,
        expected_household_count=None,
        housing_types=("다가구주택",),
        matches_register_approval_date=matches_register_approval_date,
        units=(unit,),
    )


def _reference(*cases: PermitCaseReference) -> PermitHouseholdReference:
    return PermitHouseholdReference(
        land_key=LAND,
        cases=cases,
        unlinked_unit_count=0,
        orphan_area_count=0,
        endpoint_stats=(),
        warnings=(),
        source_as_of="20260814",
    )


def _precision_fallback_case() -> PermitCaseReference:
    return PermitCaseReference(
        case_pk="CURRENT",
        building_name="영화동 다가구",
        application_type="신축",
        permit_date="20220705",
        use_approval_date="20190902",
        source_as_of="20231205",
        expected_family_count=6,
        expected_household_count=None,
        housing_types=(),
        matches_register_approval_date=True,
        units=(),
        unassigned_areas=(
            PermitUnassignedAreaReference(
                case_pk="CURRENT",
                area_pk="AREA-1",
                plan_name="201호",
                floor_group_name="지상",
                floor_number=2,
                category=PermitAreaCategory.EXCLUSIVE,
                purpose_name="단독주택",
                other_purpose="다가구주택",
                area=Decimal("31.25"),
                source_as_of="20231205",
            ),
        ),
        permit_floors=(
            PermitFloorReference(
                case_pk="CURRENT",
                floor_pk="FLOOR-2",
                dong_pk="DONG-1",
                building_name="주건축물",
                floor_group_name="지상",
                floor_number=2,
                purpose_name="단독주택",
                structure_name="철근콘크리트구조",
                area=Decimal("98.5"),
                source_as_of="20231205",
            ),
        ),
        parcels=(
            PermitParcelReference(
                case_pk="CURRENT",
                parcel_pk="PARCEL-1",
                dong_pk="DONG-1",
                lot_address="수원시 영화동 396-30",
                is_representative="Y",
                related_lot_name="영화동 396-31",
                main_building_name="주동",
                source_as_of="20231205",
            ),
        ),
    )


def _precision_reference(case: PermitCaseReference) -> PermitHouseholdReference:
    return PermitHouseholdReference(
        land_key=LAND,
        cases=(case,),
        unlinked_unit_count=0,
        orphan_area_count=0,
        endpoint_stats=(
            PermitEndpointStats("getApBasisOulnInfo", 1, 1, 1, 0, 0),
            PermitEndpointStats("getApHoOulnInfo", 0, 0, 0, 0, 0),
            PermitEndpointStats("getApExposPubuseAreaInfo", 1, 1, 1, 0, 0),
            PermitEndpointStats("getApFlrOulnInfo", 1, 1, 1, 0, 0),
        ),
        warnings=(),
        source_as_of="20231205",
    )


def _permit_state(
    *,
    reference: PermitHouseholdReference | None = None,
    error: str | None = None,
    land: LandKey = LAND,
) -> dict[str, object | None]:
    return {
        "identity": (
            land.sigungu_cd,
            land.bjdong_cd,
            land.plat_gb_cd,
            land.bun,
            land.ji,
        ),
        "reference": reference,
        "error": error,
    }


def _button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


def _rendered_text(app: AppTest) -> str:
    return " ".join(
        item.value
        for item in (
            *app.markdown,
            *app.caption,
            *app.info,
            *app.warning,
            *app.success,
        )
    )


def test_permit_lookup_waits_for_button_click_and_failure_is_isolated() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.run()

    assert not app.exception
    assert "다가구 호별면적 참고조회" in _rendered_text(app)
    assert "버튼을 누를 때만 이 정확한 지번" in _rendered_text(app)
    assert "아직 건축인허가 호별자료를 조회하지 않았습니다" in _rendered_text(app)
    assert len(app.dataframe) == 0

    _button(app, "이 지번의 인허가 호별면적 조회").click().run()

    assert not app.exception
    assert any("공식 건축HUB에서 건축물 1건" in item.value for item in app.success)
    assert any(
        "인증키가 설정되지 않았습니다" in item.value
        and "건축물대장 조회 결과에는 영향이 없습니다" in item.value
        for item in app.warning
    )


def test_matching_case_is_primary_and_other_history_is_unconfirmed() -> None:
    current = _case(
        "CURRENT",
        use_approval_date="20190902",
        area="31.25",
        ho_name="201호",
        matches_register_approval_date=True,
    )
    old = _case(
        "OLD",
        use_approval_date="20140103",
        area="22.5",
        ho_name="101호",
        matches_register_approval_date=False,
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.session_state[PERMIT_LOOKUP_STATE_KEY] = _permit_state(
        reference=_reference(current, old)
    )
    app.run()

    assert not app.exception
    rendered = _rendered_text(app)
    assert "현재 건축물대장 사용승인일과 정확히 일치" in rendered
    assert "그 사실만으로 현재 건물 귀속이 확정되지는 않습니다" in rendered
    assert "별지 제9호 또는 현재 건축물대장 확정값이 아닙니다" in rendered
    assert any(
        item.label == "과거·기타 인허가 이력(현재 건물 귀속 확인 안 됨)"
        for item in app.expander
    )
    assert len(app.dataframe) == 2
    assert app.dataframe[0].value.loc[0, "전유면적(㎡)"] == "31.25"
    assert app.dataframe[1].value.loc[0, "전유면적(㎡)"] == "22.5"


def test_precision_fallback_keeps_non_household_areas_visibly_separate() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.session_state[PERMIT_LOOKUP_STATE_KEY] = _permit_state(
        reference=_precision_reference(_precision_fallback_case())
    )
    app.run()

    assert not app.exception
    rendered = _rendered_text(app)
    assert "공개 API 채택 행: 기본 1건 · 호 0건 · 비호별 면적 1건 · 층 1건" in rendered
    assert "호 PK가 없는 인허가 전유·공용면적 1건" in rendered
    assert "현재 가구에 확정 배정하거나 호별면적과 합산하지 않습니다" in rendered
    assert "정확한 가구별 전용면적은 공개 API에 없는 별지 제9호" in rendered
    assert any(item.label == "3단계 · 인허가 층별면적(호 배정 불가)" for item in app.expander)
    assert any(item.label == "인허가 대지위치·관련지번" for item in app.expander)
    assert any(item.label == "공개 API 원문·지번검증 건수" for item in app.expander)
    assert len(app.dataframe) == 4
    assert app.dataframe[0].value.loc[0, "원문 수신"] == 1
    assert app.dataframe[1].value.loc[0, "평형구분명(원문)"] == "201호"
    assert app.dataframe[1].value.loc[0, "면적(㎡)"] == "31.25"


def test_raw_basis_rows_rejected_by_land_validation_are_not_reported_as_zero() -> None:
    reference = PermitHouseholdReference(
        land_key=LAND,
        cases=(),
        unlinked_unit_count=0,
        orphan_area_count=0,
        endpoint_stats=(
            PermitEndpointStats("getApBasisOulnInfo", 2, 0, 0, 2, 0),
        ),
        warnings=("요청 지번과 정확히 일치하지 않는 2개 행을 제외했습니다.",),
        source_as_of=None,
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.session_state[PERMIT_LOOKUP_STATE_KEY] = _permit_state(reference=reference)
    app.run()

    assert not app.exception
    rendered = _rendered_text(app)
    assert "기본개요 원문 2건을 받았지만" in rendered
    assert "지번 5개 항목 검증을 통과한 행이 없습니다" in rendered
    assert "기본개요 원문을 0건 반환" not in rendered


def test_no_approval_date_match_marks_every_case_unconfirmed() -> None:
    old = _case(
        "OLD",
        use_approval_date="20140103",
        area="22.5",
        ho_name="101호",
        matches_register_approval_date=False,
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.session_state[PERMIT_LOOKUP_STATE_KEY] = _permit_state(
        reference=_reference(old)
    )
    app.run()

    assert not app.exception
    assert any(
        "정확히 일치하는 인허가 이력이 없습니다" in item.value
        and "비확정 자료" in item.value
        for item in app.warning
    )
    assert any(
        item.label == "과거·기타 인허가 이력(현재 건물 귀속 확인 안 됨)"
        for item in app.expander
    )
    assert "현재 대장 승인일 일치" not in _rendered_text(app)


def test_permit_state_for_another_exact_lot_is_not_rendered() -> None:
    current = _case(
        "CURRENT",
        use_approval_date="20190902",
        area="31.25",
        ho_name="201호",
        matches_register_approval_date=True,
    )
    another_lot = LandKey("41113", "12600", "0", "0092", "0008")
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.session_state[PERMIT_LOOKUP_STATE_KEY] = _permit_state(
        reference=_reference(current),
        land=another_lot,
    )
    app.run()

    assert not app.exception
    assert len(app.dataframe) == 0
    assert "아직 건축인허가 호별자료를 조회하지 않았습니다" in _rendered_text(app)
    assert PERMIT_LOOKUP_STATE_KEY not in app.session_state


def test_new_search_clears_permit_session_state() -> None:
    current = _case(
        "CURRENT",
        use_approval_date="20190902",
        area="31.25",
        ho_name="201호",
        matches_register_approval_date=True,
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.session_state["search_outcome"] = _base_outcome()
    app.session_state[PERMIT_LOOKUP_STATE_KEY] = _permit_state(
        reference=_reference(current)
    )
    app.run()

    _button(app, "정보 확인하기").click().run()

    assert not app.exception
    assert PERMIT_LOOKUP_STATE_KEY not in app.session_state
    assert any("지번 주소를 입력해 주세요" in item.value for item in app.error)
