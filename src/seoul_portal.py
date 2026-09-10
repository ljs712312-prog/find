"""Opt-in, single-parcel reference from Seoul's public building-info page.

The portal's notice says violation buildings have not been displayed since
2025-09-12. An empty list is therefore a reason to check the certified register,
not proof of violation. These are the page's own endpoints, not a supported
OpenAPI; schema/network failures must never be treated as empty search results.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

import requests

from src.address import LandKey, SEOUL_DISTRICTS


SEOUL_PORTAL_URL = "https://land.seoul.go.kr/land/wskras/generalInfo.do"
SEOUL_BUILDING_LIST_URL = "https://land.seoul.go.kr/land/eais/getBldrgstList.do"


class SeoulPortalError(RuntimeError):
    """The portal could not return a trustworthy parcel reference."""


class SeoulPortalState(str, Enum):
    VISIBLE = "VISIBLE"
    NOT_LISTED = "NOT_LISTED"
    FLAGGED = "FLAGGED"


@dataclass(frozen=True, slots=True)
class SeoulPortalBuilding:
    register_pk: str
    name: str
    dong: str
    register_kind: str
    purpose: str
    violation_raw: str


@dataclass(frozen=True, slots=True)
class SeoulPortalReference:
    state: SeoulPortalState
    buildings: tuple[SeoulPortalBuilding, ...] = ()
    checked_at: str = ""
    source_url: str = SEOUL_PORTAL_URL


def _request_fields(land_key: LandKey) -> dict[str, str]:
    if land_key.sigungu_cd not in SEOUL_DISTRICTS:
        raise SeoulPortalError("서울 지번만 서울부동산정보광장에서 확인할 수 있습니다.")
    if land_key.plat_gb_cd not in {"0", "1"}:
        raise SeoulPortalError("대지·산번지만 서울포털에서 확인할 수 있습니다.")
    return {
        "sggCd": land_key.sigungu_cd,
        "bjdongCd": land_key.bjdong_cd,
        "landGbn": "2" if land_key.plat_gb_cd == "1" else "1",
        "bonbeon": land_key.bun,
        "bubeon": land_key.ji,
    }


def _text(row: dict, name: str) -> str:
    return str(row.get(name) or "").strip()


def parse_reference(payload: Any, land_key: LandKey) -> SeoulPortalReference:
    """Validate the complete envelope and every returned row's jurisdiction."""
    fields = _request_fields(land_key)
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), list):
        raise SeoulPortalError("서울포털 응답 형식을 확인하지 못했습니다. 원본 사이트에서 확인해 주세요.")
    if any(payload.get(key) for key in ("error", "errors", "errorCode")):
        raise SeoulPortalError("서울포털이 오류를 반환했습니다. 잠시 후 다시 확인해 주세요.")
    records = payload["result"]
    buildings = {}
    for row in records:
        if not isinstance(row, dict) or not _text(row, "bldrgstPk"):
            raise SeoulPortalError("서울포털 건축물 목록을 판독하지 못했습니다.")
        for name, expected in fields.items():
            actual = _text(row, name)
            if not actual.isascii() or not actual.isdigit() or actual.zfill(len(expected)) != expected:
                raise SeoulPortalError(
                    "서울포털이 다른 지번·관련 지번의 자료를 반환했거나 주소가 누락되었습니다. "
                    "현재 지번의 위반 여부로 해석하지 말고 원본 대장을 확인해 주세요."
                )
        building = SeoulPortalBuilding(
            register_pk=_text(row, "bldrgstPk"),
            name=_text(row, "bldNm"),
            dong=_text(row, "dongNm"),
            register_kind=_text(row, "regstrKindNm"),
            purpose=_text(row, "mainPurpsNm"),
            violation_raw=str(row.get("violBldYn") if row.get("violBldYn") is not None else "").strip(),
        )
        if building.register_pk in buildings and buildings[building.register_pk] != building:
            raise SeoulPortalError("서울포털의 같은 대장에 서로 다른 정보가 있어 원본 확인이 필요합니다.")
        buildings[building.register_pk] = building
    values = tuple(buildings.values())
    if not values:
        state = SeoulPortalState.NOT_LISTED
    elif any(b.violation_raw.upper() in {"1", "Y", "YES", "위반", "위반건축물"} for b in values):
        state = SeoulPortalState.FLAGGED
    else:
        state = SeoulPortalState.VISIBLE
    return SeoulPortalReference(
        state=state, buildings=values,
        checked_at=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y.%m.%d %H:%M"),
    )


class SeoulPortalClient:
    def __init__(self, *, session=None, timeout=(3.05, 15.0)):
        self._session = session
        self._timeout = timeout

    def get_building_reference(self, land_key: LandKey) -> SeoulPortalReference:
        fields = _request_fields(land_key)
        session = self._session or requests.Session()
        try:
            page = session.get(SEOUL_PORTAL_URL, timeout=self._timeout)
            page.raise_for_status()
            response = session.post(
                SEOUL_BUILDING_LIST_URL, data=fields,
                headers={"Referer": SEOUL_PORTAL_URL, "X-Requested-With": "XMLHttpRequest"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                raise SeoulPortalError("서울포털 응답을 읽지 못했습니다. 위반 여부는 확인되지 않았습니다.") from None
            return parse_reference(payload, land_key)
        except requests.RequestException:
            raise SeoulPortalError("서울포털 연결이 지연되거나 실패했습니다. 위반 여부는 확인되지 않았습니다.") from None
        finally:
            if self._session is None:
                session.close()
