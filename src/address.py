"""Safe parsing of Suwon lot-number addresses for the BuildingHUB API.

The legal-dong codes below are the current, non-abolished Suwon entries from
the Korean Standard Code Management System (행정표준코드관리시스템).  A
BuildingHUB location key splits the ten-digit legal-dong code into the first
five digits (``sigunguCd``) and the last five digits (``bjdongCd``).
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Final


# Current Suwon legal-dong codes (법정동코드), grouped by district.
SUWON_LEGAL_DONG_CODES: Final[dict[str, str]] = {
    # 장안구 (41111)
    "파장동": "4111112900",
    "정자동": "4111113000",
    "이목동": "4111113100",
    "율전동": "4111113200",
    "천천동": "4111113300",
    "영화동": "4111113400",
    "송죽동": "4111113500",
    "조원동": "4111113600",
    "연무동": "4111113700",
    "상광교동": "4111113800",
    "하광교동": "4111113900",
    # 권선구 (41113)
    "세류동": "4111312600",
    "평동": "4111312700",
    "고색동": "4111312800",
    "오목천동": "4111312900",
    "평리동": "4111313000",
    "서둔동": "4111313100",
    "구운동": "4111313200",
    "탑동": "4111313300",
    "금곡동": "4111313400",
    "호매실동": "4111313500",
    "곡반정동": "4111313600",
    "권선동": "4111313700",
    "장지동": "4111313800",
    "대황교동": "4111313900",
    "입북동": "4111314000",
    "당수동": "4111314100",
    # 팔달구 (41115)
    "팔달로1가": "4111512000",
    "팔달로2가": "4111512100",
    "팔달로3가": "4111512200",
    "남창동": "4111512300",
    "영동": "4111512400",
    "중동": "4111512500",
    "구천동": "4111512600",
    "남수동": "4111512700",
    "매향동": "4111512800",
    "북수동": "4111512900",
    "신풍동": "4111513000",
    "장안동": "4111513100",
    "교동": "4111513200",
    "매교동": "4111513300",
    "매산로1가": "4111513400",
    "매산로2가": "4111513500",
    "매산로3가": "4111513600",
    "고등동": "4111513700",
    "화서동": "4111513800",
    "지동": "4111513900",
    "우만동": "4111514000",
    "인계동": "4111514100",
    # 영통구 (41117)
    "매탄동": "4111710100",
    "원천동": "4111710200",
    "이의동": "4111710300",
    "하동": "4111710400",
    "영통동": "4111710500",
    "신동": "4111710600",
    "망포동": "4111710700",
}

SUWON_DISTRICTS: Final[dict[str, str]] = {
    "41111": "장안구",
    "41113": "권선구",
    "41115": "팔달구",
    "41117": "영통구",
}

_DASH_TRANSLATION: Final[dict[int, str]] = str.maketrans(
    {
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
        "‒": "-",  # figure dash
        "–": "-",  # en dash
        "—": "-",  # em dash
        "⁃": "-",  # hyphen bullet
        "−": "-",  # minus sign
        "﹘": "-",  # small em dash
        "﹣": "-",  # small hyphen-minus
        "－": "-",  # full-width hyphen-minus
    }
)

_LOT_ADDRESS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<location>.+?)\s+"
    r"(?:(?P<mountain>산)\s*)?"
    r"(?P<bun>[0-9]{1,4})"
    r"(?:\s*-\s*(?P<ji>[0-9]{1,4}))?"
    r"\s*(?:번지)?$"
)


class AddressParseError(ValueError):
    """Raised when an input is not an unambiguous Suwon lot address."""


@dataclass(frozen=True, slots=True)
class LandKey:
    """Exact BuildingHUB land lookup key."""

    sigungu_cd: str
    bjdong_cd: str
    plat_gb_cd: str
    bun: str
    ji: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9]{5}", self.sigungu_cd) is None:
            raise ValueError("sigungu_cd must contain exactly five digits")
        if re.fullmatch(r"[0-9]{5}", self.bjdong_cd) is None:
            raise ValueError("bjdong_cd must contain exactly five digits")
        if self.plat_gb_cd not in {"0", "1", "2"}:
            raise ValueError("plat_gb_cd must be 0 (land), 1 (mountain), or 2 (block)")
        if re.fullmatch(r"[0-9]{4}", self.bun) is None:
            raise ValueError("bun must contain exactly four digits")
        if re.fullmatch(r"[0-9]{4}", self.ji) is None:
            raise ValueError("ji must contain exactly four digits")

    @property
    def legal_dong_code(self) -> str:
        """Return the combined ten-digit legal-dong code."""

        return f"{self.sigungu_cd}{self.bjdong_cd}"

    def as_api_params(self) -> dict[str, str]:
        """Return parameter names expected by the BuildingHUB API."""

        return {
            "sigunguCd": self.sigungu_cd,
            "bjdongCd": self.bjdong_cd,
            "platGbCd": self.plat_gb_cd,
            "bun": self.bun,
            "ji": self.ji,
        }


@dataclass(frozen=True, slots=True)
class ParsedAddress:
    """Normalized, resolved representation of a Suwon lot address."""

    raw: str
    normalized: str
    district: str
    legal_dong: str
    land_key: LandKey

    @property
    def is_mountain(self) -> bool:
        return self.land_key.plat_gb_cd == "1"

    @property
    def lot_number(self) -> str:
        main_number = str(int(self.land_key.bun))
        sub_number = int(self.land_key.ji)
        prefix = "산" if self.is_mountain else ""
        suffix = f"-{sub_number}" if sub_number else ""
        return f"{prefix}{main_number}{suffix}"

    @property
    def canonical_address(self) -> str:
        return (
            f"경기도 수원시 {self.district} "
            f"{self.legal_dong} {self.lot_number}번지"
        )


def normalize_address(value: str) -> str:
    """Apply NFKC, normalize dash characters, and collapse whitespace."""

    if not isinstance(value, str):
        raise AddressParseError("주소는 문자열로 입력해 주세요.")

    normalized = unicodedata.normalize("NFKC", value).translate(_DASH_TRANSLATION)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise AddressParseError("주소를 입력해 주세요.")
    if len(normalized) > 200:
        raise AddressParseError("주소가 너무 깁니다.")
    return normalized


def _resolve_legal_dong(location: str) -> tuple[str, str, str]:
    """Resolve an exact supported Suwon location to district and API codes."""

    legal_dong = location.rsplit(" ", 1)[-1]
    full_code = SUWON_LEGAL_DONG_CODES.get(legal_dong)
    if full_code is None:
        raise AddressParseError("수원시의 현행 법정동을 확인할 수 없습니다.")

    sigungu_cd = full_code[:5]
    bjdong_cd = full_code[5:]
    district = SUWON_DISTRICTS[sigungu_cd]
    accepted_locations = {
        legal_dong,
        f"{district} {legal_dong}",
        f"수원시 {legal_dong}",
        f"수원시 {district} {legal_dong}",
        f"경기도 수원시 {legal_dong}",
        f"경기도 수원시 {district} {legal_dong}",
    }
    if location not in accepted_locations:
        raise AddressParseError("수원시 법정동 주소 형식을 확인해 주세요.")

    return legal_dong, sigungu_cd, bjdong_cd


def parse_address(value: str) -> ParsedAddress:
    """Parse a Suwon lot address without guessing or regex-based searching.

    Accepted examples include ``망포동 6-11``, ``오목천동 산 1-5`` and
    ``경기도 수원시 영통구 망포동 6-11번지``.  A query containing only a
    number, an unknown/ambiguous location, or extra punctuation is rejected.
    """

    normalized = normalize_address(value)
    match = _LOT_ADDRESS_PATTERN.fullmatch(normalized)
    if match is None:
        raise AddressParseError("동명과 지번을 함께 입력해 주세요.")

    location = match.group("location").strip()
    legal_dong, sigungu_cd, bjdong_cd = _resolve_legal_dong(location)

    bun_number = int(match.group("bun"))
    ji_number = int(match.group("ji") or "0")
    if bun_number == 0:
        raise AddressParseError("지번 본번은 1 이상이어야 합니다.")

    land_key = LandKey(
        sigungu_cd=sigungu_cd,
        bjdong_cd=bjdong_cd,
        plat_gb_cd="1" if match.group("mountain") else "0",
        bun=f"{bun_number:04d}",
        ji=f"{ji_number:04d}",
    )
    return ParsedAddress(
        raw=value,
        normalized=normalized,
        district=SUWON_DISTRICTS[sigungu_cd],
        legal_dong=legal_dong,
        land_key=land_key,
    )


def parse_lot_address(value: str) -> ParsedAddress:
    """Explicit alias for :func:`parse_address`."""

    return parse_address(value)

