"""Reported room counts, kept separate from households and families.

The title's hoCnt is a register count, not a survey of actual internal rooms.
Text-derived counts are explicitly marked as reference values, never inferred
from floor area, household/family counts or the number of returned floor rows.
"""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class RoomCount:
    count: int | None
    source: str
    note: str


_COUNT = re.compile(r"(?:\(|총\s*|호실\s*수\s*[:：]?\s*)([1-9][0-9]*)\s*(?:호실|실|호)\s*(?:\)|$)")
_ROOM_USE = re.compile(r"오피스텔|다중주택|고시원|다중생활시설|기숙사|숙박시설|여관|여인숙")
_AUXILIARY = re.compile(r"^(?:주차장|계단실|기계실|전기실|통신실|승강기|물탱크실|화장실|장애인화장실|창고|복도|옥탑)(?:\([^)]*\))?$")


def _explicit_count(text):
    value = unicodedata.normalize("NFKC", text or "")
    # Only purpose descriptions count; a standalone room label (e.g. 201호)
    # or area/household count is not the number of rooms in a building.
    if not _ROOM_USE.search(value):
        return None
    found = _COUNT.findall(value)
    return int(found[0]) if len(found) == 1 else None


def total_rooms(building, *, allow_floor_reference=True):
    count = getattr(building, "unit_count", None)
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        return RoomCount(count, "대장 호수", "표제부의 호수 항목입니다. 실제 내부 방 수와 다를 수 있습니다.")
    title_count = _explicit_count(getattr(building, "other_purpose", None))
    if title_count is not None:
        return RoomCount(title_count, "상세용도 명시 · 참고", "건물 상세용도에 명시된 호·실 개수입니다.")
    floors = getattr(building, "floors", ())
    counts, seen = [], set()
    if allow_floor_reference and floors:
        for floor in floors:
            detail = unicodedata.normalize("NFKC", floor.other_purpose or "").strip()
            parts = [p.strip() for p in re.split(r"[,·/\s]+", detail) if p.strip()]
            if parts and all(_AUXILIARY.fullmatch(part) for part in parts):
                continue
            count = _explicit_count(detail)
            floor_key = (floor.dong_name, floor.floor_group_code, floor.floor_number, floor.floor_name)
            if count is None or floor_key in seen:
                break  # Partial or repeated counts must never be called a total.
            seen.add(floor_key)
            counts.append(count)
        else:
            if counts:
                return RoomCount(sum(counts), "층별 명시 합계 · 참고", "층별 용도에 명시된 호·실 개수의 합계이며 현장 실측값은 아닙니다.")
    return RoomCount(None, "확인 불가", "대장 호수가 0이거나 미기재이고 전체 호실수를 확인할 자료가 없습니다. 세대·가구수나 면적으로 추정하지 않습니다.")
