from decimal import Decimal
from urllib.parse import urlparse

import pytest

from src.address import LandKey
from src.realty_price import (
    COLLECTIVE_HOUSING_PRICE_URL,
    INDIVIDUAL_HOUSING_PRICE_URL,
    REALTY_PRICE_HOME_URL,
    RealtyPriceClient,
    RealtyPriceError,
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
        return self.responses.pop(0)


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
