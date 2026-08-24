"""Stable public links for the official real-estate price notice service.

The official search pages do not expose a documented deep-link contract for
pre-filling a parcel or PNU.  Keep these links on the public search pages and
show the already-normalized parcel separately in the UI instead of depending
on session-bound, internal endpoints.
"""

from __future__ import annotations


REALTY_PRICE_HOME_URL = "https://www.realtyprice.kr/notice/main/main.do"
COLLECTIVE_HOUSING_PRICE_URL = (
    "https://www.realtyprice.kr/notice/town/searchPastYear.htm"
)
INDIVIDUAL_HOUSING_PRICE_URL = (
    "https://www.realtyprice.kr/notice/hpindividual/search.htm"
)
INDIVIDUAL_LAND_PRICE_URL = (
    "https://www.realtyprice.kr/notice/gsindividual/search.htm"
)

