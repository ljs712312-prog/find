from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.address import LandKey
from src.lookup import (
    AREA_ENDPOINT,
    BASIS_ENDPOINT,
    COLLECTIVE_UNIT_SOURCE_LABEL,
    EXPLICIT_API_UNIT_SOURCE_LABEL,
    EXPOSURE_ENDPOINT,
    FLOOR_ENDPOINT,
    LOOKUP_ENDPOINTS,
    RECAP_ENDPOINT,
    TITLE_ENDPOINT,
    AreaCategory,
    LookupDataError,
    ViolationStatus,
    lookup_buildings,
    lookup_register,
)


LAND_KEY = LandKey(
    sigungu_cd="41117",
    bjdong_cd="10700",
    plat_gb_cd="0",
    bun="0006",
    ji="0011",
)


def land_row(**values: Any) -> dict[str, Any]:
    row: dict[str, Any] = LAND_KEY.as_api_params()
    row.update(values)
    return row


class MockClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, LandKey, int, dict[str, Any]]] = []

    def fetch_all(
        self,
        endpoint: str,
        land_key: LandKey,
        num_of_rows: int = 100,
        **query: Any,
    ) -> Any:
        self.calls.append((endpoint, land_key, num_of_rows, query))
        return self.responses.get(endpoint, [])


def test_fetches_all_sections_and_rejects_non_exact_land_rows() -> None:
    exact_title = land_row(
        mgmBldrgstPk="TITLE-1",
        regstrGbCd="1",
        regstrGbCdNm="일반",
        bldNm="정확한 건물",
    )
    wrong_mountain = dict(exact_title, mgmBldrgstPk="WRONG-1", platGbCd="1")
    missing_ji = dict(exact_title, mgmBldrgstPk="WRONG-2")
    missing_ji.pop("ji")
    client = MockClient(
        {
            TITLE_ENDPOINT: [exact_title, exact_title.copy(), wrong_mountain, missing_ji],
            RECAP_ENDPOINT: [land_row(mgmBldrgstPk="RECAP-1", totArea="0")],
        }
    )

    result = lookup_buildings(client, LAND_KEY, num_of_rows=37)

    assert [call[0] for call in client.calls] == list(LOOKUP_ENDPOINTS)
    assert all(call[1] is LAND_KEY and call[2] == 37 and not call[3] for call in client.calls)
    assert len(result.titles) == 1
    assert result.titles[0].building_name == "정확한 건물"
    assert result.recaps[0].total_area == Decimal("0")
    title_stats = next(item for item in result.endpoint_stats if item.endpoint == TITLE_ENDPOINT)
    assert title_stats.received_count == 4
    assert title_stats.matched_count == 2
    assert title_stats.unique_count == 1
    assert title_stats.rejected_count == 2
    assert title_stats.duplicate_count == 1
    assert any("정확히 일치하지 않는 2개" in warning for warning in result.warnings)


def test_collective_unit_uses_pk_graph_and_exact_area_join() -> None:
    duplicate_exclusive = land_row(
        mgmBldrgstPk="UNIT-101",
        exposPubuseGbCd="1",
        exposPubuseGbCdNm="전유",
        mainPurpsCd="02001",
        mainPurpsCdNm="다세대주택",
        etcPurps="주거",
        area="45.25",
    )
    client = MockClient(
        {
            BASIS_ENDPOINT: [
                land_row(mgmBldrgstPk="UNIT-101", mgmUpBldrgstPk="MID-1"),
                land_row(mgmBldrgstPk="MID-1", mgmUpBldrgstPk="TITLE-1"),
            ],
            TITLE_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="TITLE-1",
                    regstrGbCd="2",
                    regstrGbCdNm="집합",
                    regstrKindCdNm="표제부",
                    bldNm="원탑빌라",
                    dongNm="A동",
                    mainPurpsCdNm="다세대주택",
                    hhldCnt="8",
                    totArea="500.00",
                )
            ],
            FLOOR_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="TITLE-1",
                    flrGbCd="10",
                    flrGbCdNm="지상",
                    flrNo="1",
                    flrNoNm="1층",
                    mainPurpsCdNm="다세대주택",
                    area="120.5",
                )
            ],
            EXPOSURE_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="UNIT-101",
                    dongNm="A동",
                    hoNm="101호",
                    flrGbCdNm="지상",
                    flrNo="1",
                    flrNoNm="1층",
                )
            ],
            AREA_ENDPOINT: [
                duplicate_exclusive,
                duplicate_exclusive.copy(),  # exact API duplicate, counted once
                land_row(
                    mgmBldrgstPk="UNIT-101",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    mainPurpsCd="02001",
                    mainPurpsCdNm="다세대주택",
                    etcPurps="발코니",
                    area="4.75",
                ),
                land_row(
                    mgmBldrgstPk="UNIT-101",
                    exposPubuseGbCd="2",
                    exposPubuseGbCdNm="공용",
                    mainPurpsCdNm="계단실",
                    area="0",
                ),
                land_row(
                    mgmBldrgstPk="ORPHAN-AREA",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    area="999",
                ),
            ],
        }
    )

    result = lookup_buildings(client, LAND_KEY)

    title = result.titles[0]
    assert title.is_collective is True
    assert title.total_area == Decimal("500.00")
    assert len(title.floors) == 1
    assert title.floors[0].area == Decimal("120.5")
    assert len(title.units) == 1
    unit = title.units[0]
    assert unit.title_pk == "TITLE-1"
    assert unit.source_label == COLLECTIVE_UNIT_SOURCE_LABEL
    assert unit.dong_name == "A동"
    assert unit.ho_name == "101호"
    assert unit.exclusive_area == Decimal("50.00")
    assert unit.common_area == Decimal("0")  # explicit zero is not missing
    assert unit.other_area is None
    assert len(unit.area_components) == 3
    exclusive_components = [
        item for item in unit.area_components if item.category is AreaCategory.EXCLUSIVE
    ]
    assert {item.other_purpose for item in exclusive_components} == {"주거", "발코니"}
    assert sum((item.area or Decimal("0")) for item in exclusive_components) == Decimal("50.00")
    assert unit.purposes == ("주거", "발코니")
    assert any("전유부 관리 PK가 없는 전유공용면적 1개" in warning for warning in result.warnings)


