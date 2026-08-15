"""Conservative joins for BuildingHUB building-permit household areas.

This module deliberately keeps permit/application history separate from the
current building-register model.  Rows are accepted only when the complete
parcel key matches, and relationships use only the documented permit, dong,
household, and area management keys.  Counts and floor areas are never used to
invent household records or areas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .address import LandKey


PERMIT_BASIS_ENDPOINT = "getApBasisOulnInfo"
PERMIT_DONG_ENDPOINT = "getApDongOulnInfo"
PERMIT_FLOOR_ENDPOINT = "getApFlrOulnInfo"
PERMIT_HOUSEHOLD_ENDPOINT = "getApHoOulnInfo"
PERMIT_GENERAL_AREA_ENDPOINT = "getApExposPubuseAreaInfo"
PERMIT_HOUSEHOLD_AREA_ENDPOINT = "getApHoExposPubuseAreaInfo"
PERMIT_PARCEL_ENDPOINT = "getApPlatPlcInfo"
PERMIT_HOUSING_TYPE_ENDPOINT = "getApHsTpInfo"

PERMIT_LOOKUP_ENDPOINTS = (
    PERMIT_BASIS_ENDPOINT,
    PERMIT_DONG_ENDPOINT,
    PERMIT_FLOOR_ENDPOINT,
    PERMIT_HOUSEHOLD_ENDPOINT,
    PERMIT_GENERAL_AREA_ENDPOINT,
    PERMIT_HOUSEHOLD_AREA_ENDPOINT,
    PERMIT_PARCEL_ENDPOINT,
    PERMIT_HOUSING_TYPE_ENDPOINT,
)


class _FetchAllClient(Protocol):
    def fetch_all(
        self,
        endpoint: str,
        land_key: LandKey,
        num_of_rows: int = 100,
        **query: Any,
    ) -> list[dict[str, Any]]: ...


class PermitLookupDataError(ValueError):
    """The client response violated the documented lookup contract."""


class PermitAreaCategory(str, Enum):
    EXCLUSIVE = "EXCLUSIVE"
    COMMON = "COMMON"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class PermitEndpointStats:
    endpoint: str
    received_count: int
    matched_count: int
    unique_count: int
    rejected_count: int
    duplicate_count: int


@dataclass(frozen=True, slots=True)
class PermitAreaComponent:
    area_pk: str | None
    category: PermitAreaCategory
    exposure_use_code: str | None
    exposure_use_name: str | None
    purpose_code: str | None
    purpose_name: str | None
    other_purpose: str | None
    area: Decimal | None


@dataclass(frozen=True, slots=True)
class PermitUnitReference:
    case_pk: str
    unit_pk: str
    dong_pk: str | None
    dong_name: str | None
    ho_number: str | None
    ho_name: str | None
    floor_group_name: str | None
    floor_number: int | None
    change_name: str | None
    exclusive_area: Decimal | None
    common_area: Decimal | None
    other_area: Decimal | None
    area_components: tuple[PermitAreaComponent, ...]
    warnings: tuple[str, ...] = ()

    @property
    def floor_name(self) -> str | None:
        if self.floor_number is not None:
            return f"{self.floor_number}층"
        return self.floor_group_name

    @property
    def total_area(self) -> Decimal | None:
        # Missing is not zero.  A total is shown only when both documented
        # categories are explicitly present, including an explicit 0.
        if self.exclusive_area is None or self.common_area is None:
            return None
        return self.exclusive_area + self.common_area

    @property
    def purposes(self) -> tuple[str, ...]:
        exclusive = tuple(
            item
            for item in self.area_components
            if item.category is PermitAreaCategory.EXCLUSIVE
        )
        components = exclusive or self.area_components
        labels: list[str] = []
        for component in components:
            label = component.other_purpose or component.purpose_name
            if label and label not in labels:
                labels.append(label)
        return tuple(labels)


@dataclass(frozen=True, slots=True)
class PermitUnassignedAreaReference:
    """Permit area component without an official household foreign key."""

    case_pk: str
    area_pk: str
    plan_name: str | None
    floor_group_name: str | None
    floor_number: int | None
    category: PermitAreaCategory
    purpose_name: str | None
    other_purpose: str | None
    area: Decimal | None
    source_as_of: str | None

    @property
    def floor_name(self) -> str | None:
        if self.floor_number is not None:
            return f"{self.floor_number}층"
        return self.floor_group_name


@dataclass(frozen=True, slots=True)
class PermitFloorReference:
    case_pk: str
    floor_pk: str
    dong_pk: str | None
    building_name: str | None
    floor_group_name: str | None
    floor_number: int | None
    purpose_name: str | None
    structure_name: str | None
    area: Decimal | None
    source_as_of: str | None

    @property
    def floor_name(self) -> str | None:
        if self.floor_number is not None:
            return f"{self.floor_number}층"
        return self.floor_group_name


@dataclass(frozen=True, slots=True)
class PermitParcelReference:
    case_pk: str
    parcel_pk: str
    dong_pk: str | None
    lot_address: str | None
    is_representative: str | None
    related_lot_name: str | None
    main_building_name: str | None
    source_as_of: str | None


@dataclass(frozen=True, slots=True)
class PermitHousingTypeReference:
    case_pk: str
    type_code: str | None
    type_name: str | None
    unit_count: int | None
    unit_area: Decimal | None
    source_as_of: str | None


@dataclass(frozen=True, slots=True)
class PermitCaseReference:
    case_pk: str
    building_name: str | None
    application_type: str | None
    permit_date: str | None
    use_approval_date: str | None
    source_as_of: str | None
    expected_family_count: int | None
    expected_household_count: int | None
    housing_types: tuple[str, ...]
    matches_register_approval_date: bool
    units: tuple[PermitUnitReference, ...]
    unassigned_areas: tuple[PermitUnassignedAreaReference, ...] = ()
    permit_floors: tuple[PermitFloorReference, ...] = ()
    parcels: tuple[PermitParcelReference, ...] = ()
    housing_type_details: tuple[PermitHousingTypeReference, ...] = ()


@dataclass(frozen=True, slots=True)
class PermitHouseholdReference:
    land_key: LandKey
    cases: tuple[PermitCaseReference, ...]
    unlinked_unit_count: int
    orphan_area_count: int
    endpoint_stats: tuple[PermitEndpointStats, ...]
    warnings: tuple[str, ...]
    source_as_of: str | None

    @property
    def has_units(self) -> bool:
        return any(case.units for case in self.cases)


def _text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
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


def _consensus_integer(rows: Sequence[Mapping[str, Any]], *keys: str) -> int | None:
    values: list[int] = []
    for row in rows:
        value = None
        for key in keys:
            value = _integer(row.get(key))
            if value is not None:
                break
        if value is not None and value not in values:
            values.append(value)
    return values[0] if len(values) == 1 else None


def _freeze(value: Any) -> Any:
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


def _normalized_lot(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    return text.zfill(4) if text.isdigit() else text


def _matches_land(row: Mapping[str, Any], land_key: LandKey) -> bool:
    expected = land_key.as_api_params()
    for key, expected_value in expected.items():
        if key not in row or row[key] is None:
            return False
        actual = _normalized_lot(row[key]) if key in {"bun", "ji"} else str(row[key]).strip()
        if actual != expected_value:
            return False
    return True


def _validate_and_dedupe(
    endpoint: str,
    raw_rows: Any,
    land_key: LandKey,
) -> tuple[list[Mapping[str, Any]], PermitEndpointStats]:
    if not isinstance(raw_rows, list):
        raise PermitLookupDataError(f"{endpoint} fetch_all 결과는 list여야 합니다.")

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
        frozen = _freeze(row)
        if frozen in seen:
            continue
        seen.add(frozen)
        unique.append(row)

    return unique, PermitEndpointStats(
        endpoint=endpoint,
        received_count=len(raw_rows),
        matched_count=len(matched),
        unique_count=len(unique),
        rejected_count=rejected_count,
        duplicate_count=len(matched) - len(unique),
    )


def _classify_area(row: Mapping[str, Any]) -> PermitAreaCategory | None:
    code = _text(row, "exposPubuseGbCd")
    name = (_text(row, "exposPubuseGbCdNm") or "").replace(" ", "")
    code_category = {
        "1": PermitAreaCategory.EXCLUSIVE,
        "2": PermitAreaCategory.COMMON,
    }.get(code)
    name_exclusive = "전유" in name
    name_common = "공용" in name
    if name_exclusive and name_common:
        return None
    name_category = (
        PermitAreaCategory.EXCLUSIVE
        if name_exclusive
        else PermitAreaCategory.COMMON
        if name_common
        else None
    )
    if (
        code_category is not None
        and name_category is not None
        and code_category is not name_category
    ):
        return None
    return name_category or code_category or PermitAreaCategory.OTHER


def _component(row: Mapping[str, Any]) -> PermitAreaComponent:
    category = _classify_area(row)
    if category is None:
        raise PermitLookupDataError("전유·공용 코드와 명칭이 충돌하는 면적 행입니다.")
    return PermitAreaComponent(
        area_pk=_text(row, "mgmHoExposPubuseAreaPk"),
        category=category,
        exposure_use_code=_text(row, "exposPubuseGbCd"),
        exposure_use_name=_text(row, "exposPubuseGbCdNm"),
        purpose_code=_text(row, "mainPurpsCd"),
        purpose_name=_text(row, "mainPurpsCdNm"),
        other_purpose=_text(row, "etcPurps"),
        area=_decimal(row.get("area")),
    )


def _unassigned_area_component(
    row: Mapping[str, Any],
    case_pk: str,
) -> PermitUnassignedAreaReference:
    category = _classify_area(row)
    if category is None:
        raise PermitLookupDataError("전유·공용 코드와 명칭이 충돌하는 면적 행입니다.")
    area_pk = _text(row, "mgmExposPubuseAreaPk")
    if area_pk is None:
        raise PermitLookupDataError("관리전유공용면적 PK가 없는 행입니다.")
    return PermitUnassignedAreaReference(
        case_pk=case_pk,
        area_pk=area_pk,
        plan_name=_text(row, "pngtypGbNm"),
        floor_group_name=_text(row, "flrGbCdNm"),
        floor_number=_integer(row.get("flrNo")),
        category=category,
        purpose_name=_text(row, "mainPurpsCdNm"),
        other_purpose=_text(row, "etcPurps"),
        area=_decimal(row.get("area")),
        source_as_of=_text(row, "crtnDay"),
    )


def _safe_pk_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    pk_field: str,
    label: str,
) -> tuple[list[Mapping[str, Any]], tuple[str, ...]]:
    """Reject rows that cannot be identified or conflict on one official PK."""

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    missing_count = 0
    for row in rows:
        row_pk = _text(row, pk_field)
        if row_pk is None:
            missing_count += 1
        else:
            grouped[row_pk].append(row)

    safe: list[Mapping[str, Any]] = []
    warnings: list[str] = []
    if missing_count:
        warnings.append(f"{label} PK가 없는 {missing_count}개 행을 제외했습니다.")
    for row_pk, grouped_rows in grouped.items():
        if len(grouped_rows) == 1:
            safe.append(grouped_rows[0])
            continue

        # The gateway may repeat the same business row with a different page
        # sequence or collection date.  These metadata-only variants are not
        # a data conflict; keep the latest one.  Any other difference remains
        # ambiguous and is excluded rather than arbitrarily selected.
        payloads = {
            _freeze(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"rnum", "crtnDay"}
                }
            )
            for row in grouped_rows
        }
        if len(payloads) == 1:
            safe.append(
                max(
                    grouped_rows,
                    key=lambda row: (_text(row, "crtnDay") or "", repr(_freeze(row))),
                )
            )
            continue
        warnings.append(
            f"{label} PK {row_pk}가 서로 다른 값으로 중복되어 제외했습니다."
        )
    return safe, tuple(warnings)


def _safe_area_rows(
    unit_pk: str,
    case_pk: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], tuple[str, ...]]:
    """Keep only unambiguous rows under one unit and permit case."""

    by_area_pk: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    missing_area_pk = 0
    mismatched_case = 0
    conflicting_category = 0
    for row in rows:
        area_pk = _text(row, "mgmHoExposPubuseAreaPk")
        if area_pk is None:
            missing_area_pk += 1
            continue
        area_case_pk = _text(row, "mgmPmsrgstPk")
        if area_case_pk is not None and area_case_pk != case_pk:
            mismatched_case += 1
            continue
        if _classify_area(row) is None:
            conflicting_category += 1
            continue
        by_area_pk[area_pk].append(row)

    safe: list[Mapping[str, Any]] = []
    warnings: list[str] = []
    if missing_area_pk:
        warnings.append(
            f"호 관리 PK {unit_pk}의 면적 PK가 없는 {missing_area_pk}개 행을 제외했습니다."
        )
    if mismatched_case:
        warnings.append(
            f"호 관리 PK {unit_pk}의 인허가 이력 PK가 일치하지 않는 "
            f"면적 {mismatched_case}개 행을 제외했습니다."
        )
    if conflicting_category:
        warnings.append(
            f"호 관리 PK {unit_pk}의 전유·공용 코드와 명칭이 충돌하는 "
            f"면적 {conflicting_category}개 행을 제외했습니다."
        )
    for area_pk, area_rows in by_area_pk.items():
        if len(area_rows) == 1:
            safe.append(area_rows[0])
            continue
        warnings.append(
            f"호 관리 PK {unit_pk}의 면적 PK {area_pk}가 서로 다른 값으로 중복되어 합계에서 제외했습니다."
        )
    return safe, tuple(warnings)


def _unit_change_exclusion_warning(
    unit_pk: str,
    rows: Sequence[Mapping[str, Any]],
) -> str | None:
    supplied_codes = tuple(_text(row, "changGbCd") for row in rows)
    codes = {code for code in supplied_codes if code is not None}
    if "4" in codes:
        return f"호 관리 PK {unit_pk}는 변경구분 코드 4(삭제)가 있어 제외했습니다."
    if codes and (len(codes) != 1 or any(code is None for code in supplied_codes)):
        return f"호 관리 PK {unit_pk}의 변경구분 코드가 혼합되거나 누락되어 제외했습니다."
    return None


def _sum_category(
    components: Sequence[PermitAreaComponent],
    category: PermitAreaCategory,
) -> Decimal | None:
    selected = [item for item in components if item.category is category]
    if not selected or any(item.area is None for item in selected):
        return None
    return sum((item.area for item in selected if item.area is not None), Decimal("0"))


def _source_as_of(endpoint_rows: Iterable[Sequence[Mapping[str, Any]]]) -> str | None:
    dates = {
        value
        for rows in endpoint_rows
        for row in rows
        if (value := _text(row, "crtnDay")) is not None
    }
    return max(dates) if dates else None


def _case_sort_key(case: PermitCaseReference) -> tuple[int, str, str, str]:
    return (
        1 if case.matches_register_approval_date else 0,
        case.use_approval_date or "",
        case.permit_date or "",
        case.source_as_of or "",
    )


def lookup_permit_households(
    client: _FetchAllClient,
    land_key: LandKey,
    *,
    register_approval_dates: Iterable[str] = (),
    num_of_rows: int = 100,
) -> PermitHouseholdReference:
    """Return parcel-level permit-history household areas.

    All permit cases remain separate.  A matching building-register approval
    date is only a display signal; it never causes rows from different permit
    management keys to be merged.
    """

    if (
        isinstance(num_of_rows, bool)
        or not isinstance(num_of_rows, int)
        or not 1 <= num_of_rows <= 100
    ):
        raise ValueError("num_of_rows는 1 이상 100 이하의 정수여야 합니다.")

    rows_by_endpoint: dict[str, list[Mapping[str, Any]]] = {}
    stats: list[PermitEndpointStats] = []
    warnings: list[str] = []
    for endpoint in PERMIT_LOOKUP_ENDPOINTS:
        raw_rows = client.fetch_all(endpoint, land_key, num_of_rows=num_of_rows)
        rows, endpoint_stats = _validate_and_dedupe(endpoint, raw_rows, land_key)
        rows_by_endpoint[endpoint] = rows
        stats.append(endpoint_stats)
        if endpoint_stats.rejected_count:
            warnings.append(
                f"{endpoint}: 요청 지번과 정확히 일치하지 않는 "
                f"{endpoint_stats.rejected_count}개 행을 제외했습니다."
            )

    basis_by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows_by_endpoint[PERMIT_BASIS_ENDPOINT]:
        case_pk = _text(row, "mgmPmsrgstPk")
        if case_pk:
            basis_by_case[case_pk].append(row)
        else:
            warnings.append("관리허가대장 PK가 없는 기본개요 행을 제외했습니다.")

    dong_by_pk: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows_by_endpoint[PERMIT_DONG_ENDPOINT]:
        dong_pk = _text(row, "mgmDongOulnPk")
        if dong_pk:
            dong_by_pk[dong_pk].append(row)

    unassigned_areas_by_case: dict[
        str, list[PermitUnassignedAreaReference]
    ] = defaultdict(list)
    safe_general_area_rows, general_area_warnings = _safe_pk_rows(
        rows_by_endpoint[PERMIT_GENERAL_AREA_ENDPOINT],
        pk_field="mgmExposPubuseAreaPk",
        label="인허가 전유공용면적",
    )
    warnings.extend(general_area_warnings)
    for row in safe_general_area_rows:
        case_pk = _text(row, "mgmPmsrgstPk")
        if case_pk is None or case_pk not in basis_by_case:
            warnings.append(
                "기본개요에 연결되지 않는 인허가 전유공용면적 행을 제외했습니다."
            )
            continue
        if _classify_area(row) is None:
            warnings.append(
                f"인허가 이력 {case_pk}의 전유·공용 코드와 명칭이 충돌하는 "
                "면적 행을 제외했습니다."
            )
            continue
        unassigned_areas_by_case[case_pk].append(
            _unassigned_area_component(row, case_pk)
        )

    permit_floors_by_case: dict[str, list[PermitFloorReference]] = defaultdict(list)
    safe_floor_rows, floor_warnings = _safe_pk_rows(
        rows_by_endpoint[PERMIT_FLOOR_ENDPOINT],
        pk_field="mgmFlrOulnPk",
        label="인허가 층별개요",
    )
    warnings.extend(floor_warnings)
    for row in safe_floor_rows:
        case_pk = _text(row, "mgmPmsrgstPk")
        if case_pk is None or case_pk not in basis_by_case:
            warnings.append("기본개요에 연결되지 않는 인허가 층별개요 행을 제외했습니다.")
            continue
        floor_pk = _text(row, "mgmFlrOulnPk")
        if floor_pk is None:
            continue
        permit_floors_by_case[case_pk].append(
            PermitFloorReference(
                case_pk=case_pk,
                floor_pk=floor_pk,
                dong_pk=_text(row, "mgmDongOulnPk"),
                building_name=_text(row, "bldNm"),
                floor_group_name=_text(row, "flrGbCdNm"),
                floor_number=_integer(row.get("flrNo")),
                purpose_name=_text(row, "mainPurpsCdNm"),
                structure_name=_text(row, "strctCdNm"),
                area=_decimal(row.get("flrArea")),
                source_as_of=_text(row, "crtnDay"),
            )
        )

    parcels_by_case: dict[str, list[PermitParcelReference]] = defaultdict(list)
    safe_parcel_rows, parcel_warnings = _safe_pk_rows(
        rows_by_endpoint[PERMIT_PARCEL_ENDPOINT],
        pk_field="mgmPlatPlcPk",
        label="인허가 대지위치",
    )
    warnings.extend(parcel_warnings)
    for row in safe_parcel_rows:
        case_pk = _text(row, "mgmPmsrgstPk")
        if case_pk is None or case_pk not in basis_by_case:
            warnings.append("기본개요에 연결되지 않는 인허가 대지위치 행을 제외했습니다.")
            continue
        parcel_pk = _text(row, "mgmPlatPlcPk")
        if parcel_pk is None:
            continue
        parcels_by_case[case_pk].append(
            PermitParcelReference(
                case_pk=case_pk,
                parcel_pk=parcel_pk,
                dong_pk=_text(row, "mgmDongOulnPk"),
                lot_address=_text(row, "platPlc"),
                is_representative=_text(row, "reprYn"),
                related_lot_name=_text(row, "relJibunNm"),
                main_building_name=_text(row, "mainDongGbCdNm"),
                source_as_of=_text(row, "crtnDay"),
            )
        )

    area_by_unit: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    orphan_area_count = 0
    for row in rows_by_endpoint[PERMIT_HOUSEHOLD_AREA_ENDPOINT]:
        unit_pk = _text(row, "mgmHoDetlPk")
        if unit_pk:
            area_by_unit[unit_pk].append(row)
        else:
            orphan_area_count += 1

    unit_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows_by_endpoint[PERMIT_HOUSEHOLD_ENDPOINT]:
        unit_pk = _text(row, "mgmHoDetlPk")
        if unit_pk:
            unit_groups[unit_pk].append(row)
        else:
            warnings.append("호별개요 관리 PK가 없는 행을 제외했습니다.")

    orphan_area_count += sum(
        len(area_rows)
        for unit_pk, area_rows in area_by_unit.items()
        if unit_pk not in unit_groups
    )
    if orphan_area_count:
        warnings.append(
            f"호별개요 PK에 연결되지 않는 호별면적 {orphan_area_count}개 행을 제외했습니다."
        )

    units_by_case: dict[str, list[PermitUnitReference]] = defaultdict(list)
    unlinked_unit_count = 0
    for unit_pk, unit_rows in unit_groups.items():
        change_warning = _unit_change_exclusion_warning(unit_pk, unit_rows)
        if change_warning is not None:
            warnings.append(change_warning)
            continue

        case_pk = _consensus_text(unit_rows, "mgmPmsrgstPk")
        if case_pk is None or case_pk not in basis_by_case:
            unlinked_unit_count += 1
            continue

        dong_pk = _consensus_text(unit_rows, "mgmDongOulnPk")
        dong_rows = dong_by_pk.get(dong_pk, []) if dong_pk else []
        if dong_rows:
            dong_case = _consensus_text(dong_rows, "mgmPmsrgstPk")
            if dong_case is not None and dong_case != case_pk:
                unlinked_unit_count += 1
                warnings.append(
                    f"호 관리 PK {unit_pk}의 동 PK가 다른 인허가 이력을 가리켜 제외했습니다."
                )
                continue

        safe_area_rows, unit_warnings = _safe_area_rows(
            unit_pk, case_pk, area_by_unit.get(unit_pk, ())
        )
        components = tuple(_component(row) for row in safe_area_rows)
        unit = PermitUnitReference(
            case_pk=case_pk,
            unit_pk=unit_pk,
            dong_pk=dong_pk,
            dong_name=_consensus_text(dong_rows, "bldNm"),
            ho_number=_consensus_text(unit_rows, "hoNo"),
            ho_name=_consensus_text(unit_rows, "hoNm"),
            floor_group_name=_consensus_text(unit_rows, "flrGbCdNm"),
            floor_number=_consensus_integer(unit_rows, "flrNo"),
            change_name=_consensus_text(unit_rows, "changGbCdNm"),
            exclusive_area=_sum_category(components, PermitAreaCategory.EXCLUSIVE),
            common_area=_sum_category(components, PermitAreaCategory.COMMON),
            other_area=_sum_category(components, PermitAreaCategory.OTHER),
            area_components=components,
            warnings=unit_warnings,
        )
        units_by_case[case_pk].append(unit)
        warnings.extend(unit_warnings)

    if unlinked_unit_count:
        warnings.append(
            f"기본개요까지 관리 PK 연결이 확인되지 않은 호별개요 {unlinked_unit_count}개를 제외했습니다."
        )

    housing_types_by_case: dict[str, list[str]] = defaultdict(list)
    housing_type_details_by_case: dict[
        str, list[PermitHousingTypeReference]
    ] = defaultdict(list)
    for row in rows_by_endpoint[PERMIT_HOUSING_TYPE_ENDPOINT]:
        case_pk = _text(row, "mgmPmsrgstPk")
        label = _text(row, "hstpGbCdNm")
        if case_pk and label and label not in housing_types_by_case[case_pk]:
            housing_types_by_case[case_pk].append(label)
        if case_pk and case_pk in basis_by_case:
            housing_type_details_by_case[case_pk].append(
                PermitHousingTypeReference(
                    case_pk=case_pk,
                    type_code=_text(row, "hstpGbCd"),
                    type_name=label,
                    unit_count=_integer(row.get("silHoHhldCnt")),
                    unit_area=_decimal(row.get("silHoHhldArea")),
                    source_as_of=_text(row, "crtnDay"),
                )
            )

    approval_dates = {
        str(value).strip()
        for value in register_approval_dates
        if value is not None and str(value).strip()
    }
    cases: list[PermitCaseReference] = []
    for case_pk, basis_rows in basis_by_case.items():
        units = tuple(
            sorted(
                units_by_case.get(case_pk, ()),
                key=lambda item: (
                    item.dong_name or "",
                    item.floor_number if item.floor_number is not None else -10_000,
                    item.ho_name or item.ho_number or "",
                    item.unit_pk,
                ),
            )
        )
        use_approval_date = _consensus_text(basis_rows, "useAprDay")
        case_source = _source_as_of((basis_rows,))
        cases.append(
            PermitCaseReference(
                case_pk=case_pk,
                building_name=_consensus_text(basis_rows, "bldNm"),
                application_type=_consensus_text(basis_rows, "archGbCdNm"),
                permit_date=_consensus_text(basis_rows, "archPmsDay"),
                use_approval_date=use_approval_date,
                source_as_of=case_source,
                expected_family_count=_consensus_integer(basis_rows, "fmlyCnt"),
                # The permit API's documented multi-family completeness count is
                # fmlyCnt.  Keep this compatibility field unset rather than
                # guessing from building-register or undocumented aliases.
                expected_household_count=None,
                housing_types=tuple(housing_types_by_case.get(case_pk, ())),
                matches_register_approval_date=bool(
                    use_approval_date and use_approval_date in approval_dates
                ),
                units=units,
                unassigned_areas=tuple(
                    sorted(
                        unassigned_areas_by_case.get(case_pk, ()),
                        key=lambda item: (
                            item.plan_name or "",
                            item.floor_number
                            if item.floor_number is not None
                            else -10_000,
                            {
                                PermitAreaCategory.EXCLUSIVE: 0,
                                PermitAreaCategory.COMMON: 1,
                                PermitAreaCategory.OTHER: 2,
                            }[item.category],
                            item.area_pk,
                        ),
                    )
                ),
                permit_floors=tuple(
                    sorted(
                        permit_floors_by_case.get(case_pk, ()),
                        key=lambda item: (
                            item.building_name or "",
                            item.floor_number
                            if item.floor_number is not None
                            else -10_000,
                            item.floor_pk,
                        ),
                    )
                ),
                parcels=tuple(
                    sorted(
                        parcels_by_case.get(case_pk, ()),
                        key=lambda item: (
                            0 if item.is_representative in {"Y", "1"} else 1,
                            item.lot_address or "",
                            item.parcel_pk,
                        ),
                    )
                ),
                housing_type_details=tuple(
                    housing_type_details_by_case.get(case_pk, ())
                ),
            )
        )

    cases.sort(key=_case_sort_key, reverse=True)
    source_as_of = _source_as_of(rows_by_endpoint.values())
    return PermitHouseholdReference(
        land_key=land_key,
        cases=tuple(cases),
        unlinked_unit_count=unlinked_unit_count,
        orphan_area_count=orphan_area_count,
        endpoint_stats=tuple(stats),
        warnings=tuple(dict.fromkeys(warnings)),
        source_as_of=source_as_of,
    )


__all__ = [
    "PERMIT_BASIS_ENDPOINT",
    "PERMIT_DONG_ENDPOINT",
    "PERMIT_FLOOR_ENDPOINT",
    "PERMIT_GENERAL_AREA_ENDPOINT",
    "PERMIT_HOUSEHOLD_AREA_ENDPOINT",
    "PERMIT_HOUSEHOLD_ENDPOINT",
    "PERMIT_HOUSING_TYPE_ENDPOINT",
    "PERMIT_PARCEL_ENDPOINT",
    "PERMIT_LOOKUP_ENDPOINTS",
    "PermitAreaCategory",
    "PermitAreaComponent",
    "PermitCaseReference",
    "PermitEndpointStats",
    "PermitFloorReference",
    "PermitHouseholdReference",
    "PermitHousingTypeReference",
    "PermitLookupDataError",
    "PermitParcelReference",
    "PermitUnassignedAreaReference",
    "PermitUnitReference",
    "lookup_permit_households",
]
