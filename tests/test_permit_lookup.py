from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.address import LandKey
from src.permit_lookup import (
    PERMIT_BASIS_ENDPOINT,
    PERMIT_DONG_ENDPOINT,
    PERMIT_FLOOR_ENDPOINT,
    PERMIT_GENERAL_AREA_ENDPOINT,
    PERMIT_HOUSEHOLD_AREA_ENDPOINT,
    PERMIT_HOUSEHOLD_ENDPOINT,
    PERMIT_HOUSING_TYPE_ENDPOINT,
    PERMIT_LOOKUP_ENDPOINTS,
    PERMIT_PARCEL_ENDPOINT,
    PermitAreaCategory,
    lookup_permit_households,
)


LAND = LandKey("41113", "12600", "0", "0092", "0007")


def land_row(**values: Any) -> dict[str, Any]:
    row: dict[str, Any] = LAND.as_api_params()
    row.update(values)
    return row


class MockClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def fetch_all(
        self,
        endpoint: str,
        land_key: LandKey,
        num_of_rows: int = 100,
        **query: Any,
    ) -> Any:
        assert land_key is LAND
        assert num_of_rows == 100
        assert not query
        self.calls.append(endpoint)
        return self.responses.get(endpoint, [])


def test_exact_pk_join_sums_all_explicit_components_and_keeps_zero() -> None:
    exclusive = land_row(
        mgmHoDetlPk="UNIT-201",
        mgmHoExposPubuseAreaPk="AREA-1",
        exposPubuseGbCd="1",
        exposPubuseGbCdNm="전유",
        mainPurpsCdNm="다가구주택",
        etcPurps="주거",
        area="30.25",
        crtnDay="20260801",
    )
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    bldNm="다가구주택",
                    archGbCdNm="신축",
                    archPmsDay="20180101",
                    useAprDay="20190902",
                    fmlyCnt="2",
                    crtnDay="20260802",
                )
            ],
            PERMIT_DONG_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    bldNm="주건축물",
                )
            ],
            PERMIT_HOUSEHOLD_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    mgmHoDetlPk="UNIT-201",
                    hoNm="201호",
                    flrNo="2",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    mgmHoDetlPk="UNIT-202",
                    hoNm="202호",
                    flrNo="2",
                ),
            ],
            PERMIT_HOUSEHOLD_AREA_ENDPOINT: [
                exclusive,
                exclusive.copy(),
                land_row(
                    mgmHoDetlPk="UNIT-201",
                    mgmHoExposPubuseAreaPk="AREA-2",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    mainPurpsCdNm="다가구주택",
                    etcPurps="현관",
                    area="4.75",
                ),
                land_row(
                    mgmHoDetlPk="UNIT-201",
                    mgmHoExposPubuseAreaPk="AREA-3",
                    exposPubuseGbCd="2",
                    exposPubuseGbCdNm="공용",
                    area="0",
                ),
                land_row(
                    mgmHoDetlPk="UNIT-202",
                    mgmHoExposPubuseAreaPk="AREA-4",
                    exposPubuseGbCdNm="전유",
                    area="28",
                ),
            ],
            PERMIT_HOUSING_TYPE_ENDPOINT: [
                land_row(mgmPmsrgstPk="CASE-1", hstpGbCdNm="다가구주택")
            ],
        }
    )

    result = lookup_permit_households(
        client,
        LAND,
        register_approval_dates=("20190902",),
    )

    assert client.calls == list(PERMIT_LOOKUP_ENDPOINTS)
    assert result.has_units is True
    assert result.source_as_of == "20260802"
    case = result.cases[0]
    assert case.matches_register_approval_date is True
    assert case.housing_types == ("다가구주택",)
    assert len(case.units) == 2
    first = case.units[0]
    assert first.ho_name == "201호"
    assert first.floor_name == "2층"
    assert first.exclusive_area == Decimal("35.00")
    assert first.common_area == Decimal("0")
    assert first.total_area == Decimal("35.00")
    assert first.purposes == ("주거", "현관")
    assert {
        component.category for component in first.area_components
    } == {PermitAreaCategory.EXCLUSIVE, PermitAreaCategory.COMMON}
    second = case.units[1]
    assert second.exclusive_area == Decimal("28")
    assert second.common_area is None
    assert second.total_area is None


