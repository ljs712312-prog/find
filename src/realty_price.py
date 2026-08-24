"""Official realty-price lookup used by the Streamlit application.

The public Realty Price Notice search pages do not expose a documented URL
that can prefill a parcel. Their browser UI does, however, read the same
public JSON endpoints. This adapter performs the exact parcel/unit search on
an explicit user action and retains the public search pages as fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any, Mapping
from urllib.parse import urlparse

import requests


REALTY_PRICE_HOME_URL = "https://www.realtyprice.kr/notice/main/main.do"
COLLECTIVE_HOUSING_PRICE_URL = (
    "https://www.realtyprice.kr/notice/town/searchPastYear.htm"
)
INDIVIDUAL_HOUSING_PRICE_URL = (
    "https://www.realtyprice.kr/notice/hpindividual/search.htm"
)

_ORIGIN = "https://www.realtyprice.kr"
_INDIVIDUAL_SEARCH_URL = f"{_ORIGIN}/notice/search/hpiSearchListApi.search"
_COLLECTIVE_OPTION_URL = f"{_ORIGIN}/notice/search/searchApt.search"
_COLLECTIVE_PRICE_URL = (
    f"{_ORIGIN}/notice/search/townPriceListPastYearMap.search"
)
_RELAY_ENDPOINTS = {
    _INDIVIDUAL_SEARCH_URL: "individual",
    _COLLECTIVE_OPTION_URL: "collective-options",
    _COLLECTIVE_PRICE_URL: "collective-prices",
}
_RELAY_PARAM_FIELDS = {
    "individual": (
        "reg",
        "eub",
        "san",
        "bun1",
        "bun2",
        "from_year",
        "to_year",
    ),
    "collective-options": (
        "reg",
        "eub",
        "bun1",
        "bun2",
        "year",
        "notice_date",
        "gbnApt",
        "apt_code",
        "dong_code",
    ),
    "collective-prices": (
        "reg",
        "eub",
        "bun1",
        "bun2",
        "year",
        "notice_date",
        "apt_code",
        "dong_code",
        "ho_code",
    ),
}


class RealtyPriceError(RuntimeError):
    """Raised when a public price response cannot be trusted."""


@dataclass(frozen=True, slots=True)
class IndividualHousingPrice:
    base_date: str
    amount: int
    address: str
    land_area: Decimal | None
    building_area: Decimal | None
    calculated_land_area: Decimal | None
    residential_area: Decimal | None


@dataclass(frozen=True, slots=True)
class PriceOption:
    code: str
    name: str
    notice_date: str | None = None


@dataclass(frozen=True, slots=True)
class CollectiveHousingPrice:
    notice_date: str
    amount: int
    private_area: Decimal | None
    complex_name: str
    dong_name: str
    ho_name: str
    address: str


@dataclass(frozen=True, slots=True)
class CollectivePriceResult:
    complex_name: str
    dong_name: str
    ho_name: str
    prices: tuple[CollectiveHousingPrice, ...]


def _value(land_key: Any, *names: str) -> str:
    if isinstance(land_key, Mapping):
        for name in names:
            if name in land_key:
                return str(land_key[name])
    for name in names:
        if hasattr(land_key, name):
            return str(getattr(land_key, name))
    raise ValueError(f"토지 키에 {names[0]} 값이 없습니다.")


def _decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _amount(value: Any) -> int:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if not text:
        raise RealtyPriceError("공시가격 금액을 해석할 수 없습니다.")
    return int(text)


def _label(value: Any, *, suffix: str = "") -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()
    if suffix and text.endswith(suffix):
        text = text[: -len(suffix)]
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text


def derive_relay_hmac_secret(service_key: str) -> str:
    """Derive the existing relay credential without transmitting the API key."""

    material = f"buildinghub-relay-v1\x00{service_key}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class RealtyPriceClient:
    """Timeout-bound client for the official public price search."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (3.05, 20.0),
        current_year: int | None = None,
        relay_url: str | None = None,
        relay_hmac_secret: str | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout
        self._year = current_year or date.today().year
        self._relay_url = self._validate_relay_url(relay_url)
        self._relay_hmac_secret = relay_hmac_secret
        if bool(self._relay_url) != bool(self._relay_hmac_secret):
            raise ValueError("공시가격 중계 URL과 서명 키는 함께 설정해야 합니다.")
        self._direct_unavailable = False

    @staticmethod
    def _validate_relay_url(value: str | None) -> str | None:
        if value is None:
            return None
        url = str(value).strip().rstrip("/")
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("공시가격 중계 URL은 안전한 HTTPS 주소여야 합니다.")
        return url

    def _seed(self, page_url: str) -> None:
        try:
            response = self._session.get(page_url, timeout=self._timeout)
        except requests.RequestException as exc:
            if self._relay_url:
                self._direct_unavailable = True
                return
            raise RealtyPriceError("부동산공시가격알리미에 연결하지 못했습니다.") from exc
        if response.status_code != 200:
            if self._relay_url:
                self._direct_unavailable = True
                return
            raise RealtyPriceError(
                f"부동산공시가격알리미가 HTTP {response.status_code}로 응답했습니다."
            )

    def _relay_items(
        self,
        url: str,
        params: Mapping[str, str],
    ) -> tuple[Mapping[str, Any], ...]:
        endpoint = _RELAY_ENDPOINTS.get(url)
        if not endpoint or not self._relay_url or not self._relay_hmac_secret:
            raise RealtyPriceError("부동산공시가격알리미에 연결하지 못했습니다.")
        relay_params = {
            field: str(params.get(field, ""))
            for field in _RELAY_PARAM_FIELDS[endpoint]
        }
        body = {"params": relay_params}
        encoded = _canonical_json(body)
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        signed = f"{timestamp}\n{nonce}\nrealty-price:{endpoint}\n{encoded}"
        signature = hmac.new(
            self._relay_hmac_secret.encode("utf-8"),
            signed.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        try:
            response = self._session.post(
                f"{self._relay_url}/v1/realty-price/{endpoint}",
                data=encoded.encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Building-Hub-Timestamp": timestamp,
                    "X-Building-Hub-Nonce": nonce,
                    "X-Building-Hub-Signature": signature,
                },
                timeout=(5.0, self._timeout[1]),
            )
        except requests.RequestException as exc:
            raise RealtyPriceError("공시가격 중계 서버에 연결하지 못했습니다.") from exc
        if response.status_code != 200:
            raise RealtyPriceError(
                f"공시가격 중계 조회가 HTTP {response.status_code}로 실패했습니다."
            )
        return self._response_items(response)

    @staticmethod
    def _response_items(response: Any) -> tuple[Mapping[str, Any], ...]:
        try:
            payload = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise RealtyPriceError("공시가격 응답을 해석할 수 없습니다.") from exc
        if not isinstance(payload, Mapping):
            raise RealtyPriceError("공시가격 응답 형식이 올바르지 않습니다.")
        model = payload.get("model")
        if not isinstance(model, Mapping):
            raise RealtyPriceError("공시가격 응답에 결과 모델이 없습니다.")
        message = str(model.get("message") or "").strip()
        if message:
            raise RealtyPriceError(message)
        items = model.get("list")
        if items is None:
            return ()
        if not isinstance(items, list) or any(
            not isinstance(item, Mapping) for item in items
        ):
            raise RealtyPriceError("공시가격 목록 형식이 올바르지 않습니다.")
        return tuple(items)

    def _items(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        referer: str,
    ) -> tuple[Mapping[str, Any], ...]:
        if self._direct_unavailable:
            return self._relay_items(url, params)
        try:
            response = self._session.get(
                url,
                params=params,
                headers={
                    "Referer": referer,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            if self._relay_url:
                self._direct_unavailable = True
                return self._relay_items(url, params)
            raise RealtyPriceError("공시가격 조회 중 연결이 끊겼습니다.") from exc
        if response.status_code != 200:
            if self._relay_url:
                self._direct_unavailable = True
                return self._relay_items(url, params)
            raise RealtyPriceError(
                f"공시가격 조회가 HTTP {response.status_code}로 실패했습니다."
            )
        try:
            return self._response_items(response)
        except RealtyPriceError:
            if self._relay_url:
                self._direct_unavailable = True
                return self._relay_items(url, params)
            raise

    def get_individual_prices(
        self,
        land_key: Any,
    ) -> tuple[IndividualHousingPrice, ...]:
        """Return individual-house prices for detached/multi-family housing."""

        self._seed(INDIVIDUAL_HOUSING_PRICE_URL)
        plat = _value(land_key, "plat_gb_cd", "platGbCd")
        params = {
            "page_no": "1",
            "gbn": "1",
            "year": "",
            "reg": _value(land_key, "sigungu_cd", "sigunguCd"),
            "eub": _value(land_key, "bjdong_cd", "bjdongCd"),
            "san": "2" if plat == "1" else "1",
            "bun1": _value(land_key, "bun"),
            "bun2": _value(land_key, "ji"),
            "road_code": "",
            "p_initialword": "",
            "build_bun1": "",
            "build_bun2": "",
            "from_year": "2005",
            "to_year": str(self._year),
            "dong_gbn": "",
            "tabGbn": "Text",
        }
        items = self._items(
            _INDIVIDUAL_SEARCH_URL,
            params,
            referer=INDIVIDUAL_HOUSING_PRICE_URL,
        )
        prices = tuple(
            IndividualHousingPrice(
                base_date=str(item.get("base_ymd") or "").strip(),
                amount=_amount(item.get("hprice_w")),
                address=str(
                    item.get("full_addr_name") or item.get("addr") or ""
                ).strip(),
                land_area=_decimal(item.get("tbook_area")),
                building_area=_decimal(item.get("bldg_garea")),
                calculated_land_area=_decimal(item.get("calc_larea")),
                residential_area=_decimal(item.get("res_area")),
            )
            for item in items
            if str(item.get("base_ymd") or "").strip()
        )
        return tuple(sorted(prices, key=lambda item: item.base_date, reverse=True))

    def _collective_fields(self, land_key: Any) -> dict[str, str]:
        return {
            "gbn": "1",
            "year": str(self._year),
            "notice_date": "",
            "notice_date_year": f"{self._year}0430",
            "gbnApt": "",
            "road_reg": "",
            "road": "",
            "initialword": "",
            "build_bun1": "",
            "build_bun2": "",
            "reg": _value(land_key, "sigungu_cd", "sigunguCd"),
            "eub": _value(land_key, "bjdong_cd", "bjdongCd"),
            "apt_name": "",
            "bun1": str(int(_value(land_key, "bun"))),
            "bun2": str(int(_value(land_key, "ji"))),
            "apt_code": "",
            "dong_code": "",
            "ho_code": "",
            "past_yn": "1",
            "init_gbn": "N",
            "searchGbnRoad": "",
            "searchGbnBunji": "1",
            "searchGbnBunjiYear": "",
        }

    def _options(
        self,
        fields: Mapping[str, str],
    ) -> tuple[PriceOption, ...]:
        items = self._items(
            _COLLECTIVE_OPTION_URL,
            fields,
            referer=COLLECTIVE_HOUSING_PRICE_URL,
        )
        return tuple(
            PriceOption(
                code=str(item.get("code") or "").strip(),
                name=str(item.get("name") or "").strip(),
                notice_date=(
                    str(item.get("notice_date")).strip()
                    if item.get("notice_date")
                    else None
                ),
            )
            for item in items
            if str(item.get("code") or "").strip()
            and str(item.get("name") or "").strip()
        )

    def _unit_candidates(
        self,
        land_key: Any,
        *,
        target_building: str,
        target_dong: str,
        target_ho: str,
    ) -> tuple[tuple[int, PriceOption, PriceOption, PriceOption], ...]:
        fields = self._collective_fields(land_key)
        complexes = self._options(fields)
        candidates: list[tuple[int, PriceOption, PriceOption, PriceOption]] = []
        target_building_key = _label(target_building)
        target_dong_key = _label(target_dong, suffix="동")
        target_ho_key = _label(target_ho, suffix="호")
        if not target_ho_key:
            return ()

        for complex_item in complexes:
            dong_fields = dict(fields)
            dong_fields.update(
                {
                    "gbnApt": "DONG",
                    "apt_code": complex_item.code,
                    "notice_date": complex_item.notice_date or "",
                }
            )
            for dong_item in self._options(dong_fields):
                official_dong_key = _label(dong_item.name, suffix="동")
                if (
                    target_dong_key
                    and official_dong_key
                    and official_dong_key != target_dong_key
                ):
                    continue
                unit_fields = dict(dong_fields)
                unit_fields.update(
                    {
                        "gbnApt": "HO",
                        "dong_code": dong_item.code,
                        "notice_date": (
                            dong_item.notice_date
                            or complex_item.notice_date
                            or ""
                        ),
                    }
                )
                for unit_item in self._options(unit_fields):
                    if _label(unit_item.name, suffix="호") != target_ho_key:
                        continue
                    official_building_key = _label(complex_item.name)
                    building_match = bool(
                        target_building_key
                        and (
                            target_building_key in official_building_key
                            or official_building_key in target_building_key
                        )
                    )
                    dong_match = bool(
                        target_dong_key
                        and official_dong_key == target_dong_key
                    )
                    candidates.append(
                        (
                            int(building_match) * 2 + int(dong_match),
                            complex_item,
                            dong_item,
                            unit_item,
                        )
                    )
        return tuple(candidates)

    def get_collective_prices(
        self,
        land_key: Any,
        *,
        building_name: str = "",
        dong_name: str = "",
        ho_name: str,
    ) -> CollectivePriceResult:
        """Resolve one official unit and return its annual published prices."""

        self._seed(COLLECTIVE_HOUSING_PRICE_URL)
        candidates = self._unit_candidates(
            land_key,
            target_building=building_name,
            target_dong=dong_name,
            target_ho=ho_name,
        )
        if not candidates:
            raise RealtyPriceError(
                "공시가격알리미에서 선택한 호실을 정확히 연결하지 못했습니다."
            )
        best_score = max(item[0] for item in candidates)
        best = tuple(item for item in candidates if item[0] == best_score)
        distinct = {
            (item[1].code, item[2].code, item[3].code) for item in best
        }
        if len(distinct) != 1:
            raise RealtyPriceError(
                "같은 호실명이 여러 단지에 있어 자동으로 하나를 선택하지 않았습니다."
            )
        _, complex_item, dong_item, unit_item = best[0]

        fields = self._collective_fields(land_key)
        fields.update(
            {
                "page_no": "1",
                "reg_name": "",
                "sreg": "",
                "seub": "",
                "old_reg": "",
                "old_eub": "",
                "notice_date": (
                    unit_item.notice_date
                    or dong_item.notice_date
                    or complex_item.notice_date
                    or ""
                ),
                "apt_code": complex_item.code,
                "dong_code": dong_item.code,
                "ho_code": unit_item.code,
                "tabGbn": "Text",
                "full_addr_name": "",
                "dong_name": "",
                "ho_name": "",
                "notice_amt": "",
                "ktown_ho_seq": "",
                "print_yn": "0",
                "capcha": "",
                "capcha_chk_yn": "",
                "recaptcha_token": "",
            }
        )
        items = self._items(
            _COLLECTIVE_PRICE_URL,
            fields,
            referer=COLLECTIVE_HOUSING_PRICE_URL,
        )
        prices = tuple(
            CollectiveHousingPrice(
                notice_date=str(
                    item.get("notice_date_name")
                    or item.get("notice_date")
                    or ""
                ).strip(),
                amount=_amount(item.get("notice_amt")),
                private_area=_decimal(item.get("priv_area")),
                complex_name=str(item.get("apt_name") or complex_item.name).strip(),
                dong_name=str(item.get("dong_name") or dong_item.name).strip(),
                ho_name=str(item.get("ho_name") or unit_item.name).strip(),
                address=str(
                    item.get("full_addr_name")
                    or item.get("short_addr_name")
                    or ""
                ).strip(),
            )
            for item in items
            if str(item.get("notice_amt") or "").strip()
        )
        prices = tuple(
            sorted(prices, key=lambda item: item.notice_date, reverse=True)
        )
        return CollectivePriceResult(
            complex_name=complex_item.name,
            dong_name=dong_item.name,
            ho_name=unit_item.name,
            prices=prices,
        )
