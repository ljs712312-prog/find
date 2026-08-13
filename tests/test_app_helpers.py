from decimal import Decimal
from types import SimpleNamespace

from app import (
    _date,
    _decimal_text,
    _friendly_api_error,
    _metric_cards,
    _sum_int_fields,
    _unit_floor_label,
    _unit_total,
)
from src.building_hub import BuildingHubAPIError, BuildingHubAuthError


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