def test_different_permit_cases_are_never_merged() -> None:
    responses: dict[str, Any] = {
        PERMIT_BASIS_ENDPOINT: [
            land_row(mgmPmsrgstPk="OLD", useAprDay="20190101"),
            land_row(mgmPmsrgstPk="NEW", useAprDay="20220101"),
        ],
        PERMIT_HOUSEHOLD_ENDPOINT: [
            land_row(mgmPmsrgstPk="OLD", mgmHoDetlPk="OLD-101", hoNm="101호"),
            land_row(mgmPmsrgstPk="NEW", mgmHoDetlPk="NEW-101", hoNm="101호"),
        ],
        PERMIT_HOUSEHOLD_AREA_ENDPOINT: [
            land_row(
                mgmHoDetlPk="OLD-101",
                mgmHoExposPubuseAreaPk="OLD-A",
                exposPubuseGbCd="1",
                area="20",
            ),
            land_row(
                mgmHoDetlPk="NEW-101",
                mgmHoExposPubuseAreaPk="NEW-A",
                exposPubuseGbCd="1",
                area="30",
            ),
        ],
    }

    result = lookup_permit_households(MockClient(responses), LAND)

    assert [case.case_pk for case in result.cases] == ["NEW", "OLD"]
    assert result.cases[0].units[0].exclusive_area == Decimal("30")
    assert result.cases[1].units[0].exclusive_area == Decimal("20")


def test_wrong_land_or_orphan_pk_is_not_guessed_and_conflict_is_not_summed() -> None:
    wrong_land = land_row(
        mgmPmsrgstPk="WRONG",
        bjdongCd="99999",
    )
    conflict_one = land_row(
        mgmHoDetlPk="UNIT-1",
        mgmHoExposPubuseAreaPk="AREA-X",
        exposPubuseGbCd="1",
        area="12",
    )
    conflict_two = dict(conflict_one, area="99")
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [land_row(mgmPmsrgstPk="CASE-1"), wrong_land],
            PERMIT_HOUSEHOLD_ENDPOINT: [
                land_row(mgmPmsrgstPk="CASE-1", mgmHoDetlPk="UNIT-1", hoNm="1호"),
                land_row(mgmPmsrgstPk="MISSING", mgmHoDetlPk="UNIT-X", hoNm="X호"),
            ],
            PERMIT_HOUSEHOLD_AREA_ENDPOINT: [
                conflict_one,
                conflict_two,
                land_row(
                    mgmHoDetlPk="ORPHAN",
                    mgmHoExposPubuseAreaPk="ORPHAN-A",
                    exposPubuseGbCd="1",
                    area="500",
                ),
            ],
        }
    )

    result = lookup_permit_households(client, LAND)

    assert result.unlinked_unit_count == 1
    assert result.orphan_area_count == 1
    assert result.cases[0].units[0].exclusive_area is None
    assert result.cases[0].units[0].area_components == ()
    assert any("서로 다른 값으로 중복" in warning for warning in result.warnings)
    assert next(
        stat for stat in result.endpoint_stats if stat.endpoint == PERMIT_BASIS_ENDPOINT
    ).rejected_count == 1


