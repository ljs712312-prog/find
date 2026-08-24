from decimal import Decimal
from urllib.parse import urlparse

import pytest
import requests

from src.address import LandKey
from src.realty_price import (
    COLLECTIVE_HOUSING_PRICE_URL,
    INDIVIDUAL_HOUSING_PRICE_URL,
    REALTY_PRICE_HOME_URL,
    RealtyPriceClient,
    RealtyPriceError,
    derive_relay_hmac_secret,
)


LAND = LandKey("41111", "13400", "0", "0396", "0030")
COLLECTIVE_LAND = LandKey("41115", "14000", "0", "0585", "0001")


class FakeResponse:
    def __init__(self, payload=None, *, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, *responses: FakeResponse):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _payload(items):
    return {"model": {"list": items}}


def test_all_price_links_use_the_official_https_host() -> None:
    for url in (
        REALTY_PRICE_HOME_URL,
        COLLECTIVE_HOUSING_PRICE_URL,
        INDIVIDUAL_HOUSING_PRICE_URL,
    ):
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.hostname == "www.realtyprice.kr"


def test_individual_house_lookup_prefills_the_exact_parcel() -> None:
    session = FakeSession(
        FakeResponse({}),
        FakeResponse(
            _payload(
                [
                    {
                        "base_ymd": "2026/01/01",
                        "hprice_w": "722,000,000",
                        "full_addr_name": "경기도 수원장안구 영화동 396-30",
                        "tbook_area": "218.3",
                        "bldg_garea": "557.87",
                        "calc_larea": "185.64",
                        "res_area": "518.38",
                    }
                ]
            )
        ),
    )

    prices = RealtyPriceClient(
        session=session, current_year=2026
    ).get_individual_prices(LAND)

    assert prices[0].amount == 722_000_000
    assert prices[0].land_area == Decimal("218.3")
    _, kwargs = session.calls[1]
    assert kwargs["params"]["reg"] == "41111"
    assert kwargs["params"]["eub"] == "13400"
    assert kwargs["params"]["bun1"] == "0396"
    assert kwargs["params"]["bun2"] == "0030"
    assert kwargs["params"]["san"] == "1"


def test_vworld_individual_lookup_uses_exact_pnu_without_web_seed() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "indvdHousingPrices": {
                    "resultCode": "OK",
                    "totalCount": "1",
                    "field": [
                        {
                            "pnu": "4111113400103960030",
                            "ldCodeNm": "경기도 수원시 장안구 영화동",
                            "mnnmSlno": "396-30",
                            "stdrYear": "2026",
                            "stdrMt": "01",
                            "housePc": "722000000",
                            "ladRegstrAr": "218.3",
                            "buldAllTotAr": "557.87",
                            "calcPlotAr": "185.64",
                        }
                    ],
                }
            }
        )
    )

    prices = RealtyPriceClient(
        session=session,
        vworld_api_key="vworld-key",
        vworld_domain="won-top-finder-work.streamlit.app",
    ).get_individual_prices(LAND)

    assert prices[0].amount == 722_000_000
    assert prices[0].base_date == "202601"
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/getIndvdHousingPriceAttr")
    assert kwargs["params"]["pnu"] == "4111113400103960030"
    assert kwargs["params"]["domain"] == "won-top-finder-work.streamlit.app"


def test_vworld_collective_lookup_prefills_pnu_dong_and_unit() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "apartHousingPrices": {
                    "resultCode": "OK",
                    "totalCount": "1",
                    "field": [
                        {
                            "aphusCode": "20358271",
                            "aphusNm": "다온하우스",
                            "dongNm": "동명없음",
                            "hoNm": "201",
                            "stdrYear": "2026",
                            "stdrMt": "01",
                            "prvuseAr": "22.81",
                            "pblntfPc": "88000000",
                            "ldCodeNm": "경기도 수원시 팔달구 우만동",
                            "mnnmSlno": "585-1",
                        }
                    ],
                }
            }
        )
    )

    result = RealtyPriceClient(
        session=session,
        vworld_api_key="vworld-key",
    ).get_collective_prices(
        COLLECTIVE_LAND,
        building_name="다온하우스",
        dong_name="",
        ho_name="201호",
    )

    assert result.ho_name == "201"
    assert result.prices[0].amount == 88_000_000
    assert result.prices[0].private_area == Decimal("22.81")
    url, kwargs = session.calls[0]
    assert url.endswith("/getApartHousingPriceAttr")
    assert kwargs["params"]["pnu"] == "4111514000105850001"
    assert kwargs["params"]["hoNm"] == "201"
    assert "dongNm" not in kwargs["params"]


