"""Best-effort screening against the public Gyeonggi real-estate portal.

The portal deliberately withholds building rows for violation and security
buildings.  An empty list is therefore *not* proof of a violation: it can also
mean a security building, a linkage delay, or missing portal data.  This
adapter preserves that ambiguity and must never be presented as a certified
building-register result.

The portal does not publish this endpoint as a supported OpenAPI.  Calls are
made only after an explicit user action and the UI always offers the original
portal page as the durable fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlencode

import requests

from src.vworld import land_key_to_pnu


PORTAL_ORIGIN = "https://gris.gg.go.kr"
PORTAL_PAGE_URL = f"{PORTAL_ORIGIN}/ost/oneStopView.do"
PORTAL_BUILDING_LIST_URL = (
    f"{PORTAL_ORIGIN}/lot/buld/selectLotBuldNmList.do"
)


class PortalBuildingState(str, Enum):
    """What the portal exposes for a parcel, without inferring legal status."""

    VISIBLE = "VISIBLE"
    NOT_LISTED = "NOT_LISTED"


class GyeonggiPortalError(RuntimeError):
    """Raised when the screening response cannot be trusted."""


@dataclass(frozen=True, slots=True)
class PortalBuildingReference:
    state: PortalBuildingState
    building_count: int
    building_names: tuple[str, ...]
    source_url: str
    source: str = "경기부동산포털"


def gyeonggi_portal_url(land_key: Any) -> str:
    """Return the public parcel page for a BuildingHUB land key."""

    return f"{PORTAL_PAGE_URL}?{urlencode({'code': '01', 'pnu': land_key_to_pnu(land_key)})}"


def _value(land_key: Any, *names: str) -> str:
    if isinstance(land_key, dict):
        for name in names:
            if name in land_key:
                return str(land_key[name])
    for name in names:
        if hasattr(land_key, name):
            return str(getattr(land_key, name))
    raise ValueError(f"토지 키에 {names[0]} 값이 없습니다.")


def _request_fields(land_key: Any) -> dict[str, str]:
    pnu = land_key_to_pnu(land_key)
    plat = _value(land_key, "plat_gb_cd", "platGbCd")
    fields = {
        "code": "",
        "pnu": pnu,
        "admDistCode": _value(land_key, "sigungu_cd", "sigunguCd"),
        "landSiteCode": _value(land_key, "bjdong_cd", "bjdongCd"),
        # The portal uses the PNU land-category values, unlike BuildingHUB.
        "lgGbn": "2" if plat == "1" else "1",
        "bobn": _value(land_key, "bun"),
        "bubn": _value(land_key, "ji"),
        "jibunNm": "",
    }
    for name in (
        "coBdngSno",
        "coBdngDng",
        "coBdngFlr",
        "coBdngHo",
        "mgmBldrgstPk",
        "regstrKindCd",
        "hoMgmBldrgstPk",
        "useCodes",
        "dongSeqno",
        "mgmUpperBldrgstPk",
        "dongNm",
        "hoNm",
        "tradeYear",
        "tradeGb",
        "dataKey",
    ):
        fields[name] = ""
    return fields


class GyeonggiPortalClient:
    """Timeout-bound, single-parcel client for the portal screening signal."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (3.05, 15.0),
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout

    def get_building_reference(self, land_key: Any) -> PortalBuildingReference:
        source_url = gyeonggi_portal_url(land_key)
        try:
            page = self._session.get(source_url, timeout=self._timeout)
            if page.status_code != 200:
                raise GyeonggiPortalError(
                    f"경기부동산포털이 HTTP {page.status_code}로 응답했습니다."
                )
            response = self._session.post(
                PORTAL_BUILDING_LIST_URL,
                data=_request_fields(land_key),
                headers={
                    "Referer": source_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise GyeonggiPortalError(
                "경기부동산포털에 연결하지 못했습니다."
            ) from exc

        if response.status_code != 200:
            raise GyeonggiPortalError(
                f"경기부동산포털이 HTTP {response.status_code}로 응답했습니다."
            )
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise GyeonggiPortalError(
                "경기부동산포털 응답을 해석할 수 없습니다."
            ) from exc
        if not isinstance(payload, list) or any(
            not isinstance(item, dict) for item in payload
        ):
            raise GyeonggiPortalError(
                "경기부동산포털 응답 형식이 올바르지 않습니다."
            )

        names = tuple(
            dict.fromkeys(
                str(item.get("bldNm") or item.get("regstrKindNm") or "").strip()
                for item in payload
                if str(
                    item.get("bldNm") or item.get("regstrKindNm") or ""
                ).strip()
            )
        )
        return PortalBuildingReference(
            state=(
                PortalBuildingState.VISIBLE
                if payload
                else PortalBuildingState.NOT_LISTED
            ),
            building_count=len(payload),
            building_names=names,
            source_url=source_url,
        )
