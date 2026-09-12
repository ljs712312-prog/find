"""Discover exact Seoul parcels through the portal's public keyword search.

The index is a candidate source, not a certified exhaustive register. Never
filter on building-name, INFO_YN or road-address presence: vacant-looking and
violation parcels must still reach BuildingHUB. Match only the full PNU key.
"""
from dataclasses import dataclass
import re
import time

import requests

from src.address import ParsedAddress
from src.seoul_search import LotNumber, seoul_parcels


SEARCH_URL = "https://land.seoul.go.kr/land/wisenut/totalSearch.do"


class CandidateSearchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ParcelCandidates:
    parcels: tuple[ParsedAddress, ...]
    complete: bool
    received_rows: int
    total_rows: int
    note: str | None = None


@dataclass(frozen=True, slots=True)
class KeywordRows:
    rows: tuple[dict, ...]
    complete: bool
    received_rows: int
    total_rows: int
    note: str | None = None


class SeoulCandidateClient:
    def __init__(self, *, session=None, timeout=(3.05, 8.0), max_pages=10, max_seconds=8.0,
                 max_retries=1, sleep=time.sleep):
        self.session = session
        self.timeout = timeout
        self.max_pages = max_pages
        self.max_seconds = max_seconds
        self.max_retries, self.sleep = max_retries, sleep

    def _request_payload(self, session, query, offset, deadline):
        for attempt in range(self.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                response = session.post(SEARCH_URL, data={
                    "query": query, "collection": "land", "range": "A",
                    "startCount": offset, "searchField": "ALL", "sort": "RANK", "rows": 100,
                }, timeout=tuple(min(part, remaining) for part in self.timeout),
                    headers={"Referer": "https://land.seoul.go.kr/land/index.jsp"})
                response.raise_for_status()
                return response.json()
            except requests.RequestException as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status is not None and status != 429 and not 500 <= status <= 599:
                    break
            except ValueError:
                # Empty/HTML gateway responses can be transient. Valid JSON
                # with the wrong schema is handled separately and is not retried.
                pass
            if attempt < self.max_retries and deadline - time.monotonic() > 0.25:
                self.sleep(0.25)
        raise CandidateSearchError("서울포털 주소 검색이 지연되거나 연결되지 않았습니다. 잠시 후 다시 검색해 주세요.") from None

    def find(self, lot: LotNumber) -> ParcelCandidates:
        lookup = {p.land_key.legal_dong_code: p for p in seoul_parcels(lot)}
        selected = {}
        result = self.search_rows(lot.label)
        invalid_pnu = False
        for row in result.rows:
            pnu = str(row.get("PNU") or "")
            if not re.fullmatch(r"[0-9]{19}", pnu):
                invalid_pnu = True
                continue
            land_type = "2" if lot.plat_gb_cd == "1" else "1"
            if pnu[10:] != land_type + lot.bun + lot.ji:
                continue
            parsed = lookup.get(pnu[:10])
            if parsed:
                selected[pnu] = parsed
            elif pnu.startswith("11"):
                invalid_pnu = True
        note = result.note
        if invalid_pnu:
            note = "지번 코드를 확인할 수 없는 후보가 있어 일부 주소가 빠졌을 수 있습니다. 전체 동 확인으로 추가 검색할 수 있습니다."
        return ParcelCandidates(tuple(sorted(selected.values(), key=lambda p: (p.district, p.legal_dong))),
                                result.complete and not invalid_pnu, result.received_rows, result.total_rows, note)

    def search_rows(self, query: str) -> KeywordRows:
        """Read the bounded, paginated index; callers must validate exact identity."""
        session = self.session or requests.Session()
        total, received = None, 0
        fingerprints = set()
        complete, note = False, None
        collected = []
        started = time.monotonic()
        try:
            for page in range(self.max_pages):
                try:
                    payload = self._request_payload(session, query, received, started + self.max_seconds)
                except CandidateSearchError:
                    if not collected:
                        raise
                    note = "주소 검색의 다음 페이지가 지연되어 확인된 후보를 먼저 표시합니다. 다시 검색하면 추가 확인합니다."
                    break
                try:
                    data = payload["result"]["land"]
                    current_total = data["thisTotalCount"]
                    if isinstance(current_total, bool) or not re.fullmatch(r"[0-9]+", str(current_total)):
                        raise ValueError()
                    current_total = int(current_total)
                    rows = data.get("colDetailList", [])
                    if not isinstance(rows, list) or (not rows and current_total > received):
                        raise ValueError()
                    if any(not isinstance(row, dict) for row in rows):
                        raise ValueError()
                    if received + len(rows) > current_total:
                        raise ValueError()
                except (ValueError, KeyError, TypeError):
                    raise CandidateSearchError("서울포털 주소 검색 응답을 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.") from None
                if total is not None and total != current_total:
                    note = "검색 중 주소 목록이 변경되어 일부 후보만 확인했습니다."
                    break
                total = current_total
                fingerprint = tuple((str(row.get("DOCID")), str(row.get("PNU"))) for row in rows)
                if rows and fingerprint in fingerprints:
                    note = "주소 검색의 다음 페이지가 반복되어 일부 후보만 확인했습니다."
                    break
                fingerprints.add(fingerprint)
                collected.extend(rows)
                received += len(rows)
                if received >= total:
                    complete = True
                    break
                if len(rows) < 100:
                    note = "주소 검색 목록 일부가 누락되어 빠른 검색을 마쳤습니다."
                    break
                if time.monotonic() - started >= self.max_seconds:
                    break
            if not complete and note is None:
                note = "검색어와 관련된 주소가 많아 일부 후보를 먼저 확인했습니다."
            return KeywordRows(tuple(collected), complete, received, total or 0, note)
        except requests.RequestException:
            raise CandidateSearchError("서울포털 주소 검색이 지연되거나 연결되지 않았습니다. 잠시 후 다시 검색해 주세요.") from None
        finally:
            if self.session is None:
                session.close()
