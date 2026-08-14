from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.address import LandKey
from src.permit_lookup import (
    PERMIT_BASIS_ENDPOINT,
    PERMIT_DONG_ENDPOINT,
    PERMIT_HOUSEHOLD_AREA_ENDPOINT,
    PERMIT_HOUSEHOLD_ENDPOINT,
    PERMIT_HOUSING_TYPE_ENDPOINT,
    PERMIT_LOOKUP_ENDPOINTS,
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


def test_empty_success_response_stays_empty_not_zero() -> None:
    result = lookup_permit_households(MockClient({}), LAND)

    assert result.has_units is False
    assert result.cases == ()
    assert result.source_as_of is None
