from decimal import Decimal
from types import SimpleNamespace

from app import (
    _date,
    _decimal_text,
    _friendly_api_error,
    _metric_cards,
    _portal_status_text,
    _sum_int_fields,
    _unit_floor_label,
    _unit_total,
    _violation_lookup_identity,
)
from src.address import parse_address
from src.building_hub import BuildingHubAPIError, BuildingHubAuthError
from src.gyeonggi_portal import PortalBuildingReference, PortalBuildingState


def test_date_formats_only_known_precisions() -> None:
    assert _date("20260813") == "2026.08.13"
    assert _date("202608") == "2026.08"
    assert _date("2026") == "2026"
    assert _date("") == "-"


def test_decimal_keeps_explicit_zero_and_missing_distinct() -> None:
    assert _decimal_text(Decimal("0")) == "0 ㎡"
    assert _decimal_text(Decimal("12.3400")) == "12.34 ㎡"
    assert _decimal_text(None) == "-"


def test_parking_sum_is_unknown_if_all_fields_missing() -> None:
    assert _sum_int_fields({}, ("a", "b")) is None
    assert _sum_int_fields({"a": "0", "b": "2"}, ("a", "b")) == 2


def test_api_errors_are_user_friendly_without_raw_key_message() -> None:
    auth = BuildingHubAuthError("30", "secret key", retryable=False)
    generic = BuildingHubAPIError("10", "secret key", retryable=False)
    assert "secret" not in _friendly_api_error(auth)
    assert "secret" not in _friendly_api_error(generic)
    assert "동기화" in _friendly_api_error(generic)


def test_unit_total_does_not_treat_missing_common_area_as_zero() -> None:
    assert _unit_total(SimpleNamespace(exclusive_area=Decimal("42.17"), common_area=None)) is None
    assert _unit_total(SimpleNamespace(exclusive_area=Decimal("42.17"), common_area=Decimal("0"))) == Decimal("42.17")


def test_unit_floor_falls_back_to_explicit_floor_number() -> None:
    unit = SimpleNamespace(
        exposures=(SimpleNamespace(floor_name=None, floor_number=3),)
    )
    assert _unit_floor_label(unit) == "3층"


def test_metric_cards_split_long_floor_and_household_values() -> None:
    building = SimpleNamespace(
        title={
            "indrAutoUtcnt": "2",
            "oudrAutoUtcnt": "1",
            "rideUseElvtCnt": "1",
        },
        ground_floor_count=4,
        underground_floor_count=1,
        household_count=0,
        family_count=8,
    )

    assert _metric_cards(building) == (
        ("층수", "지상 4층", "지하 1층"),
        ("세대 · 가구", "0세대", "8가구"),
        ("주차", "3대", None),
        ("승강기", "1대", None),
    )


def test_violation_lookup_identity_changes_with_lot() -> None:
    first = parse_address("망포동 6-11")
    second = parse_address("망포동 6-12")

    assert _violation_lookup_identity(first) != _violation_lookup_identity(second)


def test_portal_status_text_is_short_and_explicit() -> None:
    missing = PortalBuildingReference(
        state=PortalBuildingState.NOT_LISTED,
        building_count=0,
        building_names=(),
        source_url="https://example.com/missing",
    )
    visible = PortalBuildingReference(
        state=PortalBuildingState.VISIBLE,
        building_count=1,
        building_names=("건축물",),
        source_url="https://example.com/visible",
    )

    assert _portal_status_text(missing) == (
        "warning",
        "경기부동산포털상 해당 사항 없음 — 위반건축물 의심 · 참고용(확정 아님)",
    )
    assert _portal_status_text(visible) == (
        "success",
        "경기부동산포털상 결과 확인 — 위반건축물 아님 · 참고용(법적 판정 아님)",
    )