def test_general_multifamily_units_are_only_explicit_api_rows() -> None:
    client = MockClient(
        {
            BASIS_ENDPOINT: [land_row(mgmBldrgstPk="HOUSE-201", mgmUpBldrgstPk="TITLE-2")],
            TITLE_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="TITLE-2",
                    regstrGbCd="1",
                    regstrGbCdNm="일반",
                    mainPurpsCdNm="단독주택",
                    etcPurps="다가구주택(5가구)",
                    fmlyCnt="5",
                    useAprDay="20180102",
                )
            ],
            EXPOSURE_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="HOUSE-201",
                    dongNm="주건축물",
                    hoNm="201호",
                    flrNoNm="2층",
                )
            ],
            # An explicit row with no numeric area remains None, not zero.
            AREA_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="HOUSE-201",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    mainPurpsCdNm="다가구주택",
                    area="",
                )
            ],
        }
    )

    result = lookup_buildings(client, LAND_KEY)

    title = result.titles[0]
    assert title.is_collective is False
    assert title.is_multi_family_house is True
    assert title.family_count == 5
    # The count of five never creates inferred household records.
    assert len(title.units) == 1
    assert title.unit_information_note == EXPLICIT_API_UNIT_SOURCE_LABEL
    assert title.units[0].source_label == EXPLICIT_API_UNIT_SOURCE_LABEL
    assert title.units[0].ho_name == "201호"
    assert title.units[0].exclusive_area is None
    assert title.units[0].area_components[0].area is None
    assert result.violation_status is ViolationStatus.UNKNOWN
    assert "별도 근거 확인" in result.violation.note


def test_ambiguous_parent_graph_does_not_guess_a_title() -> None:
    client = MockClient(
        {
            BASIS_ENDPOINT: [
                land_row(mgmBldrgstPk="UNIT-X", mgmUpBldrgstPk="TITLE-A"),
                land_row(mgmBldrgstPk="UNIT-X", mgmUpBldrgstPk="TITLE-B"),
            ],
            TITLE_ENDPOINT: [
                land_row(mgmBldrgstPk="TITLE-A", regstrGbCdNm="집합"),
                land_row(mgmBldrgstPk="TITLE-B", regstrGbCdNm="집합"),
            ],
            EXPOSURE_ENDPOINT: [land_row(mgmBldrgstPk="UNIT-X", hoNm="301호")],
        }
    )

    result = lookup_buildings(client, LAND_KEY)

    assert all(not title.units for title in result.titles)
    assert len(result.unlinked_units) == 1
    assert result.unlinked_units[0].title_pk is None
    assert any("추정 연결하지 않았습니다" in warning for warning in result.warnings)


def test_rejects_non_list_client_result_and_invalid_page_size() -> None:
    client = MockClient({BASIS_ENDPOINT: {"not": "a list"}})

    with pytest.raises(LookupDataError):
        lookup_buildings(client, LAND_KEY)
    with pytest.raises(ValueError):
        lookup_buildings(MockClient({}), LAND_KEY, num_of_rows=0)
    with pytest.raises(ValueError):
        lookup_buildings(MockClient({}), LAND_KEY, num_of_rows=101)
    with pytest.raises(ValueError):
        lookup_buildings(MockClient({}), LAND_KEY, num_of_rows=True)
    with pytest.raises(ValueError):
        lookup_buildings(MockClient({}), LAND_KEY, num_of_rows="100")  # type: ignore[arg-type]


def test_app_facing_snapshot_surface_accepts_parsed_like_value() -> None:
    class ParsedLike:
        land_key = LAND_KEY

    client = MockClient(
        {
            TITLE_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="TITLE-UI",
                    regstrGbCdNm="집합",
                    bldNm="UI 건물",
                    crtnDay="20260801",
                )
            ],
            BASIS_ENDPOINT: [land_row(mgmBldrgstPk="UNIT-UI", mgmUpBldrgstPk="TITLE-UI")],
            EXPOSURE_ENDPOINT: [land_row(mgmBldrgstPk="UNIT-UI", hoNm="101호")],
            AREA_ENDPOINT: [
                land_row(
                    mgmBldrgstPk="UNIT-UI",
                    exposPubuseGbCd="1",
                    exposPubuseGbCdNm="전유",
                    mainPurpsCdNm="공동주택",
                    etcPurps="주거",
                    area="12.5",
                    crtnDay="20260731",
                )
            ],
        }
    )

    snapshot = lookup_register(client, ParsedLike())

    assert snapshot.buildings is snapshot.titles
    building = snapshot.buildings[0]
    assert building.title["bldNm"] == "UI 건물"
    assert building.register_group == "집합"
    assert building.units[0].dong_name is None
    assert building.units[0].ho_name == "101호"
    assert building.units[0].floor_name is None
    assert building.units[0].exclusive_area == Decimal("12.5")
    assert building.units[0].common_area is None
    assert building.units[0].purposes == ("주거",)
    assert snapshot.source_as_of == "20260801"

    with pytest.raises(TypeError):
        lookup_register(MockClient({}), object())
