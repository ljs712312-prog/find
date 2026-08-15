"""Official BuildingHUB building-permit API client.

The public-data gateway and pagination envelope are identical to the building
register service, so the defensive transport implementation is reused while
the host and operation allow-list stay separate.  Only the operations approved
for this app's multi-family reference lookup are exposed.
"""

from __future__ import annotations

from .building_hub import BuildingHubClient


class BuildingPermitHubClient(BuildingHubClient):
    """Fetch rows from the official ``ArchPmsHubService``."""

    BASE_URL = "https://apis.data.go.kr/1613000/ArchPmsHubService"

    ENDPOINTS = frozenset(
        {
            "getApBasisOulnInfo",
            "getApDongOulnInfo",
            "getApFlrOulnInfo",
            "getApHoOulnInfo",
            "getApExposPubuseAreaInfo",
            "getApHoExposPubuseAreaInfo",
            "getApPlatPlcInfo",
            "getApHsTpInfo",
        }
    )
    _FILTERS = frozenset({"startDate", "endDate"})


__all__ = ["BuildingPermitHubClient"]
