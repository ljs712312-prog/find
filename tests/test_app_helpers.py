from decimal import Decimal
from types import SimpleNamespace

import app as app_module

from app import (
    _date,
    _decimal_text,
    _friendly_api_error,
    _friendly_permit_error,
    _metric_cards,
    _permit_unit_table,
    _portal_status_text,
    _relay_fingerprint,
    _sum_int_fields,
    _unit_floor_label,
    _unit_total,
    _violation_lookup_identity,
)
from src.address import parse_address
from src.building_hub import (
    BuildingHubAPIError,
    BuildingHubAuthError,
    BuildingHubNetworkError,
    BuildingHubValidationError,
)
from src.gyeonggi_portal import PortalBuildingReference, PortalBuildingState
from src.permit_lookup import PermitUnitReference


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


def test_network_error_explains_delay_without_raw_request_data() -> None:
    error = BuildingHubNetworkError(
        endpoint="getBrTitleInfo",
        attempts=4,
        reason="read_timeout",
    )

    message = _friendly_api_error(error)

    assert "표제부" in message
    assert "응답하지 않았습니다" in message
    assert "getBrTitleInfo" not in message


def test_relay_configuration_error_and_cache_identity_are_safe() -> None:
    secret = "relay-secret-which-is-longer-than-thirty-two-characters"
    direct = _relay_fingerprint(None, None)
    relay = _relay_fingerprint("https://relay.example.com", secret)

    assert direct != relay
    assert secret not in relay
    assert "중계 서버 설정" in _friendly_api_error(
        BuildingHubValidationError("relay pair is incomplete")
    )


def test_partial_snapshot_is_not_kept_in_the_long_lived_lookup_cache(
    monkeypatch: object,
) -> None:
    class CachedLookup:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []
            self.cleared: list[tuple[object, ...]] = []

        def __call__(self, *args: object) -> SimpleNamespace:
            self.calls.append(args)
            return SimpleNamespace(is_partial=True)

        def clear(self, *args: object) -> None:
            self.cleared.append(args)

    cached_lookup = CachedLookup()
    monkeypatch.setattr(app_module, "_lookup_api_cached", cached_lookup)  # type: ignore[attr-defined]

    outcome = app_module._search("망포동 6-11", "test-service-key")

    assert outcome.snapshot is not None
    assert cached_lookup.cleared == cached_lookup.calls


def test_permit_auth_error_is_separate_and_does_not_echo_secret() -> None:
    auth = BuildingHubAuthError("30", "permit secret key", retryable=False)
    message = _friendly_permit_error(auth)
    assert "secret" not in message
    assert "건축인허가정보" in message


def test_permit_unit_table_keeps_missing_common_area_distinct() -> None:
    unit = PermitUnitReference(
        case_pk="CASE-1",
        unit_pk="UNIT-1",
        dong_pk=None,
        dong_name="주건축물",
        ho_number="201",
        ho_name="201호",
        floor_group_name="지상",
        floor_number=2,
        change_name=None,
        exclusive_area=Decimal("31.25"),
        common_area=None,
        other_area=None,
        area_components=(),
    )
    table = _permit_unit_table(SimpleNamespace(units=(unit,)))
    assert table.to_dict("records") == [
        {
            "동": "주건축물",
            "층": "2층",
            "호(가구)": "201호",
            "전유면적(㎡)": "31.25",
            "공용면적(㎡)": "-",
            "전유+공용(㎡)": "-",
            "용도": "-",
            "변경구분": "-",
        }
    ]


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
