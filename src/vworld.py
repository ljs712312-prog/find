"""Optional VWorld GIS-building lookup for a violation-status reference.

The BuildingHUB building-register API does not expose a violation flag.  When
the operator supplies a separate VWorld key, this adapter reads ``violt_bild``
from the official GIS integrated-building WFS.  The value is deliberately
modelled as a *reference*, not as a certified building-register result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests


VWORLD_WFS_URL = "https://api.vworld.kr/ned/wfs/getBldgisSpceWFS"


class ViolationState(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    MIXED = "MIXED"


class VWorldError(RuntimeError):
    """Raised when VWorld cannot provide a trustworthy response."""


@dataclass(frozen=True, slots=True)
class ViolationReference:
    state: ViolationState
    raw_values: tuple[str, ...] = ()
    feature_count: int = 0
    source: str = "VWorld GIS건물통합정보"
    as_of: str | None = None
    message: str = ""


def land_key_to_pnu(land_key: Any) -> str:
    """Convert a BuildingHUB land key to a 19-digit PNU."""

    def value(*names: str) -> str:
        if isinstance(land_key, dict):
            for name in names:
                if name in land_key:
                    return str(land_key[name])
        for name in names:
            if hasattr(land_key, name):
                return str(getattr(land_key, name))
        raise ValueError(f"토지 키에 {names[0]} 값이 없습니다.")

    sigungu = value("sigungu_cd", "sigunguCd")
    bjdong = value("bjdong_cd", "bjdongCd")
    plat = value("plat_gb_cd", "platGbCd")
    bun = value("bun")
    ji = value("ji")
    if plat not in {"0", "1"}:
        raise ValueError("블록 주소는 PNU로 변환할 수 없습니다.")
    special_land = "2" if plat == "1" else "1"
    pnu = f"{sigungu}{bjdong}{special_land}{bun}{ji}"
    if len(pnu) != 19 or not pnu.isdigit():
        raise ValueError("PNU를 만들 수 없는 토지 키입니다.")
    return pnu


def _normalize_violation(value: Any) -> ViolationState:
    raw = str(value).strip().upper()
    if raw in {"1", "Y", "YES", "TRUE", "위반", "위반건축물"}:
        return ViolationState.YES
    if raw in {"0", "N", "NO", "FALSE", "정상"}:
        return ViolationState.NO
    return ViolationState.UNKNOWN


class VWorldClient:
    """Small, timeout-bound client for the official building WFS."""

    def __init__(
        self,
        api_key: str,
        *,
        domain: str | None = None,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (3.05, 15.0),
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("VWorld API 키가 필요합니다.")
        self._api_key = api_key.strip()
        self._domain = domain.strip() if domain else None
        self._session = session or requests.Session()
        self._timeout = timeout

    def get_violation_reference(self, land_key: Any) -> ViolationReference:
        params = {
            "typename": "dt_d010",
            "pnu": land_key_to_pnu(land_key),
            "maxFeatures": "1000",
            "resultType": "results",
            "srsName": "EPSG:4326",
            "output": "application/json",
            "key": self._api_key,
        }
        if self._domain:
            params["domain"] = self._domain

        try:
            response = self._session.get(
                VWORLD_WFS_URL, params=params, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise VWorldError("VWorld 연결에 실패했습니다.") from exc

        # Never include response.url: it contains the API key.
        if response.status_code != 200:
            raise VWorldError(f"VWorld가 HTTP {response.status_code}로 응답했습니다.")
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            message = response.text[:500]
            if "INVALID_KEY" in message or "INCORRECT_KEY" in message:
                raise VWorldError("VWorld 인증키 또는 등록 도메인을 확인해 주세요.") from exc
            raise VWorldError("VWorld 응답을 해석할 수 없습니다.") from exc

        if not isinstance(payload, dict):
            raise VWorldError("VWorld 응답 형식이 올바르지 않습니다.")
        features = payload.get("features") or []
        if not isinstance(features, list):
            raise VWorldError("VWorld 피처 형식이 올바르지 않습니다.")
        if not features:
            return ViolationReference(
                state=ViolationState.UNKNOWN,
                message="해당 필지의 GIS건물통합정보가 없습니다.",
            )

        raw_values: list[str] = []
        states: set[ViolationState] = set()
        dates: list[str] = []
        for feature in features:
            props = feature.get("properties", {}) if isinstance(feature, dict) else {}
            if not isinstance(props, dict):
                continue
            raw = props.get("violt_bild")
            if raw is not None and str(raw).strip():
                raw_values.append(str(raw).strip())
                states.add(_normalize_violation(raw))
            last_update = props.get("last_updt_dt")
            if last_update:
                dates.append(str(last_update))

        known_states = states - {ViolationState.UNKNOWN}
        if known_states == {ViolationState.YES}:
            state = ViolationState.YES
        elif known_states == {ViolationState.NO} and ViolationState.UNKNOWN not in states:
            state = ViolationState.NO
        elif ViolationState.YES in known_states and ViolationState.NO in known_states:
            state = ViolationState.MIXED
        else:
            state = ViolationState.UNKNOWN

        return ViolationReference(
            state=state,
            raw_values=tuple(sorted(set(raw_values))),
            feature_count=len(features),
            as_of=max(dates) if dates else None,
            message="발급 건축물대장으로 최종 확인이 필요합니다.",
        )

