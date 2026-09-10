"""Resolve an exact Seoul road/building number to verified parcel keys."""
from dataclasses import dataclass
from html.parser import HTMLParser
import re

from src.address import (
    AddressParseError, LandKey, ParsedAddress, SEOUL_DISTRICTS,
    SEOUL_LEGAL_DONG_CODES, normalize_address,
)
from src.seoul_candidates import SeoulCandidateClient


_ROAD = re.compile(
    r"^(?:(?P<prefix>.+?)\s+)?(?P<road>[가-힣A-Za-z0-9·.]+(?:대로|로|길))"
    r"\s*(?P<underground>지하\s*)?(?P<main>[0-9]{1,5})"
    r"(?:\s*-\s*(?P<sub>[0-9]{1,5}))?$"
)
_DONG_BY_CODE = {code: (district, dong) for (district, dong), code in SEOUL_LEGAL_DONG_CODES.items()}


@dataclass(frozen=True, slots=True)
class RoadAddress:
    road: str
    main: int
    sub: int = 0
    district: str | None = None
    underground: bool = False

    @property
    def query(self) -> str:
        number = f"{self.main}" + (f"-{self.sub}" if self.sub else "")
        return " ".join(part for part in (
            self.district, self.road, "지하" if self.underground else None, number,
        ) if part)


def parse_road_address(value: str) -> RoadAddress | None:
    """Accept only a road + building number, optional Seoul/gu and parentheses.

    None means this is not road input. Never silently discard another city,
    district, building subnumber, underground flag, or trailing unit number.
    """
    normalized = normalize_address(value)
    # Parenthetical dong/building names in copied road addresses are descriptive.
    normalized = re.sub(r"\s*\([^()]*\)$", "", normalized).strip()
    match = _ROAD.fullmatch(normalized)
    if match is None:
        if re.search(r"[가-힣](?:대로|로|길)(?:\s|[0-9]|$)", normalized):
            raise AddressParseError("도로명과 건물번호를 입력해 주세요. 예: 은천로5길 26, 테헤란로 152. 동·호수는 제외해 주세요.")
        return None
    prefix = (match["prefix"] or "").split()
    if prefix and prefix[0] in {"서울", "서울시", "서울특별시"}:
        prefix.pop(0)
    if prefix and (len(prefix) != 1 or prefix[0] not in SEOUL_DISTRICTS.values()):
        raise AddressParseError("서울특별시 도로명 주소만 조회합니다. 자치구·도로명·건물번호를 확인해 주세요.")
    main, sub = int(match["main"]), int(match["sub"] or "0")
    if main == 0:
        raise AddressParseError("도로명 건물번호는 1 이상이어야 합니다.")
    return RoadAddress(match["road"], main, sub, prefix[0] if prefix else None, bool(match["underground"]))


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain(value) -> str:
    parser = _PlainText()
    parser.feed(str(value or ""))
    return " ".join("".join(parser.parts).split())


def _record_road(value) -> str:
    text = re.sub(r"\s*\([^()]*\)$", "", _plain(value)).strip()
    # The index includes unit documents, e.g. "152 41층[4117호]". Remove
    # only an explicit unit suffix from source records, never a building number.
    return re.sub(
        r"\s+(?:지하\s*)?[0-9A-Za-z-]+(?:동|층|호)(?:\[[0-9A-Za-z호-]+\])?"
        r"(?:\s+[0-9A-Za-z-]+(?:동|층|호))*$", "", text,
    ).strip()


@dataclass(frozen=True, slots=True)
class RoadCandidate:
    parsed: ParsedAddress
    road_address: str
    building_name: str = ""


@dataclass(frozen=True, slots=True)
class RoadSearchResult:
    address: RoadAddress
    matches: tuple[RoadCandidate, ...]
    complete: bool
    note: str | None = None


class SeoulRoadClient:
    def __init__(self, *, keyword_client=None):
        self.keyword_client = keyword_client or SeoulCandidateClient()

    def find(self, address: RoadAddress) -> RoadSearchResult:
        result = self.keyword_client.search_rows(address.query)
        selected = {}
        invalid = False
        for row in result.rows:
            road_text = _record_road(row.get("ADDR_ROAD"))
            if not road_text:
                continue
            try:
                actual = parse_road_address(road_text)
            except AddressParseError:
                invalid = True
                continue
            if actual is None:
                invalid = True
                continue
            if (actual.road, actual.main, actual.sub, actual.underground) != (
                address.road, address.main, address.sub, address.underground,
            ) or (address.district and address.district != actual.district):
                continue
            pnu = str(row.get("PNU") or "")
            location = _DONG_BY_CODE.get(pnu[:10])
            if (not re.fullmatch(r"[0-9]{19}", pnu) or not location
                    or pnu[10] not in {"1", "2"} or int(pnu[11:15]) == 0
                    or actual.district != location[0]):
                invalid = True
                continue
            key = LandKey(pnu[:5], pnu[5:10], "1" if pnu[10] == "2" else "0", pnu[11:15], pnu[15:19])
            parsed = ParsedAddress(address.query, road_text, *location, key)
            selected.setdefault(key, RoadCandidate(parsed, road_text, _plain(row.get("DANJI_NAME"))))
        note = result.note
        if invalid:
            note = "도로명과 지번의 연결을 확인할 수 없는 후보가 있어 일부 주소가 빠졌을 수 있습니다."
        return RoadSearchResult(address, tuple(sorted(selected.values(), key=lambda c: (
            c.parsed.district, c.parsed.legal_dong, c.parsed.land_key.bun, c.parsed.land_key.ji,
        ))), result.complete and not invalid, note)
