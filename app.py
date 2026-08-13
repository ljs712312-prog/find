"""Streamlit UI for the official BuildingHUB-based register lookup."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import re
from typing import Any, Iterable, Mapping

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src.address import AddressParseError, LandKey, ParsedAddress, parse_address
from src.building_hub import (
    BuildingHubAPIError,
    BuildingHubAuthError,
    BuildingHubClient,
    BuildingHubError,
    BuildingHubHTTPError,
    BuildingHubNetworkError,
    BuildingHubQuotaError,
    BuildingHubRateLimitError,
)
from src.legacy import LegacyBuilding, load_legacy_frames, lookup_legacy
from src.lookup import RegisterSnapshot, TitleSummary, UnitSummary, lookup_register
from src.vworld import (
    ViolationReference,
    ViolationState,
    VWorldClient,
    VWorldError,
)


# Bump this whenever cached API response interpretation changes.  Streamlit
# hashes this argument into each entry, so a hot deploy cannot keep serving a
# snapshot produced by an older register-mapping rule.
LOOKUP_CACHE_SCHEMA = "2026-08-13.2"


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    parsed: ParsedAddress
    snapshot: RegisterSnapshot | None = None
    legacy: tuple[LegacyBuilding, ...] = ()
    api_error: str | None = None
    used_legacy: bool = False


def _secret(name: str) -> str | None:
    """Read an optional Streamlit secret without leaking or requiring a file."""

    try:
        value = st.secrets.get(name)
    except (StreamlitSecretNotFoundError, FileNotFoundError, KeyError):
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _key_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@st.cache_data(ttl=6 * 60 * 60, max_entries=256, show_spinner=False)
def _lookup_api_cached(
    sigungu_cd: str,
    bjdong_cd: str,
    plat_gb_cd: str,
    bun: str,
    ji: str,
    cache_schema: str,
    key_fingerprint: str,
    _service_key: str,
) -> RegisterSnapshot:
    # ``key_fingerprint`` invalidates old cached responses after key rotation;
    # the actual secret is excluded from Streamlit's cache key and never logged.
    del cache_schema, key_fingerprint
    land_key = LandKey(sigungu_cd, bjdong_cd, plat_gb_cd, bun, ji)
    with BuildingHubClient(_service_key) as client:
        return lookup_register(client, land_key)


@st.cache_data(show_spinner=False)
def _legacy_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_legacy_frames()


@st.cache_data(ttl=60 * 60, max_entries=256, show_spinner=False)
def _vworld_cached(
    sigungu_cd: str,
    bjdong_cd: str,
    plat_gb_cd: str,
    bun: str,
    ji: str,
    key_fingerprint: str,
    domain: str | None,
    _api_key: str,
) -> ViolationReference:
    del key_fingerprint
    land_key = LandKey(sigungu_cd, bjdong_cd, plat_gb_cd, bun, ji)
    return VWorldClient(_api_key, domain=domain).get_violation_reference(land_key)


def _land_args(land_key: LandKey) -> tuple[str, str, str, str, str]:
    return (
        land_key.sigungu_cd,
        land_key.bjdong_cd,
        land_key.plat_gb_cd,
        land_key.bun,
        land_key.ji,
    )


def _friendly_api_error(error: BuildingHubError) -> str:
    if isinstance(error, BuildingHubAuthError):
        return "건축HUB 인증키가 아직 동기화되지 않았거나 사용 권한이 없습니다."
    if isinstance(error, BuildingHubQuotaError):
        return "오늘의 건축HUB API 호출 한도를 모두 사용했습니다."
    if isinstance(error, BuildingHubRateLimitError):
        return "건축HUB 요청이 잠시 몰렸습니다. 잠시 후 다시 조회해 주세요."
    if isinstance(error, BuildingHubNetworkError):
        return "건축HUB 서버에 연결하지 못했습니다."
    if isinstance(error, BuildingHubHTTPError):
        return f"건축HUB가 HTTP {error.status_code} 오류로 응답했습니다."
    if isinstance(error, BuildingHubAPIError):
        if error.result_code == "10":
            return "건축HUB가 요청 파라미터 오류를 반환했습니다. 인증키 승인 동기화를 확인해 주세요."
        return f"건축HUB 오류가 발생했습니다. (코드 {error.result_code})"
    return "건축HUB 응답을 처리하지 못했습니다."


def _search(query: str, service_key: str | None) -> SearchOutcome:
    parsed = parse_address(query)
    if service_key:
        try:
            snapshot = _lookup_api_cached(
                *_land_args(parsed.land_key),
                LOOKUP_CACHE_SCHEMA,
                _key_fingerprint(service_key),
                service_key,
            )
        except BuildingHubError as error:
            api_error = _friendly_api_error(error)
        else:
            return SearchOutcome(parsed=parsed, snapshot=snapshot)
    else:
        api_error = "배포 설정에 건축HUB API 키가 없습니다."

    master, floors = _legacy_frames()
    legacy = lookup_legacy(parsed, master, floors)
    return SearchOutcome(
        parsed=parsed,
        legacy=legacy,
        api_error=api_error,
        used_legacy=bool(legacy),
    )


def _text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    result = str(value).strip()
    return result if result else fallback


def _date(value: Any) -> str:
    text = _text(value)
    if text == "-":
        return text
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
    if len(digits) == 6:
        return f"{digits[:4]}.{digits[4:6]}"
    if len(digits) == 4:
        return digits
    return text


def _decimal_text(value: Decimal | Any, *, suffix: str = "㎡") -> str:
    if value is None or str(value).strip() == "":
        return "-"
    try:
        number = Decimal(str(value))
    except Exception:  # presentation helper: preserve a non-numeric source value
        return _text(value)
    formatted = format(number.normalize(), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{formatted} {suffix}".strip()


def _count_text(value: int | None, unit: str) -> str:
    return "확인 불가" if value is None else f"{value:,}{unit}"


def _sum_int_fields(row: Mapping[str, Any], fields: Iterable[str]) -> int | None:
    values: list[int] = []
    for field in fields:
        raw = row.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            values.append(int(Decimal(str(raw))))
        except Exception:
            continue
    return sum(values) if values else None


def _natural_key(value: Any) -> tuple[Any, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", _text(value, ""))
    )


def _unit_total(unit: UnitSummary) -> Decimal | None:
    # A missing common/exclusive section is unknown, not an implicit zero.
    if unit.exclusive_area is None or unit.common_area is None:
        return None
    return unit.exclusive_area + unit.common_area


def _unit_floor_label(unit: UnitSummary) -> str:
    names = tuple(
        dict.fromkeys(item.floor_name for item in unit.exposures if item.floor_name)
    )
    if len(names) == 1:
        return names[0]
    numbers = tuple(
        dict.fromkeys(
            item.floor_number
            for item in unit.exposures
            if item.floor_number is not None
        )
    )
    return f"{numbers[0]}층" if len(numbers) == 1 else "-"


def _floor_table(building: TitleSummary) -> pd.DataFrame:
    rows = [
        {
            "층": floor.floor_name
            or (
                f"{floor.floor_number}층"
                if floor.floor_number is not None
                else floor.floor_group_name
            )
            or "-",
            "주용도": floor.purpose_name or "-",
            "상세용도": floor.other_purpose or "-",
            "구조": floor.structure_name or "-",
            "면적(㎡)": _decimal_text(floor.area, suffix="").strip(),
        }
        for floor in building.floors
    ]
    rows.sort(key=lambda item: _natural_key(item["층"]))
    return pd.DataFrame(rows)


def _unit_table(building: TitleSummary) -> pd.DataFrame:
    rows = [
        {
            "동": unit.dong_name or building.dong_name or "-",
            "층": _unit_floor_label(unit),
            "호": unit.ho_name or "-",
            "전유면적(㎡)": _decimal_text(unit.exclusive_area, suffix="").strip(),
            "공용면적(㎡)": _decimal_text(unit.common_area, suffix="").strip(),
            "전유+공용(㎡)": _decimal_text(_unit_total(unit), suffix="").strip(),
            "용도": ", ".join(unit.purposes) or "-",
        }
        for unit in building.units
    ]
    rows.sort(
        key=lambda item: (
            _natural_key(item["동"]),
            _natural_key(item["층"]),
            _natural_key(item["호"]),
        )
    )
    return pd.DataFrame(rows)


def _render_violation(parsed: ParsedAddress) -> None:
    key = _secret("VWORLD_API_KEY")
    if not key:
        st.warning(
            "위반 여부: 건축HUB 공개 API에서 확인할 수 없습니다. "
            "VWorld 키 연동 전에는 세움터·정부24 발급 대장으로 확인해 주세요."
        )
        return

    try:
        reference = _vworld_cached(
            *_land_args(parsed.land_key),
            _key_fingerprint(key),
            _secret("VWORLD_DOMAIN"),
            key,
        )
    except VWorldError:
        st.warning("위반 여부: VWorld 참고정보를 불러오지 못했습니다. 원본 대장을 확인해 주세요.")
        return

    tail = f" (기준 {reference.as_of})" if reference.as_of else ""
    if reference.state is ViolationState.YES:
        st.error(f"VWorld 참고정보: 위반건축물 표시가 있습니다{tail}. 원본 대장 확인이 필요합니다.")
    elif reference.state is ViolationState.NO:
        st.success(
            f"VWorld 참고정보: 위반 표시 없음{tail}. 다만 법적 확인값은 아니므로 원본 대장을 확인해 주세요."
        )
    elif reference.state is ViolationState.MIXED:
        st.warning(f"VWorld 참고정보: 같은 필지의 건물별 위반 표시가 서로 다릅니다{tail}.")
    else:
        st.warning(f"위반 여부: VWorld에서도 확인되지 않습니다{tail}. 원본 대장을 확인해 주세요.")


def _metric_cards(
    building: TitleSummary,
) -> tuple[tuple[str, str, str | None], ...]:
    title = building.title
    parking = _sum_int_fields(
        title,
        (
            "indrAutoUtcnt",
            "oudrAutoUtcnt",
            "indrMechUtcnt",
            "oudrMechUtcnt",
        ),
    )
    elevators = _sum_int_fields(title, ("rideUseElvtCnt", "emgenUseElvtCnt"))
    return (
        (
            "층수",
            f"지상 {_count_text(building.ground_floor_count, '층')}",
            f"지하 {_count_text(building.underground_floor_count, '층')}",
        ),
        (
            "세대 · 가구",
            _count_text(building.household_count, "세대"),
            _count_text(building.family_count, "가구"),
        ),
        ("주차", _count_text(parking, "대"), None),
        ("승강기", _count_text(elevators, "대"), None),
    )


def _render_metrics(building: TitleSummary) -> None:
    # Fixed-width children in a horizontal container wrap onto a new row on
    # narrow screens.  Secondary values keep floor and household pairs clear
    # without forcing two long strings onto a single metric line.
    with st.container(horizontal=True, gap="small"):
        for label, value, secondary in _metric_cards(building):
            st.metric(
                label,
                value,
                delta=secondary,
                delta_color="off",
                delta_arrow="off",
                width=190,
            )


def _render_building(building: TitleSummary, index: int) -> None:
    label_parts = tuple(
        dict.fromkeys(
            part
            for part in (building.building_name, building.dong_name)
            if part
        )
    )
    label = " ".join(label_parts) or f"{building.register_group} 건축물 {index + 1}"

    with st.container(border=True):
        st.subheader(f"{label} · {building.register_group}")
        st.write(f"**지번**  {building.lot_address or '-'}")
        st.write(f"**도로명**  {building.road_address or '정보 없음'}")
        _render_metrics(building)

        left, right = st.columns(2)
        left.info(f"**주용도**  {building.purpose_name or '-'}")
        right.info(f"**사용승인일**  {_date(building.approval_date)}")
        details = [
            ("상세용도", building.other_purpose),
            ("구조", building.structure_name),
            ("대지면적", _decimal_text(building.site_area)),
            ("건축면적", _decimal_text(building.building_area)),
            ("연면적", _decimal_text(building.total_area)),
        ]
        st.caption(" · ".join(f"{name}: {_text(value)}" for name, value in details))

        if building.floors:
            st.markdown("#### 층별 현황")
            st.dataframe(
                _floor_table(building),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("이 건축물의 층별개요가 공개 API에 없습니다.")

        if building.units:
            heading = "집합건물 호실별 면적" if building.is_collective else "API가 명시적으로 반환한 호별 정보"
            st.markdown(f"#### {heading}")
            st.dataframe(
                _unit_table(building),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "전유·공용 면적은 호실 관리 PK가 같은 모든 면적 행을 구분해 합산했습니다. "
                "‘전유+공용’은 앱의 참고 계산값입니다."
            )
        elif building.is_collective:
            st.warning("집합건물이지만 공개 API에서 이 표제부에 연결되는 전유부를 확인하지 못했습니다.")
        elif building.is_multi_family_house:
            st.warning(
                "다가구주택 호(가구)별 면적대장(별지 제9호)은 현재 건축HUB 공개 API가 제공하지 않습니다. "
                "층 면적을 가구 수로 나누어 추정하지 않았습니다."
            )


def _render_api(outcome: SearchOutcome) -> None:
    assert outcome.snapshot is not None
    snapshot = outcome.snapshot
    if not snapshot.buildings:
        st.error("공식 API 조회 결과가 없습니다. 지번과 산번지 여부를 확인해 주세요.")
        return

    st.success(f"공식 건축HUB에서 건축물 {len(snapshot.buildings)}건을 확인했습니다.")
    st.caption(
        f"정규화 주소: {outcome.parsed.canonical_address} · "
        f"대장 레코드 생성일: {_date(snapshot.source_as_of)} · 월간 갱신 API"
    )
    _render_violation(outcome.parsed)
    for index, building in enumerate(snapshot.buildings):
        _render_building(building, index)

    if snapshot.warnings:
        with st.expander("데이터 연결 주의사항"):
            for warning in snapshot.warnings:
                st.write(f"- {warning}")


def _render_legacy_building(building: LegacyBuilding, index: int) -> None:
    row = building.title
    label = " ".join(
        part for part in (row.get("건물명"), row.get("동명칭")) if _text(part, "")
    ) or f"스냅샷 건축물 {index + 1}"
    with st.container(border=True):
        st.subheader(label)
        st.write(f"**지번**  {_text(row.get('대지위치'))}")
        st.write(f"**도로명**  {_text(row.get('도로명대지위치'), '정보 없음')}")
        left, right = st.columns(2)
        left.info(f"**주용도**  {_text(row.get('주용도코드명'))}")
        right.info(f"**사용승인일**  {_date(row.get('사용승인일'))}")
        if building.floors:
            data = [
                {
                    "층": f"{_text(item.get('층번호'))}층",
                    "주용도": _text(item.get("주용도코드명")),
                    "상세용도": _text(item.get("기타용도")),
                    "면적(㎡)": _text(item.get("면적(㎡)")),
                }
                for item in building.floors
            ]
            data.sort(key=lambda item: _natural_key(item["층"]))
            st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")


def _render_legacy(outcome: SearchOutcome) -> None:
    st.warning(
        f"{outcome.api_error} 기존 수원 CSV 스냅샷의 요약·층별 정보만 임시로 표시합니다. "
        "호실면적과 위반 여부는 표시하지 않습니다."
    )
    for index, building in enumerate(outcome.legacy):
        _render_legacy_building(building, index)


def _render_intro() -> None:
    st.info(
        "수원시 법정동 지번을 입력하세요. 산번지는 ‘산’을 포함해야 합니다.  "
        "예: `망포동 6-11`, `오목천동 산1-5`, `매산로1가 1-4`"
    )


def render_app() -> None:
    st.set_page_config(
        page_title="원탑 건축물대장",
        page_icon="🏢",
        layout="centered",
    )
    st.markdown(
        """
        <style>
        .block-container {max-width: 920px; padding-top: 2.5rem; padding-bottom: 4rem;}
        h1 {text-align: center; letter-spacing: -0.04em;}
        div[data-testid="stMetric"] {border: 1px solid #dfe4ec; border-radius: 12px; padding: 0.8rem;}
        div[data-testid="stMetricValue"] {white-space: normal; overflow-wrap: anywhere; line-height: 1.15;}
        div[data-testid="stFormSubmitButton"] button {min-height: 44px; font-weight: 700;}
        div[data-testid="stTextInput"] input {min-height: 44px;}
        @media (max-width: 640px) {
          .block-container {padding-left: 1rem; padding-right: 1rem; padding-top: 1.5rem;}
          h1 {font-size: 1.85rem !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("🏢 원탑 건축물대장")
    st.caption("국토교통부 건축HUB 공식 API 기반 · 수원시 지번 조회")

    with st.form("search_form", clear_on_submit=False):
        query = st.text_input(
            "지번 주소",
            placeholder="예: 망포동 6-11 / 오목천동 산1-5",
            help="현재 수원시 법정동 지번을 지원합니다.",
        )
        submitted = st.form_submit_button("정보 확인하기", width="stretch")

    if submitted:
        # Clear the previous result before validation/network work so stale data
        # can never remain paired with a new or empty query.
        st.session_state.pop("search_outcome", None)
        if not query.strip():
            st.error("지번 주소를 입력해 주세요.")
        else:
            try:
                with st.spinner("건축HUB 건축물대장을 확인하고 있습니다…"):
                    st.session_state.search_outcome = _search(
                        query, _secret("BUILDING_HUB_API_KEY")
                    )
            except AddressParseError as error:
                st.error(str(error))

    outcome = st.session_state.get("search_outcome")
    if outcome is None:
        _render_intro()
    elif outcome.snapshot is not None:
        _render_api(outcome)
    elif outcome.legacy:
        _render_legacy(outcome)
    else:
        st.error(
            f"{outcome.api_error or '조회에 실패했습니다.'} "
            "보조 스냅샷에도 해당 지번이 없습니다."
        )

    with st.expander("데이터 출처와 확인 범위"):
        st.write(
            "건축HUB 건축물대장정보는 월간 갱신 공개자료입니다. 이 화면은 공식 증명서가 아니며, "
            "계약·권리분석 등 중요한 판단은 세움터·정부24 발급 대장으로 최종 확인해야 합니다."
        )
        st.write(
            "다가구 호별 면적대장과 위반건축물 여부는 건축HUB 공개 API에 없습니다. "
            "없는 값을 0 또는 정상으로 추정하지 않습니다."
        )


if __name__ == "__main__":
    render_app()