def test_ambiguous_or_unscoped_area_rows_are_excluded_with_warnings() -> None:
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [land_row(mgmPmsrgstPk="CASE-1")],
            PERMIT_HOUSEHOLD_ENDPOINT: [
                land_row(mgmPmsrgstPk="CASE-1", mgmHoDetlPk="UNIT-1")
            ],
            PERMIT_HOUSEHOLD_AREA_ENDPOINT: [
                land_row(
                    mgmHoDetlPk="UNIT-1",
                    mgmHoExposPubuseAreaPk="VALID",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    area="12",
                ),
                land_row(
                    mgmHoDetlPk="UNIT-1",
                    mgmHoExposPubuseAreaPk="CATEGORY-CONFLICT",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="공용",
                    area="100",
                ),
                land_row(
                    mgmHoDetlPk="UNIT-1",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    area="200",
                ),
                land_row(
                    mgmPmsrgstPk="OTHER-CASE",
                    mgmHoDetlPk="UNIT-1",
                    mgmHoExposPubuseAreaPk="WRONG-CASE",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    area="300",
                ),
            ],
        }
    )

    result = lookup_permit_households(client, LAND)

    unit = result.cases[0].units[0]
    assert unit.exclusive_area == Decimal("12")
    assert [component.area_pk for component in unit.area_components] == ["VALID"]
    assert any("전유·공용 코드와 명칭이 충돌" in item for item in result.warnings)
    assert any("면적 PK가 없는 1개 행" in item for item in result.warnings)
    assert any("인허가 이력 PK가 일치하지 않는 면적 1개 행" in item for item in result.warnings)


def test_deleted_or_ambiguous_change_units_are_excluded() -> None:
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [land_row(mgmPmsrgstPk="CASE-1")],
            PERMIT_HOUSEHOLD_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="KEEP",
                    changGbCd="1",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="NO-CODE",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="DELETED",
                    changGbCd="4",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="MIXED",
                    changGbCd="1",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="MIXED",
                    changGbCd="2",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="PARTIAL",
                    changGbCd="1",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoDetlPk="PARTIAL",
                    changGbCd=None,
                ),
            ],
        }
    )

    result = lookup_permit_households(client, LAND)

    assert {unit.unit_pk for unit in result.cases[0].units} == {"KEEP", "NO-CODE"}
    assert any("코드 4(삭제)" in item for item in result.warnings)
    assert sum("혼합되거나 누락" in item for item in result.warnings) == 2


def test_completeness_uses_only_documented_family_count() -> None:
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    fmlyCnt="3",
                    hhldCnt="9",
                    hoCnt="11",
                )
            ]
        }
    )

    result = lookup_permit_households(client, LAND)

    case = result.cases[0]
    assert case.expected_family_count == 3
    assert case.expected_household_count is None


def test_undocumented_field_aliases_are_not_used() -> None:
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [
                land_row(mgmPmsrgstPk="CASE-1", pmsDay="20200101")
            ],
            PERMIT_DONG_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    dongNm="별칭 동",
                )
            ],
            PERMIT_HOUSEHOLD_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    mgmHoDetlPk="UNIT-1",
                    dongNm="별칭 호 동",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmHoOulnPk="ALIAS-ONLY-UNIT",
                ),
            ],
            PERMIT_HOUSEHOLD_AREA_ENDPOINT: [
                land_row(
                    mgmHoDetlPk="UNIT-1",
                    mgmHoExposPubuseAreaPk="AREA-1",
                    exposPubuseGbCd="1",
                    area="10",
                ),
                land_row(
                    mgmHoOulnPk="ALIAS-ONLY-UNIT",
                    mgmHoExposPubuseAreaPk="ALIAS-AREA",
                    exposPubuseGbCd="1",
                    area="999",
                ),
            ],
        }
    )

    result = lookup_permit_households(client, LAND)

    case = result.cases[0]
    assert case.permit_date is None
    assert len(case.units) == 1
    assert case.units[0].unit_pk == "UNIT-1"
    assert case.units[0].dong_name is None
    assert case.units[0].exclusive_area == Decimal("10")
    assert result.orphan_area_count == 1
    assert any("호별개요 관리 PK가 없는 행" in item for item in result.warnings)


def test_empty_success_response_stays_empty_not_zero() -> None:
    result = lookup_permit_households(MockClient({}), LAND)

    assert result.has_units is False
    assert result.cases == ()
    assert result.source_as_of is None


