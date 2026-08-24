from urllib.parse import urlparse

from src.realty_price import (
    COLLECTIVE_HOUSING_PRICE_URL,
    INDIVIDUAL_HOUSING_PRICE_URL,
    INDIVIDUAL_LAND_PRICE_URL,
    REALTY_PRICE_HOME_URL,
)


def test_all_price_links_use_the_official_https_host() -> None:
    for url in (
        REALTY_PRICE_HOME_URL,
        COLLECTIVE_HOUSING_PRICE_URL,
        INDIVIDUAL_HOUSING_PRICE_URL,
        INDIVIDUAL_LAND_PRICE_URL,
    ):
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.hostname == "www.realtyprice.kr"


def test_price_links_open_the_relevant_public_search_pages() -> None:
    assert "/town/searchPastYear.htm" in COLLECTIVE_HOUSING_PRICE_URL
    assert "/hpindividual/search.htm" in INDIVIDUAL_HOUSING_PRICE_URL
    assert "/gsindividual/search.htm" in INDIVIDUAL_LAND_PRICE_URL
