import pytest

from src.address import (
    AddressParseError,
    SUWON_LEGAL_DONG_CODES,
    parse_address,
)


def test_complete_current_suwon_legal_dong_mapping() -> None:
    assert len(SUWON_LEGAL_DONG_CODES) == 56
    assert SUWON_LEGAL_DONG_CODES["파장동"] == "4111112900"
    assert SUWON_LEGAL_DONG_CODES["당수동"] == "4111314100"
    assert SUWON_LEGAL_DONG_CODES["매산로1가"] == "4111513400"
    assert SUWON_LEGAL_DONG_CODES["망포동"] == "4111710700"


def test_parses_standard_lot_address() -> None:
    parsed = parse_address("망포동 6-11")

    assert parsed.legal_dong == "망포동"
    assert parsed.district == "영통구"
    assert parsed.land_key.sigungu_cd == "41117"
    assert parsed.land_key.bjdong_cd == "10700"
    assert parsed.land_key.plat_gb_cd == "0"
    assert parsed.land_key.bun == "0006"
    assert parsed.land_key.ji == "0011"
    assert parsed.land_key.as_api_params() == {
        "sigunguCd": "41117",
        "bjdongCd": "10700",
        "platGbCd": "0",
        "bun": "0006",
        "ji": "0011",
    }


def test_numeric_legal_dong_name_is_not_misread_as_lot_number() -> None:
    parsed = parse_address("매산로1가 1-4")

    assert parsed.legal_dong == "매산로1가"
    assert parsed.land_key.sigungu_cd == "41115"
    assert parsed.land_key.bjdong_cd == "13400"
    assert parsed.land_key.bun == "0001"
    assert parsed.land_key.ji == "0004"


@pytest.mark.parametrize("query", ["오목천동 산1-5", "오목천동 산 1-5"])
def test_parses_mountain_lot_with_or_without_space(query: str) -> None:
    parsed = parse_address(query)

    assert parsed.legal_dong == "오목천동"
    assert parsed.land_key.sigungu_cd == "41113"
    assert parsed.land_key.bjdong_cd == "12900"
    assert parsed.land_key.plat_gb_cd == "1"
    assert parsed.land_key.bun == "0001"
    assert parsed.land_key.ji == "0005"
    assert parsed.lot_number == "산1-5"


def test_parses_full_official_address() -> None:
    parsed = parse_address("경기도 수원시 영통구 망포동 6-11번지")

    assert parsed.normalized == "경기도 수원시 영통구 망포동 6-11번지"
    assert parsed.canonical_address == "경기도 수원시 영통구 망포동 6-11번지"


@pytest.mark.parametrize(
    "query",
    [
        "망포동 6–11",  # en dash
        "망포동 6—11",  # em dash
        "망포동 ６－１１",  # NFKC full-width digits and hyphen
    ],
)
def test_normalizes_unicode_dashes_and_full_width_digits(query: str) -> None:
    parsed = parse_address(query)

    assert parsed.normalized == "망포동 6-11"
    assert parsed.land_key.bun == "0006"
    assert parsed.land_key.ji == "0011"


def test_missing_sublot_defaults_to_zero() -> None:
    parsed = parse_address("망포동 6")

    assert parsed.land_key.bun == "0006"
    assert parsed.land_key.ji == "0000"
    assert parsed.lot_number == "6"


@pytest.mark.parametrize("query", ["6", "6-11", "  ", "0000"])
def test_rejects_number_only_or_empty_input(query: str) -> None:
    with pytest.raises(AddressParseError):
        parse_address(query)


@pytest.mark.parametrize(
    "query",
    [
        "망포동[ 6-11",
        "망포동.* 6-11",
        "망포동 6-11[",
        "경기도 화성시 망포동 6-11",
        "권선구 망포동 6-11",
    ],
)
def test_rejects_regex_characters_and_mismatched_locations(query: str) -> None:
    with pytest.raises(AddressParseError):
        parse_address(query)
