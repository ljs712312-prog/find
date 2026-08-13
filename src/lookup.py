"""Join BuildingHUB register responses into immutable lookup results.

The public API exposes each register section through a separate operation.
This module deliberately joins those sections only by their management keys:

* every response row must exactly match the requested five-part land key;
* a unit (전유부) and its area rows are joined by ``mgmBldrgstPk``;
* a unit is attached to a title only when the ``mgmUpBldrgstPk`` graph in the
  basic-outline response reaches that title; and
* no household or unit row is inferred from counts, names, or floor areas.

Those rules are intentionally conservative.  A missing value therefore stays
``None`` and is not silently changed to zero or guessed from a nearby record.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Protocol, Sequence

from .address import LandKey

if TYPE_CHECKING:  # pragma: no cover - imported only for static type checkers
    from .building_hub import BuildingHubClient


BASIS_ENDPOINT = "getBrBasisOulnInfo"
TITLE_ENDPOINT = "getBrTitleInfo"
RECAP_ENDPOINT = "getBrRecapTitleInfo"
FLOOR_ENDPOINT = "getBrFlrOulnInfo"
EXPOSURE_ENDPOINT = "getBrExposInfo"
AREA_ENDPOINT = "getBrExposPubuseAreaInfo"

LOOKUP_ENDPOINTS = (
    BASIS_ENDPOINT,
    TITLE_ENDPOINT,
    RECAP_ENDPOINT,
    FLOOR_ENDPOINT,
    EXPOSURE_ENDPOINT,
    AREA_ENDPOINT,
)

COLLECTIVE_UNIT_SOURCE_LABEL = "집합건물 전유부"
EXPLICIT_API_UNIT_SOURCE_LABEL = "API 반환 호별 정보"


class _FetchAllClient(Protocol):
    def fetch_all(
        self,
        endpoint: str,
        land_key: LandKey,
        num_of_rows: int = 100,
        **query: Any,
    ) -> list[dict[str, Any]]: ...


class LookupDataError(ValueError):
    """Raised when a client violates the documented ``fetch_all`` contract."""


class ViolationStatus(str, Enum):
    """Violation status supported by this data source.

    BuildingHUB's building-register operations do not expose an authoritative
    violation flag, so this lookup layer must never turn absence into ``NO``.
    """

    UNKNOWN = "UNKNOWN"


class AreaCategory(str, Enum):
    EXCLUSIVE = "EXCLUSIVE"
    COMMON = "COMMON"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class EndpointStats:
    endpoint: str
    received_count: int
    matched_count: int
    unique_count: int
    rejected_count: int
    duplicate_count: int


@dataclass(frozen=True, slots=True)
class ViolationAssessment:
    status: ViolationStatus = ViolationStatus.UNKNOWN
    note: str = (
        "건축HUB 건축물대장정보 응답에는 위반건축물 여부가 없어 "
        "원본 건축물대장 등 별도 근거 확인이 필요합니다."
    )


@dataclass(frozen=True, slots=True)
class FloorSummary:
    register_pk: str
    dong_name: str | None
    floor_group_code: str | None
    floor_group_name: str | None
    floor_number: int | None
    floor_name: str | None
    structure_name: str | None
    purpose_code: str | None
    purpose_name: str | None
    other_purpose: str | None
    area: Decimal | None
    area_exception_yn: str | None


@dataclass(frozen=True, slots=True)
class UnitExposureSummary:
    dong_name: str | None
    ho_name: str | None
    floor_group_code: str | None
    floor_group_name: str | None
    floor_number: int | None
    floor_name: str | None


@dataclass(frozen=True, slots=True)
class UnitAreaComponent:
    category: AreaCategory
    exposure_use_code: str | None
    exposure_use_name: str | None
    purpose_code: str | None
    purpose_name: str | None
    other_purpose: str | None
    area: Decimal | None
    row_count: int


@dataclass(frozen=True, slots=True)
class UnitSummary:
    unit_pk: str
    title_pk: str | None
    source_label: str
    exposures: tuple[UnitExposureSummary, ...]
    exclusive_area: Decimal | None
    common_area: Decimal | None
    other_area: Decimal | None
    area_components: tuple[UnitAreaComponent, ...]

    @staticmethod
    def _single_text(values: Iterable[str | None]) -> str | None:
        distinct = tuple(dict.fromkeys(value for value in values if value))
        return distinct[0] if len(distinct) == 1 else None

    @property
    def dong_name(self) -> str | None:
        """Return a name only when all explicit exposure rows agree."""

        return self._single_text(item.dong_name for item in self.exposures)

    @property
    def ho_name(self) -> str | None:
        """Return a unit name only when all explicit exposure rows agree."""

        return self._single_text(item.ho_name for item in self.exposures)

    @property
    def floor_name(self) -> str | None:
        """Return a floor name only when all explicit exposure rows agree."""

        return self._single_text(item.floor_name for item in self.exposures)

    @property
    def purposes(self) -> tuple[str, ...]:
        """Return distinct, explicitly supplied purpose labels."""

        labels: list[str] = []
        for component in self.area_components:
            label = component.other_purpose or component.purpose_name
            if label and label not in labels:
                labels.append(label)
        return tuple(labels)


@dataclass(frozen=True, slots=True)
class TitleSummary:
    title_pk: str
    title: Mapping[str, Any]
    register_type_code: str | None
    register_type_name: str | None
    register_kind_code: str | None
    register_kind_name: str | None
    lot_address: str | None
    road_address: str | None
    building_name: str | None
    dong_name: str | None
    purpose_code: str | None
    purpose_name: str | None
    other_purpose: str | None
    structure_name: str | None
    roof_name: str | None
    site_area: Decimal | None
    building_area: Decimal | None
    total_area: Decimal | None
    floor_ratio_area: Decimal | None
    building_coverage_ratio: Decimal | None
    floor_area_ratio: Decimal | None
    household_count: int | None
    family_count: int | None
    unit_count: int | None
    ground_floor_count: int | None
    underground_floor_count: int | None
    permit_date: str | None
    construction_start_date: str | None
    approval_date: str | None
    is_collective: bool
    is_multi_family_house: bool
    source_row_count: int
    floors: tuple[FloorSummary, ...] = ()
    units: tuple[UnitSummary, ...] = ()

    @property
    def unit_information_note(self) -> str | None:
        """Describe explicit API unit data without implying completeness."""

        if not self.units:
            return None
        if self.is_collective:
            return COLLECTIVE_UNIT_SOURCE_LABEL
        return EXPLICIT_API_UNIT_SOURCE_LABEL

    @property
    def register_group(self) -> str:
        """Return the API register group without inferring a finer subtype."""

        if self.register_type_name:
            return self.register_type_name
        return "집합" if self.is_collective else "일반"


@dataclass(frozen=True, slots=True)
class RecapSummary:
    recap_pk: str | None
    lot_address: str | None
    road_address: str | None
    building_name: str | None
    purpose_name: str | None
    other_purpose: str | None
    site_area: Decimal | None
    building_area: Decimal | None
    total_area: Decimal | None
    household_count: int | None
    family_count: int | None
    unit_count: int | None


@dataclass(frozen=True, slots=True)
class LookupResult:
    land_key: LandKey
    titles: tuple[TitleSummary, ...]
    recaps: tuple[RecapSummary, ...]
    unlinked_floors: tuple[FloorSummary, ...]
    unlinked_units: tuple[UnitSummary, ...]
    violation: ViolationAssessment
    endpoint_stats: tuple[EndpointStats, ...]
    warnings: tuple[str, ...]
    source_as_of: str | None

    @property
    def violation_status(self) -> ViolationStatus:
        return self.violation.status

    @property
    def buildings(self) -> tuple[TitleSummary, ...]:
        """App-facing name for the joined title-level building results."""

        return self.titles


# Public app-facing name.  The alias keeps one canonical immutable result type.
RegisterSnapshot = LookupResult


def _text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        result = str(value).strip()
        if result:
            return result
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: Any) -> int | None:
    number = _decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def _consensus_text(rows: Sequence[Mapping[str, Any]], *keys: str) -> str | None:
    values = tuple(dict.fromkeys(value for row in rows if (value := _text(row, *keys))))
    return values[0] if len(values) == 1 else None


def _consensus_decimal(rows: Sequence[Mapping[str, Any]], key: str) -> Decimal | None:
    values = tuple(
        dict.fromkeys(value for row in rows if (value := _decimal(row.get(key))) is not None)
    )
    return values[0] if len(values) == 1 else None


def _consensus_integer(rows: Sequence[Mapping[str, Any]], key: str) -> int | None:
    values = tuple(
        dict.fromkeys(value for row in rows if (value := _integer(row.get(key))) is not None)
    )
    return values[0] if len(values) == 1 else None


def _freeze(value: Any) -> Any:
    """Create a type-preserving, hashable representation for exact deduping."""

    if isinstance(value, Mapping):
        return (
            "mapping",
            tuple(sorted((str(key), _freeze(item)) for key, item in value.items())),
        )
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_freeze(item) for item in value))
    if isinstance(value, set):
        return ("set", tuple(sorted((_freeze(item) for item in value), key=repr)))
    return (type(value).__qualname__, repr(value))


def _matches_land(row: Mapping[str, Any], land_key: LandKey) -> bool:
    expected = land_key.as_api_params()
    return all(
        key in row
        and row[key] is not None
        and str(row[key]).strip() == expected_value
        for key, expected_value in expected.items()
    )


def _validate_and_dedupe(
    endpoint: str,
    raw_rows: Any,
    land_key: LandKey,
) -> tuple[list[Mapping[str, Any]], EndpointStats]:
    if not isinstance(raw_rows, list):
        raise LookupDataError(f"{endpoint} fetch_all 결과는 list여야 합니다.")

    matched: list[Mapping[str, Any]] = []
    rejected_count = 0
    for row in raw_rows:
        if not isinstance(row, Mapping) or not _matches_land(row, land_key):
            rejected_count += 1
            continue
        matched.append(row)

    unique: list[Mapping[str, Any]] = []
    seen: set[Any] = set()
    for row in matched:
        marker = _freeze(row)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(row)

    stats = EndpointStats(
        endpoint=endpoint,
        received_count=len(raw_rows),
        matched_count=len(matched),
        unique_count=len(unique),
        rejected_count=rejected_count,
        duplicate_count=len(matched) - len(unique),
    )
    return unique, stats


def _classify_area(row: Mapping[str, Any]) -> AreaCategory:
    code = _text(row, "exposPubuseGbCd")
    name = _text(row, "exposPubuseGbCdNm") or ""
    name_exclusive = "전유" in name
    name_common = "공용" in name
    code_exclusive = code == "1"
    code_common = code == "2"

    exclusive = name_exclusive or (not name and code_exclusive)
    common = name_common or (not name and code_common)
    if exclusive and not common:
        # A supplied name and code must not contradict each other.
        if name and code_common:
            return AreaCategory.OTHER
        return AreaCategory.EXCLUSIVE
    if common and not exclusive:
        if name and code_exclusive:
            return AreaCategory.OTHER
        return AreaCategory.COMMON
    return AreaCategory.OTHER


def _sum_areas(rows: Iterable[Mapping[str, Any]]) -> Decimal | None:
    values = [area for row in rows if (area := _decimal(row.get("area"))) is not None]
    if not values:
        return None
    return sum(values, Decimal("0"))


def _area_components(rows: Sequence[Mapping[str, Any]]) -> tuple[UnitAreaComponent, ...]:
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        category = _classify_area(row)
        key = (
            category,
            _text(row, "exposPubuseGbCd"),
            _text(row, "exposPubuseGbCdNm"),
            _text(row, "mainPurpsCd"),
            _text(row, "mainPurpsCdNm"),
            _text(row, "etcPurps"),
        )
        grouped.setdefault(key, []).append(row)

    return tuple(
        UnitAreaComponent(
            category=key[0],
            exposure_use_code=key[1],
            exposure_use_name=key[2],
            purpose_code=key[3],
            purpose_name=key[4],
            other_purpose=key[5],
            area=_sum_areas(component_rows),
            row_count=len(component_rows),
        )
        for key, component_rows in grouped.items()
    )


def _make_floor(row: Mapping[str, Any]) -> FloorSummary:
    return FloorSummary(
        register_pk=_text(row, "mgmBldrgstPk") or "",
        dong_name=_text(row, "dongNm"),
        floor_group_code=_text(row, "flrGbCd"),
        floor_group_name=_text(row, "flrGbCdNm"),
        floor_number=_integer(row.get("flrNo")),
        floor_name=_text(row, "flrNoNm"),
        structure_name=_text(row, "strctCdNm"),
        purpose_code=_text(row, "mainPurpsCd"),
        purpose_name=_text(row, "mainPurpsCdNm"),
        other_purpose=_text(row, "etcPurps"),
        area=_decimal(row.get("area")),
        area_exception_yn=_text(row, "areaExctYn"),
    )


def _make_exposure(row: Mapping[str, Any]) -> UnitExposureSummary:
    return UnitExposureSummary(
        dong_name=_text(row, "dongNm"),
        ho_name=_text(row, "hoNm"),
        floor_group_code=_text(row, "flrGbCd"),
        floor_group_name=_text(row, "flrGbCdNm"),
        floor_number=_integer(row.get("flrNo")),
        floor_name=_text(row, "flrNoNm"),
    )


def _is_collective(rows: Sequence[Mapping[str, Any]]) -> bool:
    for row in rows:
        code = _text(row, "regstrGbCd")
        name = _text(row, "regstrGbCdNm") or ""
        if code == "2" or "집합" in name:
            return True
    return False


def _is_multi_family_house(rows: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        "다가구" in " ".join(
            filter(None, (_text(row, "mainPurpsCdNm"), _text(row, "etcPurps")))
        )
        for row in rows
    )


def _make_title(title_pk: str, rows: Sequence[Mapping[str, Any]]) -> TitleSummary:
    return TitleSummary(
        title_pk=title_pk,
        # Copy the exact API row so callers can access fields not yet promoted
        # to the stable summary surface without mutating the client response.
        title=dict(rows[0]),
        register_type_code=_consensus_text(rows, "regstrGbCd"),
        register_type_name=_consensus_text(rows, "regstrGbCdNm"),
        register_kind_code=_consensus_text(rows, "regstrKindCd"),
        register_kind_name=_consensus_text(rows, "regstrKindCdNm"),
        lot_address=_consensus_text(rows, "platPlc"),
        road_address=_consensus_text(rows, "newPlatPlc"),
        building_name=_consensus_text(rows, "bldNm"),
        dong_name=_consensus_text(rows, "dongNm"),
        purpose_code=_consensus_text(rows, "mainPurpsCd"),
        purpose_name=_consensus_text(rows, "mainPurpsCdNm"),
        other_purpose=_consensus_text(rows, "etcPurps"),
        structure_name=_consensus_text(rows, "strctCdNm"),
        roof_name=_consensus_text(rows, "roofCdNm"),
        site_area=_consensus_decimal(rows, "platArea"),
        building_area=_consensus_decimal(rows, "archArea"),
        total_area=_consensus_decimal(rows, "totArea"),
        floor_ratio_area=_consensus_decimal(rows, "vlRatEstmTotArea"),
        building_coverage_ratio=_consensus_decimal(rows, "bcRat"),
        floor_area_ratio=_consensus_decimal(rows, "vlRat"),
        household_count=_consensus_integer(rows, "hhldCnt"),
        family_count=_consensus_integer(rows, "fmlyCnt"),
        unit_count=_consensus_integer(rows, "hoCnt"),
        ground_floor_count=_consensus_integer(rows, "grndFlrCnt"),
        underground_floor_count=_consensus_integer(rows, "ugrndFlrCnt"),
        permit_date=_consensus_text(rows, "pmsDay"),
        construction_start_date=_consensus_text(rows, "stcnsDay"),
        approval_date=_consensus_text(rows, "useAprDay"),
        is_collective=_is_collective(rows),
        is_multi_family_house=_is_multi_family_house(rows),
        source_row_count=len(rows),
    )


def _make_recap(row: Mapping[str, Any]) -> RecapSummary:
    return RecapSummary(
        recap_pk=_text(row, "mgmBldrgstPk"),
        lot_address=_text(row, "platPlc"),
        road_address=_text(row, "newPlatPlc"),
        building_name=_text(row, "bldNm"),
        purpose_name=_text(row, "mainPurpsCdNm"),
        other_purpose=_text(row, "etcPurps"),
        site_area=_decimal(row.get("platArea")),
        building_area=_decimal(row.get("archArea")),
        total_area=_decimal(row.get("totArea")),
        household_count=_integer(row.get("hhldCnt")),
        family_count=_integer(row.get("fmlyCnt")),
        unit_count=_integer(row.get("hoCnt")),
    )


def _build_parent_graph(
    basis_rows: Sequence[Mapping[str, Any]],
) -> dict[str, frozenset[str]]:
    parent_sets: dict[str, set[str]] = defaultdict(set)
    for row in basis_rows:
        child = _text(row, "mgmBldrgstPk")
        parent = _text(row, "mgmUpBldrgstPk")
        if child and parent:
            parent_sets[child].add(parent)
    return {child: frozenset(parents) for child, parents in parent_sets.items()}


def _resolve_title_pk(
    register_pk: str,
    title_pks: frozenset[str],
    parent_graph: Mapping[str, frozenset[str]],
) -> str | None:
    if register_pk in title_pks:
        return register_pk

    current = register_pk
    visited = {current}
    while True:
        parents = parent_graph.get(current, frozenset())
        # Multiple parents are ambiguous; selecting either would be a guess.
        if len(parents) != 1:
            return None
        parent = next(iter(parents))
        if parent in title_pks:
            return parent
        if parent in visited:
            return None
        visited.add(parent)
        current = parent


def lookup_buildings(
    client: _FetchAllClient | "BuildingHubClient",
    land_key: LandKey,
    *,
    num_of_rows: int = 100,
) -> LookupResult:
    """Fetch and exactly join the six BuildingHUB register sections.

    Client/network exceptions are intentionally allowed to propagate so the UI
    can distinguish an API failure from an empty, successfully queried ledger.
    """

    if (
        isinstance(num_of_rows, bool)
        or not isinstance(num_of_rows, int)
        or not 1 <= num_of_rows <= 100
    ):
        raise ValueError("num_of_rows는 1 이상 100 이하의 정수여야 합니다.")

    rows_by_endpoint: dict[str, list[Mapping[str, Any]]] = {}
    stats: list[EndpointStats] = []
    warnings: list[str] = []
    for endpoint in LOOKUP_ENDPOINTS:
        raw_rows = client.fetch_all(endpoint, land_key, num_of_rows=num_of_rows)
        rows, endpoint_stats = _validate_and_dedupe(endpoint, raw_rows, land_key)
        rows_by_endpoint[endpoint] = rows
        stats.append(endpoint_stats)
        if endpoint_stats.rejected_count:
            warnings.append(
                f"{endpoint}: 요청 지번과 정확히 일치하지 않는 "
                f"{endpoint_stats.rejected_count}개 행을 제외했습니다."
            )

    title_groups: dict[str, list[Mapping[str, Any]]] = {}
    missing_title_pk = 0
    for row in rows_by_endpoint[TITLE_ENDPOINT]:
        title_pk = _text(row, "mgmBldrgstPk")
        if not title_pk:
            missing_title_pk += 1
            continue
        title_groups.setdefault(title_pk, []).append(row)
    if missing_title_pk:
        warnings.append(f"표제부 관리 PK가 없는 {missing_title_pk}개 행을 제외했습니다.")

    base_titles = tuple(
        _make_title(title_pk, title_rows)
        for title_pk, title_rows in title_groups.items()
    )
    title_pks = frozenset(title.title_pk for title in base_titles)
    title_by_pk = {title.title_pk: title for title in base_titles}
    parent_graph = _build_parent_graph(rows_by_endpoint[BASIS_ENDPOINT])

    floors_by_title: dict[str, list[FloorSummary]] = defaultdict(list)
    unlinked_floors: list[FloorSummary] = []
    for row in rows_by_endpoint[FLOOR_ENDPOINT]:
        floor = _make_floor(row)
        title_pk = _resolve_title_pk(floor.register_pk, title_pks, parent_graph)
        if title_pk is None:
            unlinked_floors.append(floor)
        else:
            floors_by_title[title_pk].append(floor)

    area_rows_by_pk: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    missing_area_pk = 0
    for row in rows_by_endpoint[AREA_ENDPOINT]:
        unit_pk = _text(row, "mgmBldrgstPk")
        if unit_pk:
            area_rows_by_pk[unit_pk].append(row)
        else:
            missing_area_pk += 1
    if missing_area_pk:
        warnings.append(f"전유공용면적 관리 PK가 없는 {missing_area_pk}개 행을 제외했습니다.")

    exposure_groups: dict[str, list[Mapping[str, Any]]] = {}
    missing_exposure_pk = 0
    for row in rows_by_endpoint[EXPOSURE_ENDPOINT]:
        unit_pk = _text(row, "mgmBldrgstPk")
        if not unit_pk:
            missing_exposure_pk += 1
            continue
        exposure_groups.setdefault(unit_pk, []).append(row)
    if missing_exposure_pk:
        warnings.append(f"전유부 관리 PK가 없는 {missing_exposure_pk}개 행을 제외했습니다.")

    orphan_area_count = sum(
        len(area_rows)
        for unit_pk, area_rows in area_rows_by_pk.items()
        if unit_pk not in exposure_groups
    )
    if orphan_area_count:
        warnings.append(
            "같은 전유부 관리 PK가 없는 전유공용면적 "
            f"{orphan_area_count}개 행은 호실로 추정 연결하지 않았습니다."
        )

    units_by_title: dict[str, list[UnitSummary]] = defaultdict(list)
    unlinked_units: list[UnitSummary] = []
    for unit_pk, exposure_rows in exposure_groups.items():
        title_pk = _resolve_title_pk(unit_pk, title_pks, parent_graph)
        title = title_by_pk.get(title_pk) if title_pk else None
        source_label = (
            COLLECTIVE_UNIT_SOURCE_LABEL
            if title is not None and title.is_collective
            else EXPLICIT_API_UNIT_SOURCE_LABEL
        )
        unit_area_rows = area_rows_by_pk.get(unit_pk, [])
        classified_rows = [(_classify_area(row), row) for row in unit_area_rows]
        unit = UnitSummary(
            unit_pk=unit_pk,
            title_pk=title_pk,
            source_label=source_label,
            exposures=tuple(_make_exposure(row) for row in exposure_rows),
            exclusive_area=_sum_areas(
                row for category, row in classified_rows if category is AreaCategory.EXCLUSIVE
            ),
            common_area=_sum_areas(
                row for category, row in classified_rows if category is AreaCategory.COMMON
            ),
            other_area=_sum_areas(
                row for category, row in classified_rows if category is AreaCategory.OTHER
            ),
            area_components=_area_components(unit_area_rows),
        )
        if title_pk is None:
            unlinked_units.append(unit)
        else:
            units_by_title[title_pk].append(unit)

    if unlinked_floors:
        warnings.append(
            f"표제부까지 PK 경로가 확인되지 않은 층별개요 {len(unlinked_floors)}개 행을 "
            "추정 연결하지 않았습니다."
        )
    if unlinked_units:
        warnings.append(
            f"표제부까지 PK 경로가 확인되지 않은 전유부 {len(unlinked_units)}개를 "
            "추정 연결하지 않았습니다."
        )

    titles = tuple(
        replace(
            title,
            floors=tuple(floors_by_title.get(title.title_pk, ())),
            units=tuple(units_by_title.get(title.title_pk, ())),
        )
        for title in base_titles
    )
    recaps = tuple(_make_recap(row) for row in rows_by_endpoint[RECAP_ENDPOINT])

    return LookupResult(
        land_key=land_key,
        titles=titles,
        recaps=recaps,
        unlinked_floors=tuple(unlinked_floors),
        unlinked_units=tuple(unlinked_units),
        violation=ViolationAssessment(),
        endpoint_stats=tuple(stats),
        warnings=tuple(warnings),
        source_as_of=_source_as_of(rows_by_endpoint.values()),
    )


# Concise alias for callers that prefer a service-style name.
lookup = lookup_buildings


def _source_as_of(endpoint_rows: Iterable[Sequence[Mapping[str, Any]]]) -> str | None:
    """Return the latest API creation date supplied by any exact-match row."""

    dates = {
        value
        for rows in endpoint_rows
        for row in rows
        if (value := _text(row, "crtnDay")) is not None
    }
    return max(dates) if dates else None


def lookup_register(
    client: _FetchAllClient | "BuildingHubClient",
    parsed_or_land_key: Any,
    *,
    num_of_rows: int = 100,
) -> RegisterSnapshot:
    """App-facing lookup accepting either ``ParsedAddress`` or ``LandKey``."""

    if isinstance(parsed_or_land_key, LandKey):
        land_key = parsed_or_land_key
    else:
        land_key = getattr(parsed_or_land_key, "land_key", None)
        if not isinstance(land_key, LandKey):
            raise TypeError("parsed_or_land_key는 ParsedAddress 또는 LandKey여야 합니다.")
    return lookup_buildings(client, land_key, num_of_rows=num_of_rows)
