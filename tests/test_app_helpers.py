from decimal import Decimal

from app import _date, _decimal_text, _friendly_api_error, _sum_int_fields
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