def test_vworld_auth_error_is_explained_without_falling_back() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "indvdHousingPrices": {
                    "resultCode": "INCORRECT_KEY",
                    "resultMsg": "인증키 정보가 올바르지 않습니다.",
                }
            }
        )
    )

    with pytest.raises(RealtyPriceError, match="인증키 또는 등록 도메인"):
        RealtyPriceClient(
            session=session,
            vworld_api_key="wrong-key",
        ).get_individual_prices(LAND)

    assert len(session.calls) == 1


def test_collective_lookup_resolves_complex_dong_and_unit_before_price() -> None:
    session = FakeSession(
        FakeResponse({}),
        FakeResponse(
            _payload(
                [
                    {
                        "code": 20358271,
                        "name": "(585-1) 다온하우스",
                        "notice_date": "20260626",
                    }
                ]
            )
        ),
        FakeResponse(
            _payload(
                [
                    {
                        "code": 1,
                        "name": "동명없음",
                        "notice_date": "20260626",
                    }
                ]
            )
        ),
        FakeResponse(
            _payload(
                [
                    {
                        "code": 1,
                        "name": "201",
                        "notice_date": "20260626",
                    },
                    {
                        "code": 2,
                        "name": "202",
                        "notice_date": "20260626",
                    },
                ]
            )
        ),
        FakeResponse(
            _payload(
                [
                    {
                        "notice_date_name": "2026.1.1",
                        "notice_amt": " 88,000,000",
                        "priv_area": "22.81",
                        "apt_name": "다온하우스",
                        "dong_name": "동명없음",
                        "ho_name": "201",
                        "full_addr_name": "경기도 수원팔달구 우만동 585-1",
                    }
                ]
            )
        ),
    )

    result = RealtyPriceClient(
        session=session, current_year=2026
    ).get_collective_prices(
        COLLECTIVE_LAND,
        building_name="다온하우스",
        dong_name="",
        ho_name="201호",
    )

    assert result.ho_name == "201"
    assert result.prices[0].amount == 88_000_000
    assert result.prices[0].private_area == Decimal("22.81")
    _, price_kwargs = session.calls[-1]
    assert price_kwargs["params"]["reg"] == "41115"
    assert price_kwargs["params"]["eub"] == "14000"
    assert price_kwargs["params"]["bun1"] == "585"
    assert price_kwargs["params"]["bun2"] == "1"
    assert price_kwargs["params"]["apt_code"] == "20358271"
    assert price_kwargs["params"]["dong_code"] == "1"
    assert price_kwargs["params"]["ho_code"] == "1"


def test_collective_lookup_does_not_guess_an_unknown_unit() -> None:
    session = FakeSession(
        FakeResponse({}),
        FakeResponse(_payload([])),
    )

    with pytest.raises(RealtyPriceError, match="정확히 연결"):
        RealtyPriceClient(session=session, current_year=2026).get_collective_prices(
            COLLECTIVE_LAND,
            ho_name="999호",
        )


def test_invalid_price_payload_is_rejected() -> None:
    session = FakeSession(FakeResponse({}), FakeResponse({"unexpected": True}))

    with pytest.raises(RealtyPriceError, match="결과 모델"):
        RealtyPriceClient(session=session).get_individual_prices(LAND)


def test_individual_lookup_uses_signed_relay_after_direct_network_failure() -> None:
    service_key = "public-data-service-key"
    session = FakeSession(
        requests.ConnectTimeout("direct blocked"),
        FakeResponse(
            _payload(
                [
                    {
                        "base_ymd": "2026/01/01",
                        "hprice_w": "722,000,000",
                    }
                ]
            )
        ),
    )
    prices = RealtyPriceClient(
        session=session,
        current_year=2026,
        relay_url="https://relay.example/functions/v1/building-hub-relay",
        relay_hmac_secret=derive_relay_hmac_secret(service_key),
    ).get_individual_prices(LAND)

    assert prices[0].amount == 722_000_000
    relay_url, relay_kwargs = session.calls[1]
    assert relay_url.endswith("/v1/realty-price/individual")
    assert len(relay_kwargs["headers"]["X-Building-Hub-Signature"]) == 64
    assert service_key not in relay_kwargs["data"].decode("utf-8")