def test_case_level_precision_fallback_preserves_unassigned_area_and_floor() -> None:
    client = MockClient(
        {
            PERMIT_BASIS_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    bldNm="다가구 테스트",
                    useAprDay="20231204",
                    fmlyCnt="6",
                    crtnDay="20231205",
                )
            ],
            PERMIT_DONG_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    bldNm="주건축물",
                )
            ],
            PERMIT_GENERAL_AREA_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmExposPubuseAreaPk="GENERAL-1",
                    pngtypGbNm="201호",
                    flrGbCdNm="지상",
                    flrNo="2",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    etcPurps="다가구주택",
                    area="31.25",
                    crtnDay="20231204",
                ),
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmExposPubuseAreaPk="GENERAL-2",
                    pngtypGbNm="201호",
                    flrGbCdNm="지상",
                    flrNo="2",
                    exposPubuseGbCd="2",
                    exposPubuseGbCdNm="공용",
                    area="4.5",
                ),
            ],
            PERMIT_FLOOR_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    mgmFlrOulnPk="FLOOR-2",
                    bldNm="주건축물",
                    flrGbCdNm="지상",
                    flrNo="2",
                    mainPurpsCdNm="단독주택",
                    strctCdNm="철근콘크리트구조",
                    flrArea="98.5",
                )
            ],
            PERMIT_PARCEL_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    mgmDongOulnPk="DONG-1",
                    mgmPlatPlcPk="PARCEL-1",
                    platPlc="수원시 영화동 396-30",
                    reprYn="Y",
                    relJibunNm="영화동 396-31",
                    mainDongGbCdNm="주동",
                )
            ],
            PERMIT_HOUSING_TYPE_ENDPOINT: [
                land_row(
                    mgmPmsrgstPk="CASE-1",
                    hstpGbCd="1",
                    hstpGbCdNm="준주택(고시원)",
                    silHoHhldCnt="3",
                    silHoHhldArea="22.5",
                )
            ],
        }
    )

    result = lookup_permit_households(
        client,
        LAND,
        register_approval_dates=("20231204",),
    )

    case = result.cases[0]
    assert case.matches_register_approval_date is True
    assert case.units == ()
    assert [item.area_pk for item in case.unassigned_areas] == [
        "GENERAL-1",
        "GENERAL-2",
    ]
    assert case.unassigned_areas[0].area == Decimal("31.25")
    assert case.unassigned_areas[0].floor_name == "2층"
    assert case.permit_floors[0].area == Decimal("98.5")
    assert case.parcels[0].related_lot_name == "영화동 396-31"
    assert case.housing_type_details[0].unit_count == 3
    assert case.housing_type_details[0].unit_area == Decimal("22.5")


def test_unassigned_area_without_pk_is_not_presented_as_a_household_area() -> None:
    result = lookup_permit_households(
        MockClient(
            {
                PERMIT_BASIS_ENDPOINT: [land_row(mgmPmsrgstPk="CASE-1")],
                PERMIT_GENERAL_AREA_ENDPOINT: [
                    land_row(
                        mgmPmsrgstPk="CASE-1",
                        pngtypGbNm="301호",
                        exposPubuseGbCd="1",
                        area="99",
                    )
                ],
            }
        ),
        LAND,
    )

    assert result.cases[0].unassigned_areas == ()
    assert any("인허가 전유공용면적 PK가 없는" in item for item in result.warnings)


def test_metadata_only_area_duplicates_keep_the_latest_collection_row() -> None:
    common = {
        "mgmPmsrgstPk": "CASE-1",
        "mgmExposPubuseAreaPk": "GENERAL-1",
        "pngtypGbNm": "201호",
        "flrNo": "2",
        "exposPubuseGbCd": "1",
        "area": "31.25",
    }
    result = lookup_permit_households(
        MockClient(
            {
                PERMIT_BASIS_ENDPOINT: [land_row(mgmPmsrgstPk="CASE-1")],
                PERMIT_GENERAL_AREA_ENDPOINT: [
                    land_row(**common, rnum="1", crtnDay="20231204"),
                    land_row(**common, rnum="2", crtnDay="20240105"),
                ],
            }
        ),
        LAND,
    )

    assert len(result.cases[0].unassigned_areas) == 1
    assert result.cases[0].unassigned_areas[0].source_as_of == "20240105"
    assert not any("서로 다른 값으로 중복" in item for item in result.warnings)
